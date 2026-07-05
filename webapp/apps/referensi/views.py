import os
import json
import datetime
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache

from apps.referensi.models import Indikator, Wilayah, Rincian
from apps.katalog.models import KolomTabel
from apps.data.models import Fakta

class DataCleaningDashboardView(LoginRequiredMixin, View):
    """
    Menampilkan antarmuka untuk melakukan pembersihan (merge) data
    referensi seperti Indikator, Wilayah, dan Rincian.
    """
    def get(self, request):
        tab = request.GET.get('tab', 'indikator')
        search = request.GET.get('q', '')
        
        context = {
            'tab': tab,
            'search': search,
        }
        
        if tab == 'indikator':
            qs = Indikator.objects.annotate(kolom_count=Count('kolom_set')).filter(kolom_count__gt=0).order_by('-kolom_count')
            if search:
                qs = qs.filter(nama__icontains=search)
            items = list(qs[:200])  # limit for performance in UI
            
        elif tab == 'wilayah':
            qs = Wilayah.objects.annotate(fakta_count=Count('fakta_set')).filter(fakta_count__gt=0).order_by('-fakta_count')
            if search:
                qs = qs.filter(nama__icontains=search)
            items = list(qs[:200])
            
        elif tab == 'rincian':
            qs = Rincian.objects.annotate(fakta_count=Count('fakta_set')).filter(fakta_count__gt=0).order_by('-fakta_count')
            if search:
                qs = qs.filter(nama__icontains=search)
            items = list(qs[:200])
        
        context['items'] = items
            
        return render(request, 'referensi/cleaning_dashboard.html', context)


