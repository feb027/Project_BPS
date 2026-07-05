from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute('''
                SELECT relname AS table_name,
                       n_live_tup AS row_count,
                       pg_size_pretty(pg_relation_size(relid)) AS table_size,
                       pg_size_pretty(pg_indexes_size(relid)) AS index_size
                FROM pg_stat_user_tables
                ORDER BY n_live_tup DESC
                LIMIT 10;
            ''')
            rows = cur.fetchall()
            print("Top Tables:")
            for r in rows:
                print(f"{r[0]:<20} | Rows: {r[1]:<8} | Size: {r[2]:<8} | Index: {r[3]}")
