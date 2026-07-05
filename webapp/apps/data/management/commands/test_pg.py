from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SELECT pid, state, query, now() - query_start AS duration FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 10;")
            rows = cur.fetchall()
            print(f"Active queries ({len(rows)}):")
            for r in rows:
                print(f"PID: {r[0]}, State: {r[1]}, Duration: {r[3]}")
                print(f"Query: {r[2][:200]}")
                print("-" * 40)