class MergeEntitiesView(LoginRequiredMixin, View):
    """
    API endpoint untuk memproses penggabungan (merge) beberapa entitas kotor ke satu target.
    """
    def _create_backup(self, entity_type, target_id, source_ids, sources_data):
        import os
        from django.conf import settings
        # Pastikan folder backup ada
        backup_dir = os.path.join(settings.BASE_DIR, 'backups', 'merge_logs')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"merge_{entity_type}_{timestamp}.json"
        filepath = os.path.join(backup_dir, filename)
        
        backup_data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "entity_type": entity_type,
            "target_id": target_id,
            "source_ids": source_ids,
            "sources_data": sources_data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
        return filepath

    def post(self, request):
        try:
            data = json.loads(request.body)
            entity_type = data.get('type')
            target_id = data.get('target_id')
            source_ids = data.get('source_ids', [])
            
            if not target_id or not source_ids:
                return JsonResponse({'success': False, 'error': 'Target dan sumber (source) harus dipilih.'}, status=400)
                
            # target_id is passed as string from JSON, make sure it's int for comparison
            try:
                target_id = int(target_id)
                source_ids = [int(sid) for sid in source_ids]
            except ValueError:
                return JsonResponse({'success': False, 'error': 'ID harus berupa angka.'}, status=400)
                
            if target_id in source_ids:
                return JsonResponse({'success': False, 'error': 'Target tidak boleh ada di dalam daftar sumber.'}, status=400)
                
            with transaction.atomic():
                if entity_type == 'indikator':
                    sources = Indikator.objects.filter(id__in=source_ids)
                    sources_data = [{"id": s.id, "nama": s.nama, "satuan": s.satuan} for s in sources]
                    
                    # Fetch relationships before updating
                    kolom_data = list(KolomTabel.objects.filter(indikator_id__in=source_ids).values('id', 'indikator_id'))
                    sources_data.append({"_kolom_data": kolom_data})
                    
                    self._create_backup(entity_type, target_id, source_ids, sources_data)
                    
                    updated = KolomTabel.objects.filter(indikator_id__in=source_ids).update(indikator_id=target_id)
                    sources.delete()
                    msg = f"Berhasil menggabungkan indikator. {updated} kolom tabel diperbarui."
                    
                elif entity_type == 'wilayah':
                    sources = Wilayah.objects.filter(id__in=source_ids)
                    sources_data = [{"id": s.id, "nama": s.nama, "jenis": s.jenis} for s in sources]
                    
                    fakta_data = list(Fakta.objects.filter(wilayah_id__in=source_ids).values('id', 'wilayah_id'))
                    sources_data.append({"_fakta_data": fakta_data})
                    
                    self._create_backup(entity_type, target_id, source_ids, sources_data)
                    
                    updated = Fakta.objects.filter(wilayah_id__in=source_ids).update(wilayah_id=target_id)
                    sources.delete()
                    msg = f"Berhasil menggabungkan wilayah. {updated} baris fakta diperbarui."
                    
                elif entity_type == 'rincian':
                    sources = Rincian.objects.filter(id__in=source_ids)
                    sources_data = [{"id": s.id, "nama": s.nama, "kelompok": s.kelompok} for s in sources]
                    
                    fakta_data = list(Fakta.objects.filter(rincian_id__in=source_ids).values('id', 'rincian_id'))
                    sources_data.append({"_fakta_data": fakta_data})
                    
                    self._create_backup(entity_type, target_id, source_ids, sources_data)
                    
                    updated = Fakta.objects.filter(rincian_id__in=source_ids).update(rincian_id=target_id)
                    sources.delete()
                    msg = f"Berhasil menggabungkan rincian. {updated} baris fakta diperbarui."
                    
                else:
                    return JsonResponse({'success': False, 'error': 'Tipe entitas tidak valid.'}, status=400)
            # Invalidate cache after merge
            cache.clear()
                    
            return JsonResponse({'success': True, 'message': msg})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class EntityPreviewAPIView(LoginRequiredMixin, View):
    """
    API endpoint untuk mengambil 5 sampel Fakta terkait sebuah entitas (Indikator/Wilayah/Rincian)
    guna keperluan intip data (preview) di UI sebelum di-merge.
    """
    def get(self, request):
        entity_type = request.GET.get('type')
        entity_id = request.GET.get('id')
        
        if not entity_type or not entity_id:
            return JsonResponse({'error': 'Parameter type dan id wajib diisi.'}, status=400)
            
        try:
            entity_id = int(entity_id)
        except ValueError:
            return JsonResponse({'error': 'ID tidak valid.'}, status=400)
            
        if entity_type == 'indikator':
            tabel_ids = list(KolomTabel.objects.filter(indikator_id=entity_id).order_by().values_list('tabel_id', flat=True).distinct()[:30])
            fakta_filter = {'kolom__indikator_id': entity_id}
        elif entity_type == 'wilayah':
            tabel_ids = list(Fakta.objects.filter(wilayah_id=entity_id).order_by().values_list('tabel_id', flat=True).distinct()[:30])
            fakta_filter = {'wilayah_id': entity_id}
        elif entity_type == 'rincian':
            tabel_ids = list(Fakta.objects.filter(rincian_id=entity_id).order_by().values_list('tabel_id', flat=True).distinct()[:30])
            fakta_filter = {'rincian_id': entity_id}
        else:
            return JsonResponse({'error': 'Tipe entitas tidak valid.'}, status=400)
            
        # Ambil persis 1 sampel fakta untuk setiap tabel yang menggunakannya
        # Ini menjamin kita melihat persebaran tahun dan buku publikasi secara utuh
        results = []
        for tid in tabel_ids:
            f = Fakta.objects.filter(tabel_id=tid, **fakta_filter).select_related('tabel__bab__publikasi').first()
            if not f:
                continue
                
            val = f.nilai_tampil
            if f.flag != Fakta.Flag.ADA:
                val = f.get_flag_display()
                
            pub = f.tabel.bab.publikasi if f.tabel and f.tabel.bab else None
            pub_title = pub.judul if pub else "Tidak diketahui"
            pub_year = pub.tahun_terbit if pub else "-"
            
            results.append({
                'id': f.id,
                'tabel_id': f.tabel.id,
                'tabel_no': f.tabel.nomor_tabel,
                'tabel_judul': f.tabel.judul,
                'publikasi': f"{pub_title} ({pub_year})",
                'tahun_data': f.tahun_lengkap or '-',
                'nilai': val
            })
            
        # Urutkan dari tahun terbaru di level Python
        results.sort(key=lambda x: str(x['tahun_data']), reverse=True)
            
        return JsonResponse({'samples': results})


class MergeHistoryAPIView(LoginRequiredMixin, View):
    def get(self, request):
        import os
        from django.conf import settings
        backup_dir = os.path.join(settings.BASE_DIR, 'backups', 'merge_logs')
        
        if not os.path.exists(backup_dir):
            return JsonResponse({'history': []})
            
        files = os.listdir(backup_dir)
        history = []
        for f in sorted(files, reverse=True):
            if f.endswith('.json'):
                try:
                    with open(os.path.join(backup_dir, f), 'r', encoding='utf-8') as fp:
                        data = json.load(fp)
                        sources_count = len(data.get('source_ids', []))
                        history.append({
                            'filename': f,
                            'timestamp': data.get('timestamp'),
                            'entity_type': data.get('entity_type'),
                            'target_id': data.get('target_id'),
                            'sources_count': sources_count
                        })
                except Exception:
                    pass
        return JsonResponse({'history': history})


