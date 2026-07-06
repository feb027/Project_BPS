from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Audit database for time-series readiness'

    def add_arguments(self, parser):
        parser.add_argument('--query', type=str, default='', help='Search term for data')
        parser.add_argument('--wilayah', type=str, default='', help='Wilayah name to filter')
        parser.add_argument('--start-year', type=int, default=None, help='Start year')
        parser.add_argument('--end-year', type=int, default=None, help='End year')

    def handle(self, *args, **options):
        self.stdout.write('=== TIME-SERIES READINESS AUDIT ===')
        self.stdout.write(f"Query: {options['query']}")
        self.stdout.write(f"Wilayah: {options['wilayah']}")
        self.stdout.write(f"Year range: {options['start_year']} to {options['end_year']}")
        self.stdout.write('-' * 50)
        
        with connection.cursor() as cursor:
            # Core counts
            self.stdout.write('\n=== CORE COUNTS ===')
            query = """
            SELECT 
                'fakta' AS item, COUNT(*) AS rows 
                FROM data_fakta
            UNION ALL
            SELECT 'publikasi', COUNT(*) 
                FROM katalog_publikasi
            UNION ALL
            SELECT 'tabel', COUNT(*) 
                FROM katalog_tabel
            UNION ALL
            SELECT 'kolom_tabel', COUNT(*) 
                FROM katalog_kolomtabel
            UNION ALL
            SELECT 'indikator', COUNT(*) 
                FROM referensi_indikator
            UNION ALL
            SELECT 'wilayah', COUNT(*) 
                FROM referensi_wilayah
            UNION ALL
            SELECT 'rincian', COUNT(*) 
                FROM referensi_rincian
            ORDER BY 1
            """
            cursor.execute(query)
            for row in cursor.fetchall():
                self.stdout.write(f"{row[0]:<12} {row[1]:>8}")
                
            # Year coverage
            self.stdout.write('\n=== YEAR COVERAGE ===')
            query = """
            WITH effective AS (
                SELECT 
                    COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) AS effective_year
                FROM data_fakta f
                JOIN katalog_kolomtabel k ON k.id = f.kolom_id
                JOIN katalog_tabel t ON t.id = f.tabel_id
                JOIN katalog_bab b ON b.id = t.bab_id
                JOIN katalog_publikasi p ON p.id = b.publikasi_id
            )
            SELECT 
                COUNT(*) AS total,
                COUNT(effective_year) AS effective_tahun_filled,
                MIN(effective_year) AS min_year,
                MAX(effective_year) AS max_year,
                COUNT(DISTINCT effective_year) AS distinct_years
            FROM effective
            """
            cursor.execute(query)
            result = cursor.fetchone()
            self.stdout.write(f"Total: {result[0]}")
            self.stdout.write(f"Effective tahun: {result[1]}")
            self.stdout.write(f"Min year: {result[2]}")
            self.stdout.write(f"Max year: {result[3]}")
            self.stdout.write(f"Distinct years: {result[4]}")
            
            # Specific query analysis
            if options['query'] or options['wilayah']:
                self.stdout.write('\n=== SPECIFIC QUERY ANALYSIS ===')
                params = []
                where_clauses = []
                
                if options['wilayah']:
                    where_clauses.append("w.nama ILIKE %s")
                    params.append(f"%{options['wilayah']}%")
                if options['start_year']:
                    where_clauses.append("COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) >= %s")
                    params.append(options['start_year'])
                if options['end_year']:
                    where_clauses.append("COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) <= %s")
                    params.append(options['end_year'])
                if options['query']:
                    where_clauses.append("LOWER(i.nama) LIKE %s")
                    params.append(f"%{options['query'].lower()}%")
                    
                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
                
                query = f"""
                SELECT 
                    COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) AS effective_year,
                    i.id AS indikator_id,
                    i.nama AS indikator,
                    w.nama AS wilayah,
                    COUNT(*) AS rows
                FROM data_fakta f
                JOIN referensi_wilayah w ON w.id = f.wilayah_id
                JOIN katalog_kolomtabel k ON k.id = f.kolom_id
                JOIN referensi_indikator i ON i.id = k.indikator_id
                JOIN katalog_tabel t ON t.id = f.tabel_id
                JOIN katalog_bab b ON b.id = t.bab_id
                JOIN katalog_publikasi p ON p.id = b.publikasi_id
                WHERE {where_sql}
                GROUP BY 1, 2, 3, 4
                ORDER BY 1, 2, 3
                """
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    self.stdout.write(f"{row[0]} | {row[1]} | {row[3]} | {row[4]} rows")
                    
            # Duplicate grain check
            self.stdout.write('\n=== DUPLICATE GRAIN CHECK ===')
            query = """
            WITH duplicates AS (
                SELECT 
                    tabel_id, 
                    kolom_id, 
                    wilayah_id, 
                    rincian_id, 
                    tahun, 
                    COUNT(*) AS cnt
                FROM data_fakta
                GROUP BY 1,2,3,4,5
                HAVING COUNT(*) > 1
            )
            SELECT 
                COUNT(*) AS duplicate_groups,
                SUM(cnt) AS rows_in_duplicates,
                MAX(cnt) AS max_dupe_group
            FROM duplicates
            """
            cursor.execute(query)
            dup_result = cursor.fetchone()
            self.stdout.write(f"Duplicate groups: {dup_result[0]}")
            self.stdout.write(f"Rows in duplicates: {dup_result[1]}")
            self.stdout.write(f"Max duplicates in one group: {dup_result[2]}")
            
            # Numeric parsing analysis
            self.stdout.write('\n=== NUMERIC PARSE ANALYSIS ===')
            # Using simpler patterns without regex escaping issues
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE nilai_teks ~ '[0-9]{1,3},[0-9]{3}' AND nilai_num < 1000) AS comma_thousands_small,
                COUNT(*) FILTER (WHERE nilai_teks ~ '[0-9]+[,.][0-9]{2}' AND nilai_num > 1000) AS decimal_large_num
            FROM data_fakta
            """
            cursor.execute(query)
            result = cursor.fetchone()
            self.stdout.write(f"Comma thousands but small numbers: {result[0]}")
            self.stdout.write(f"Decimal but large numbers: {result[1]}")
            
            # Specific query results
            if options['wilayah'] or options['start_year'] or options['end_year']:
                self.stdout.write('\n=== SPECIFIC QUERY RESULTS ===')
                params = []
                where_clauses = []
                
                if options['wilayah']:
                    where_clauses.append("w.nama ILIKE %s")
                    params.append(f"%{options['wilayah']}%")
                if options['start_year']:
                    where_clauses.append("COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) >= %s")
                    params.append(options['start_year'])
                if options['end_year']:
                    where_clauses.append("COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) <= %s")
                    params.append(options['end_year'])
                if options['query']:
                    where_clauses.append("LOWER(i.nama) LIKE %s")
                    params.append(f"%{options['query'].lower()}%")
                    
                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
                
                query = f"""
                SELECT 
                    COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) AS year,
                    i.id AS indikator_id,
                    i.nama AS indikator,
                    w.nama AS wilayah,
                    f.nilai_teks,
                    f.nilai_num,
                    p.judul AS publikasi,
                    t.nomor_tabel,
                    t.judul AS tabel_judul
                FROM data_fakta f
                JOIN referensi_wilayah w ON w.id = f.wilayah_id
                JOIN katalog_kolomtabel k ON k.id = f.kolom_id
                JOIN referensi_indikator i ON i.id = k.indikator_id
                JOIN katalog_tabel t ON t.id = f.tabel_id
                JOIN katalog_bab b ON b.id = t.bab_id
                JOIN katalog_publikasi p ON p.id = b.publikasi_id
                WHERE {where_sql}
                ORDER BY 1, 2, 3
                """
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    self.stdout.write(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[6]}")
                    
        self.stdout.write('\n=== AUDIT COMPLETE ===')