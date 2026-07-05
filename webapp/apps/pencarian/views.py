import csv
import json
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import F
from django.contrib.postgres.search import SearchQuery, SearchRank

from apps.data.models import Fakta
from apps.referensi.models import Wilayah

def cari(request):
    """Pencarian lanjutan dengan FTS, filter indikator spesifik, wilayah, dan tahun."""
    q = request.GET.get("q", "").strip()
    indikator_q = request.GET.get("indikator", "").strip()
    wilayah_terpilih = request.GET.get("wilayah", "")
    tahun_terpilih = request.GET.get("tahun", "")
    export = request.GET.get("export", "")

    hasil = []
    list_wilayah = Wilayah.objects.all().order_by("nama")
    
    # Ambil list tahun unik dari Fakta untuk dropdown
    # Untuk sementara kita buat manual agar cepat, atau query distinct.
    # Namun karena data bisa banyak, list_tahun bisa statis atau query yang di-cache.
    # Kita buat statis mundur dari 2026 ke 2010.
    list_tahun = [str(y) for y in range(2026, 2009, -1)]
    
    if q:
        query = SearchQuery(q, search_type="websearch")
        
        # Base query
        qs = Fakta.objects.select_related("tabel", "wilayah", "rincian", "kolom__indikator")
        
        # Filter Pencarian (FTS)
        qs = qs.filter(search_vector=query)
        
        # Filter Indikator (Strict)
        if indikator_q:
            qs = qs.filter(kolom__indikator__nama__icontains=indikator_q)
            
        # Filter Wilayah
        if wilayah_terpilih:
            qs = qs.filter(wilayah_id=wilayah_terpilih)
            
        # Filter Tahun
        if tahun_terpilih:
            qs = qs.filter(tahun=tahun_terpilih)
            
        # Rank query
        qs = qs.annotate(rank=SearchRank(F('search_vector'), query)).order_by("-rank")
        
        if export == "csv":
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="hasil_pencarian_{q}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Nomor Tabel', 'Judul Tabel', 'Indikator', 'Wilayah/Rincian', 'Tahun', 'Nilai Angka', 'Nilai Teks', 'Satuan'])
            
            for f in qs[:5000]: # Limit 5000 untuk export biar tidak timeout
                indikator = getattr(f.kolom.indikator, 'nama', '') if getattr(f, 'kolom', None) else ''
                satuan = getattr(f.kolom, 'satuan', '') if getattr(f, 'kolom', None) else ''
                wilayah = getattr(f.wilayah, 'nama', '') if f.wilayah else (getattr(f.rincian, 'nama', '') if getattr(f, 'rincian', None) else '')
                writer.writerow([getattr(f.tabel, 'nomor_tabel', ''), getattr(f.tabel, 'judul', ''), indikator, wilayah, f.tahun_lengkap, getattr(f, 'nilai_num', ''), getattr(f, 'nilai_teks', ''), satuan])
            return response
            
        # Ambil 100 teratas untuk HTML
        hasil = list(qs[:100])
        
        # Data chart grouped by (Indikator + Wilayah) for Time Series line chart
        series_data = {}
        all_years = set()
        
        for f in reversed(hasil): # Reversed agar urutan ranking tertinggi diutamakan
            if f.nilai_num is not None:
                wilayah_nama = f.wilayah.nama if f.wilayah else (getattr(f.rincian, 'nama', '') if getattr(f, 'rincian', None) else '')
                indikator_nama = f.kolom.indikator.nama if getattr(f, 'kolom', None) and f.kolom.indikator else ''
                tahun = f.tahun_lengkap
                
                if tahun:
                    series_name = f"{indikator_nama[:30]} - {wilayah_nama}"
                    if series_name not in series_data:
                        series_data[series_name] = {}
                    series_data[series_name][tahun] = float(f.nilai_num)
                    all_years.add(tahun)
                    
        # Ambil max 10 series agar chart tidak terlalu penuh
        top_series_names = list(series_data.keys())[:10]
        
        sorted_years = sorted(list(all_years))
        datasets = []
        
        import random
        for series_name in top_series_names:
            data_by_year = series_data[series_name]
            # BPS brand colors base
            r = random.randint(2, 200)
            g = random.randint(100, 220)
            b = random.randint(150, 255)
            
            data_points = []
            for y in sorted_years:
                data_points.append(data_by_year.get(y, None))
                
            datasets.append({
                'label': series_name,
                'data': data_points,
                'borderColor': f'rgb({r}, {g}, {b})',
                'backgroundColor': f'rgba({r}, {g}, {b}, 0.1)',
                'borderWidth': 2,
                'tension': 0.1,
                'spanGaps': True,
                'pointRadius': 4,
                'pointHoverRadius': 6
            })
            
        chart_data_dict = {
            'labels': sorted_years,
            'datasets': datasets
        }

        context = {
            "q": q,
            "indikator_q": indikator_q,
            "hasil": hasil,
            "list_wilayah": list_wilayah,
            "list_tahun": list_tahun,
            "wilayah_terpilih": wilayah_terpilih,
            "tahun_terpilih": tahun_terpilih,
            "chart_data_json": json.dumps(chart_data_dict),
            "chart_title": f"Tren Pencarian: {q}"
        }
    else:
        context = {
            "q": q,
            "indikator_q": indikator_q,
            "hasil": [],
            "list_wilayah": list_wilayah,
            "list_tahun": list_tahun,
            "wilayah_terpilih": wilayah_terpilih,
            "tahun_terpilih": tahun_terpilih,
            "chart_data_json": '{"labels": [], "datasets": []}',
            "chart_title": ""
        }

    return render(request, "pencarian/cari.html", context)