class UndoMergeAPIView(LoginRequiredMixin, View):
    def post(self, request):
        import os
        from django.conf import settings
        data = json.loads(request.body)
        filename = data.get('filename')
        
        if not filename:
            return JsonResponse({'success': False, 'error': 'Filename tidak valid.'}, status=400)
            
        filepath = os.path.join(settings.BASE_DIR, 'backups', 'merge_logs', filename)
        if not os.path.exists(filepath):
            return JsonResponse({'success': False, 'error': 'File backup tidak ditemukan.'}, status=404)
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
                
            entity_type = backup_data.get('entity_type')
            sources_data = backup_data.get('sources_data', [])
            
            relation_data = None
            if sources_data and isinstance(sources_data[-1], dict) and ('_kolom_data' in sources_data[-1] or '_fakta_data' in sources_data[-1]):
                relation_data = sources_data.pop()
                
            with transaction.atomic():
                if entity_type == 'indikator':
                    for s in sources_data:
                        Indikator.objects.get_or_create(id=s['id'], defaults={'nama': s['nama'], 'satuan': s.get('satuan')})
                    if relation_data and '_kolom_data' in relation_data:
                        for k in relation_data['_kolom_data']:
                            KolomTabel.objects.filter(id=k['id']).update(indikator_id=k['indikator_id'])
                            
                elif entity_type == 'wilayah':
                    for s in sources_data:
                        Wilayah.objects.get_or_create(id=s['id'], defaults={'nama': s['nama'], 'jenis': s.get('jenis')})
                    if relation_data and '_fakta_data' in relation_data:
                        for k in relation_data['_fakta_data']:
                            Fakta.objects.filter(id=k['id']).update(wilayah_id=k['wilayah_id'])
                            
                elif entity_type == 'rincian':
                    for s in sources_data:
                        Rincian.objects.get_or_create(id=s['id'], defaults={'nama': s['nama'], 'kelompok': s.get('kelompok')})
                    if relation_data and '_fakta_data' in relation_data:
                        for k in relation_data['_fakta_data']:
                            Fakta.objects.filter(id=k['id']).update(rincian_id=k['rincian_id'])
                            
            # Rename file so it can't be undone twice
            os.rename(filepath, filepath + '.restored')
            cache.clear()
            return JsonResponse({'success': True})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class AutoCleanBracketsAPIView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            with transaction.atomic():
                # Cari semua indikator yang punya tanda '[' atau ']'
                kotor = list(Indikator.objects.filter(nama__iregex=r'[\[\]]'))
                merged_count = 0
                for ind in kotor:
                    bersih_nama = ind.nama.replace('[', '').replace(']', '').strip()
                    if bersih_nama == ind.nama:
                        continue
                        
                    # Cari apakah versi bersihnya sudah ada
                    target = Indikator.objects.filter(nama__iexact=bersih_nama).exclude(id=ind.id).first()
                    if target:
                        # Pindahkan datanya
                        KolomTabel.objects.filter(indikator_id=ind.id).update(indikator_id=target.id)
                        ind.delete()
                        merged_count += 1
                        
            cache.clear()
            return JsonResponse({'success': True, 'merged_count': merged_count})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class SmartSuggestionAPIView(LoginRequiredMixin, View):
    def get(self, request):
        import difflib
        
        tab = request.GET.get('tab', 'indikator')
        
        if tab == 'indikator':
            qs = Indikator.objects.all()
        elif tab == 'wilayah':
            qs = Wilayah.objects.all()
        else:
            qs = Rincian.objects.all()
            
        # Ambil maksimal 500 item (bisa diurutkan secara acak atau berdasar ID) agar difflib tidak O(N^2)
        items = list(qs.order_by('-id').values('id', 'nama')[:500])
            
        # Simplistic clustering
        clusters = []
        processed_ids = set()
        
        # Sort by length so shorter names become the 'target'
        items.sort(key=lambda x: len(x['nama']))
        
        for i, item in enumerate(items):
            if item['id'] in processed_ids:
                continue
                
            cluster = [item]
            processed_ids.add(item['id'])
            
            # Cari yang mirip
            for j in range(i+1, len(items)):
                other = items[j]
                if other['id'] in processed_ids:
                    continue
                    
                # Gunakan difflib untuk rasio kemiripan > 0.85
                ratio = difflib.SequenceMatcher(None, item['nama'].lower(), other['nama'].lower()).ratio()
                if ratio > 0.85:
                    cluster.append(other)
                    processed_ids.add(other['id'])
                    
            if len(cluster) > 1:
                clusters.append({
                    'target': cluster[0],
                    'sources': cluster[1:]
                })
                
            if len(clusters) >= 20: # Limit 20 clusters for UI performance
                break
                
        return JsonResponse({'clusters': clusters})
