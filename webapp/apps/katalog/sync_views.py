import difflib
import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch, Avg
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from apps.katalog.models import Publikasi, Tabel, KolomTabel, SyncLog, SyncAction
from apps.referensi.models import Indikator
from .sync_engine import match_columns

def norm_title(title):
    import re
    return re.sub(r'\b20\d{2}\b|\b\d{4}-\d{4}\b', '', title).lower().strip()

class SyncDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        pubs = Publikasi.objects.all().order_by('-tahun_terbit')
        context = {
            'publikasi_list': pubs,
        }
        return render(request, 'katalog/sync_dashboard.html', context)
        
    def post(self, request):
        if request.content_type == 'application/json':
            try:
                body_data = json.loads(request.body)
                action = body_data.get('action')
            except json.JSONDecodeError:
                action = None
        else:
            action = request.POST.get('action')
        
        if action == 'analyze':
            source_id = request.POST.get('source_pub')
            target_id = request.POST.get('target_pub')
            
            if not source_id or not target_id:
                return JsonResponse({'error': 'Source and Target required'}, status=400)
                
            source_pub = Publikasi.objects.get(pk=source_id)
            target_pub = Publikasi.objects.get(pk=target_id)
            
            kolom_qs = KolomTabel.objects.select_related('indikator').annotate(avg_val=Avg('fakta_set__nilai_num'))
            source_tables = Tabel.objects.filter(bab__publikasi=source_pub).prefetch_related(Prefetch('kolom_set', queryset=kolom_qs))
            target_tables = Tabel.objects.filter(bab__publikasi=target_pub).prefetch_related(Prefetch('kolom_set', queryset=kolom_qs))
            
            # Create dictionaries of source tables for faster matching
            source_dict = {norm_title(t.judul): t for t in source_tables}
            source_num_dict = {t.nomor_tabel: t for t in source_tables if t.nomor_tabel}
            
            results = []
            
            # Analyze each target table
            for t_target in target_tables:
                n_target = norm_title(t_target.judul)
                
                # Find best match
                best_match = None
                best_ratio = 0
                
                # Exact nomor_tabel match first
                if t_target.nomor_tabel and t_target.nomor_tabel in source_num_dict:
                    best_match = source_num_dict[t_target.nomor_tabel]
                    best_ratio = 1.0
                # Exact normalized match
                elif n_target in source_dict:
                    best_match = source_dict[n_target]
                    best_ratio = 1.0
                else:
                    # Fast Fuzzy match using get_close_matches
                    close_matches = difflib.get_close_matches(n_target, source_dict.keys(), n=1, cutoff=0.8)
                    if close_matches:
                        best_match = source_dict[close_matches[0]]
                        best_ratio = difflib.SequenceMatcher(None, n_target, close_matches[0]).ratio()
                
                # If good match found (> 92%), try to map columns
                if best_match and best_ratio > 0.92:
                    target_cols = list(t_target.kolom_set.all())
                    source_cols = list(best_match.kolom_set.all())
                    
                    column_mappings = match_columns(target_cols, source_cols)
                    
                    for c_target in target_cols:
                        mapping = column_mappings.get(c_target.id)
                        if mapping:
                            c_source, best_c_score = mapping
                            
                            # Keep target's year unchanged (fix for year bug)
                            suggested_year = c_target.tahun
                            
                            # Anomaly Check (Distribution difference > 10x)
                            is_anomaly = False
                            avg_t = getattr(c_target, 'avg_val', None)
                            avg_s = getattr(c_source, 'avg_val', None)
                            if avg_t and avg_s and float(avg_s) != 0:
                                ratio = float(avg_t) / float(avg_s)
                                if ratio > 10 or ratio < 0.1:
                                    is_anomaly = True
                            
                            # Only suggest if it's actually different from what target has currently
                            if (c_target.indikator_id != c_source.indikator_id or 
                                c_target.satuan != c_source.satuan or 
                                c_target.tahun != suggested_year):
                                
                                results.append({
                                    'target_col_id': c_target.id,
                                    'target_table_id': t_target.id,
                                    'target_table_name': t_target.judul,
                                    'target_col_name': c_target.indikator.nama,
                                    'target_col_satuan': c_target.satuan,
                                    'target_col_tahun': c_target.tahun,
                                    
                                    'source_table_id': best_match.id,
                                    'source_table_name': best_match.judul,
                                    
                                    'source_ind_id': c_source.indikator_id,
                                    'source_ind_name': c_source.indikator.nama,
                                    'suggested_satuan': c_source.satuan,
                                    'suggested_tahun': suggested_year,
                                    
                                    'is_anomaly': is_anomaly,
                                    'match_score': round(best_c_score * 100)
                                })
                        else:
                            # Target column has no match, include it so user can Quick Edit
                            results.append({
                                'target_col_id': c_target.id,
                                'target_table_id': t_target.id,
                                'target_table_name': t_target.judul,
                                'target_col_name': c_target.indikator.nama,
                                'target_col_satuan': c_target.satuan,
                                'target_col_tahun': c_target.tahun,
                                
                                'source_table_id': best_match.id,
                                'source_table_name': best_match.judul,
                                
                                'source_ind_id': None,
                                'source_ind_name': '',
                                'suggested_satuan': '',
                                'suggested_tahun': '',
                                
                                'is_anomaly': False,
                                'match_score': 0
                            })
            
            return JsonResponse({'matches': results})
            
        elif action == 'sync':
            try:
                data = json.loads(request.body)
                items = data.get('items', [])
                source_pub_id = data.get('source_pub')
                target_pub_id = data.get('target_pub')
                
                with transaction.atomic():
                    # Create a log session
                    sync_log = SyncLog.objects.create(
                        source_publikasi_id=source_pub_id,
                        target_publikasi_id=target_pub_id
                    )
                    
                    for item in items:
                        col = KolomTabel.objects.get(pk=item['target_col_id'])
                        
                        ind_id = item.get('source_ind_id')
                        if item.get('custom_ind_name'):
                            ind, _ = Indikator.objects.get_or_create(nama=item['custom_ind_name'])
                            ind_id = ind.id
                            
                        if not ind_id:
                            ind_id = col.indikator_id
                            
                        # Save old state for undo
                        SyncAction.objects.create(
                            log=sync_log,
                            kolom=col,
                            old_indikator=col.indikator,
                            old_satuan=col.satuan,
                            old_tahun=col.tahun,
                            new_indikator_id=ind_id
                        )
                        
                        col.indikator_id = ind_id
                        col.satuan = item.get('suggested_satuan') or ''
                        suggested_tahun = item.get('suggested_tahun')
                        col.tahun = int(suggested_tahun) if suggested_tahun else None
                        col.save()
                
                return JsonResponse({'success': True, 'synced_count': len(items), 'log_id': sync_log.id})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
                
        elif action == 'undo':
            try:
                log_id = request.POST.get('log_id')
                sync_log = SyncLog.objects.get(pk=log_id)
                
                with transaction.atomic():
                    actions = sync_log.actions.all()
                    count = actions.count()
                    for action_obj in actions:
                        col = action_obj.kolom
                        col.indikator = action_obj.old_indikator
                        col.satuan = action_obj.old_satuan
                        col.tahun = action_obj.old_tahun
                        col.save()
                    
                    sync_log.delete()
                return JsonResponse({'success': True, 'restored_count': count})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
                
        return JsonResponse({'error': 'Invalid action'}, status=400)
