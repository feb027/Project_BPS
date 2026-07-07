#!/usr/bin/env python3
"""Merge missing 2018/2019 raw BPS publication tables from a restored staging DB.

This script intentionally does NOT preserve staging primary keys. It remaps natural keys
into production IDs to avoid collisions, then inserts only tables absent from production.

Default mode is dry-run: inserts happen in a transaction and are rolled back.
Use --apply to commit.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

YEARS = (2018, 2019)

# Corrections observed in the laptop dump. These avoid adding obvious OCR/parse junk to
# referensi_wilayah while still preserving the underlying facts.
WILAYAH_NAME_CORRECTIONS = {
    "Cikatom": "Cikatomas",
    "Sodonghlir": "Sodonghilir",
}
# This row label is a fish species in table 5.5.3, not a kecamatan.
WILAYAH_TO_RINCIAN = {
    "Sepat Siam": ("Sepat Siam", ""),
}
YEAR_LABEL_RE = re.compile(r"^(?:19|20)\d{2}$")


@dataclass
class MergeStats:
    inserted: Counter
    mapped_existing: Counter
    corrected: Counter
    selected_staging_table_ids: list[int]

    def __init__(self) -> None:
        self.inserted = Counter()
        self.mapped_existing = Counter()
        self.corrected = Counter()
        self.selected_staging_table_ids = []


def norm_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


class Merger:
    def __init__(self, prod_conn: psycopg.Connection, staging_conn: psycopg.Connection, apply: bool) -> None:
        self.prod = prod_conn
        self.staging = staging_conn
        self.apply = apply
        self.stats = MergeStats()
        self.pub_map: dict[int, int] = {}
        self.bab_map: dict[int, int] = {}
        self.tabel_map: dict[int, int] = {}
        self.kolom_map: dict[int, int] = {}
        self.indikator_map: dict[int, int] = {}
        self.rincian_map: dict[int, int] = {}
        self.wilayah_map: dict[int, int | None] = {}
        self.kabupaten_tasikmalaya_id: int | None = None

    def fetchone_prod(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.prod.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetchall_prod(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.prod.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def fetchone_staging(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.staging.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetchall_staging(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.staging.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def insert_returning_id(self, table: str, values: dict[str, Any]) -> int:
        cols = list(values)
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) RETURNING id"
        with self.prod.cursor() as cur:
            cur.execute(sql, tuple(values[c] for c in cols))
            new_id = cur.fetchone()[0]
        self.stats.inserted[table] += 1
        return int(new_id)

    def run(self) -> None:
        self.ensure_kabupaten()
        self.map_publications()
        self.select_missing_tables()
        self.map_or_insert_babs()
        self.insert_tables_and_columns()
        self.insert_facts()
        self.update_sequences()
        self.print_summary()

    def ensure_kabupaten(self) -> None:
        row = self.fetchone_prod(
            """
            SELECT id FROM referensi_wilayah
            WHERE nama = 'Kabupaten Tasikmalaya' AND jenis = 'kabupaten'
            ORDER BY id LIMIT 1
            """
        )
        if not row:
            raise RuntimeError("Production missing Kabupaten Tasikmalaya wilayah")
        self.kabupaten_tasikmalaya_id = row["id"]

    def map_publications(self) -> None:
        for row in self.fetchall_staging(
            "SELECT * FROM katalog_publikasi WHERE tahun_terbit = ANY(%s) ORDER BY tahun_terbit",
            (list(YEARS),),
        ):
            prod = self.fetchone_prod(
                "SELECT id FROM katalog_publikasi WHERE judul=%s AND tahun_terbit=%s",
                (row["judul"], row["tahun_terbit"]),
            )
            if prod:
                self.pub_map[row["id"]] = prod["id"]
                self.stats.mapped_existing["katalog_publikasi"] += 1
            else:
                new_id = self.insert_returning_id(
                    "katalog_publikasi",
                    {
                        "dibuat_pada": row["dibuat_pada"],
                        "diubah_pada": row["diubah_pada"],
                        "judul": row["judul"],
                        "tahun_terbit": row["tahun_terbit"],
                        "wilayah_cakupan": row["wilayah_cakupan"],
                        "jenis": row["jenis"],
                        "file_pdf": row["file_pdf"],
                        "catatan": row["catatan"],
                    },
                )
                self.pub_map[row["id"]] = new_id

    def prod_table_keys(self) -> set[tuple[int, int, str]]:
        keys: set[tuple[int, int, str]] = set()
        rows = self.fetchall_prod(
            """
            SELECT p.tahun_terbit, b.nomor AS bab_nomor, t.nomor_tabel
            FROM katalog_tabel t
            JOIN katalog_bab b ON b.id=t.bab_id
            JOIN katalog_publikasi p ON p.id=b.publikasi_id
            WHERE p.tahun_terbit = ANY(%s)
            """,
            (list(YEARS),),
        )
        for r in rows:
            keys.add((r["tahun_terbit"], r["bab_nomor"], r["nomor_tabel"]))
        return keys

    def select_missing_tables(self) -> None:
        existing = self.prod_table_keys()
        rows = self.fetchall_staging(
            """
            SELECT t.id, p.tahun_terbit, b.nomor AS bab_nomor, t.nomor_tabel, t.judul
            FROM katalog_tabel t
            JOIN katalog_bab b ON b.id=t.bab_id
            JOIN katalog_publikasi p ON p.id=b.publikasi_id
            WHERE p.tahun_terbit = ANY(%s)
            ORDER BY p.tahun_terbit, b.nomor, t.nomor_tabel, t.id
            """,
            (list(YEARS),),
        )
        self.stats.selected_staging_table_ids = [
            r["id"] for r in rows if (r["tahun_terbit"], r["bab_nomor"], r["nomor_tabel"]) not in existing
        ]
        if not self.stats.selected_staging_table_ids:
            print("No missing staging tables selected; production already has 2018/2019 additions.")

    def map_or_insert_babs(self) -> None:
        if not self.stats.selected_staging_table_ids:
            return
        rows = self.fetchall_staging(
            """
            SELECT DISTINCT b.*
            FROM katalog_bab b
            JOIN katalog_tabel t ON t.bab_id=b.id
            WHERE t.id = ANY(%s)
            ORDER BY b.publikasi_id, b.nomor
            """,
            (self.stats.selected_staging_table_ids,),
        )
        for row in rows:
            prod_pub_id = self.pub_map[row["publikasi_id"]]
            prod = self.fetchone_prod(
                "SELECT id FROM katalog_bab WHERE publikasi_id=%s AND nomor=%s",
                (prod_pub_id, row["nomor"]),
            )
            if prod:
                self.bab_map[row["id"]] = prod["id"]
                self.stats.mapped_existing["katalog_bab"] += 1
            else:
                new_id = self.insert_returning_id(
                    "katalog_bab",
                    {
                        "dibuat_pada": row["dibuat_pada"],
                        "diubah_pada": row["diubah_pada"],
                        "nomor": row["nomor"],
                        "nama": row["nama"],
                        "publikasi_id": prod_pub_id,
                    },
                )
                self.bab_map[row["id"]] = new_id

    def map_or_insert_indikator(self, stg_id: int | None) -> int | None:
        if stg_id is None:
            return None
        if stg_id in self.indikator_map:
            return self.indikator_map[stg_id]
        row = self.fetchone_staging("SELECT * FROM referensi_indikator WHERE id=%s", (stg_id,))
        if not row:
            raise RuntimeError(f"Missing staging indikator {stg_id}")
        prod = self.fetchone_prod("SELECT id FROM referensi_indikator WHERE nama=%s", (row["nama"],))
        if prod:
            self.indikator_map[stg_id] = prod["id"]
            self.stats.mapped_existing["referensi_indikator"] += 1
            return prod["id"]
        new_id = self.insert_returning_id(
            "referensi_indikator",
            {
                "dibuat_pada": row["dibuat_pada"],
                "diubah_pada": row["diubah_pada"],
                "nama": row["nama"],
                "satuan": row["satuan"],
                "tipe_nilai": row["tipe_nilai"],
            },
        )
        self.indikator_map[stg_id] = new_id
        return new_id

    def map_or_insert_rincian_by_key(self, nama: str, kelompok: str = "") -> int:
        prod = self.fetchone_prod("SELECT id FROM referensi_rincian WHERE nama=%s AND kelompok=%s", (nama, kelompok))
        if prod:
            return prod["id"]
        now = datetime.now(timezone.utc)
        return self.insert_returning_id(
            "referensi_rincian",
            {
                "dibuat_pada": now,
                "diubah_pada": now,
                "nama": nama,
                "kelompok": kelompok,
            },
        )

    def map_or_insert_rincian(self, stg_id: int | None) -> int | None:
        if stg_id is None:
            return None
        if stg_id in self.rincian_map:
            return self.rincian_map[stg_id]
        row = self.fetchone_staging("SELECT * FROM referensi_rincian WHERE id=%s", (stg_id,))
        if not row:
            raise RuntimeError(f"Missing staging rincian {stg_id}")
        prod = self.fetchone_prod("SELECT id FROM referensi_rincian WHERE nama=%s AND kelompok=%s", (row["nama"], row["kelompok"]))
        if prod:
            self.rincian_map[stg_id] = prod["id"]
            self.stats.mapped_existing["referensi_rincian"] += 1
            return prod["id"]
        new_id = self.insert_returning_id(
            "referensi_rincian",
            {
                "dibuat_pada": row["dibuat_pada"],
                "diubah_pada": row["diubah_pada"],
                "nama": row["nama"],
                "kelompok": row["kelompok"],
            },
        )
        self.rincian_map[stg_id] = new_id
        return new_id

    def map_wilayah_exact(self, nama: str, jenis: str, parent_id: int | None) -> int:
        prod = self.fetchone_prod(
            """
            SELECT id FROM referensi_wilayah
            WHERE nama=%s AND jenis=%s AND parent_id IS NOT DISTINCT FROM %s
            ORDER BY id LIMIT 1
            """,
            (nama, jenis, parent_id),
        )
        if not prod:
            raise RuntimeError(f"Unmapped wilayah: nama={nama!r} jenis={jenis!r} parent={parent_id!r}")
        return prod["id"]

    def resolve_fact_subject(self, stg_wilayah_id: int | None, stg_rincian_id: int | None, tahun: int | None) -> tuple[int | None, int | None, int | None]:
        wilayah_id: int | None = None
        rincian_id: int | None = self.map_or_insert_rincian(stg_rincian_id)
        new_tahun = tahun
        if stg_wilayah_id is None:
            return None, rincian_id, new_tahun
        row = self.fetchone_staging("SELECT * FROM referensi_wilayah WHERE id=%s", (stg_wilayah_id,))
        if not row:
            raise RuntimeError(f"Missing staging wilayah {stg_wilayah_id}")
        name = norm_text(row["nama"])
        if name in WILAYAH_NAME_CORRECTIONS:
            target = WILAYAH_NAME_CORRECTIONS[name]
            wilayah_id = self.map_wilayah_exact(target, row["jenis"], None)
            self.stats.corrected[f"wilayah:{name}->{target}"] += 1
            return wilayah_id, rincian_id, new_tahun
        if name in WILAYAH_TO_RINCIAN:
            rincian_name, kelompok = WILAYAH_TO_RINCIAN[name]
            rincian_id = self.map_or_insert_rincian_by_key(rincian_name, kelompok)
            self.stats.corrected[f"wilayah_as_rincian:{name}"] += 1
            return None, rincian_id, new_tahun
        if YEAR_LABEL_RE.match(name):
            wilayah_id = self.kabupaten_tasikmalaya_id
            new_tahun = int(name)
            self.stats.corrected[f"wilayah_year_label:{name}"] += 1
            return wilayah_id, rincian_id, new_tahun
        parent_prod_id = None
        if row["parent_id"] is not None:
            parent_prod_id = self.resolve_fact_subject(row["parent_id"], None, None)[0]
        wilayah_id = self.map_wilayah_exact(row["nama"], row["jenis"], parent_prod_id)
        self.stats.mapped_existing["referensi_wilayah"] += 1
        return wilayah_id, rincian_id, new_tahun

    def insert_tables_and_columns(self) -> None:
        if not self.stats.selected_staging_table_ids:
            return
        table_rows = self.fetchall_staging(
            "SELECT * FROM katalog_tabel WHERE id = ANY(%s) ORDER BY id",
            (self.stats.selected_staging_table_ids,),
        )
        for row in table_rows:
            prod_bab_id = self.bab_map[row["bab_id"]]
            existing = self.fetchone_prod(
                "SELECT id FROM katalog_tabel WHERE bab_id=%s AND nomor_tabel=%s",
                (prod_bab_id, row["nomor_tabel"]),
            )
            if existing:
                self.tabel_map[row["id"]] = existing["id"]
                self.stats.mapped_existing["katalog_tabel"] += 1
                continue
            new_id = self.insert_returning_id(
                "katalog_tabel",
                {
                    "dibuat_pada": row["dibuat_pada"],
                    "diubah_pada": row["diubah_pada"],
                    "nomor_tabel": row["nomor_tabel"],
                    "judul": row["judul"],
                    "judul_en": row["judul_en"],
                    "sumber": row["sumber"],
                    "tahun_data": row["tahun_data"],
                    "halaman_awal": row["halaman_awal"],
                    "halaman_akhir": row["halaman_akhir"],
                    "tipe_baris": row["tipe_baris"],
                    "status_verifikasi": row["status_verifikasi"],
                    "bab_id": prod_bab_id,
                    "nama_ringkas": row["nama_ringkas"],
                },
            )
            self.tabel_map[row["id"]] = new_id

        col_rows = self.fetchall_staging(
            "SELECT * FROM katalog_kolomtabel WHERE tabel_id = ANY(%s) ORDER BY tabel_id, urutan, id",
            (self.stats.selected_staging_table_ids,),
        )
        for row in col_rows:
            prod_tabel_id = self.tabel_map[row["tabel_id"]]
            existing = self.fetchone_prod(
                "SELECT id FROM katalog_kolomtabel WHERE tabel_id=%s AND urutan=%s",
                (prod_tabel_id, row["urutan"]),
            )
            if existing:
                self.kolom_map[row["id"]] = existing["id"]
                self.stats.mapped_existing["katalog_kolomtabel"] += 1
                continue
            indikator_id = self.map_or_insert_indikator(row["indikator_id"])
            if indikator_id is None:
                raise RuntimeError(f"Kolom {row['id']} has null indikator")
            new_id = self.insert_returning_id(
                "katalog_kolomtabel",
                {
                    "dibuat_pada": row["dibuat_pada"],
                    "diubah_pada": row["diubah_pada"],
                    "urutan": row["urutan"],
                    "satuan": row["satuan"],
                    "tahun": row["tahun"],
                    "tipe_nilai": row["tipe_nilai"],
                    "indikator_id": indikator_id,
                    "tabel_id": prod_tabel_id,
                },
            )
            self.kolom_map[row["id"]] = new_id

    def insert_facts(self) -> None:
        if not self.stats.selected_staging_table_ids:
            return
        rows = self.fetchall_staging(
            "SELECT * FROM data_fakta WHERE tabel_id = ANY(%s) ORDER BY id",
            (self.stats.selected_staging_table_ids,),
        )
        for row in rows:
            prod_tabel_id = self.tabel_map[row["tabel_id"]]
            prod_kolom_id = self.kolom_map.get(row["kolom_id"]) if row["kolom_id"] is not None else None
            if row["kolom_id"] is not None and prod_kolom_id is None:
                raise RuntimeError(f"Fact {row['id']} unmapped kolom {row['kolom_id']}")
            prod_wilayah_id, prod_rincian_id, prod_tahun = self.resolve_fact_subject(
                row["wilayah_id"], row["rincian_id"], row["tahun"]
            )
            self.insert_returning_id(
                "data_fakta",
                {
                    "dibuat_pada": row["dibuat_pada"],
                    "diubah_pada": row["diubah_pada"],
                    "tahun": prod_tahun,
                    "nilai_num": row["nilai_num"],
                    "nilai_teks": row["nilai_teks"],
                    "flag": row["flag"],
                    "dibuat_oleh_id": None,
                    "kolom_id": prod_kolom_id,
                    "rincian_id": prod_rincian_id,
                    "tabel_id": prod_tabel_id,
                    "wilayah_id": prod_wilayah_id,
                    "search_vector": None,
                },
            )

    def update_sequences(self) -> None:
        seq_tables = [
            "katalog_publikasi",
            "katalog_bab",
            "katalog_tabel",
            "katalog_kolomtabel",
            "referensi_indikator",
            "referensi_rincian",
            "referensi_wilayah",
            "data_fakta",
        ]
        with self.prod.cursor() as cur:
            for table in seq_tables:
                seq = f"{table}_id_seq"
                cur.execute(f"SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {table}), 1), true)", (seq,))

    def print_summary(self) -> None:
        print("\n== merge summary ==")
        print("mode", "APPLY" if self.apply else "DRY-RUN ROLLBACK")
        print("selected_staging_tables", len(self.stats.selected_staging_table_ids))
        print("inserted")
        for key, value in sorted(self.stats.inserted.items()):
            print(f"  {key}: {value}")
        print("mapped_existing")
        for key, value in sorted(self.stats.mapped_existing.items()):
            print(f"  {key}: {value}")
        print("corrections")
        for key, value in sorted(self.stats.corrected.items()):
            print(f"  {key}: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prod-db", default="bps_publikasi")
    parser.add_argument("--staging-db", default="bps_laptop_2018_2019_staging_20260707")
    parser.add_argument("--apply", action="store_true", help="Commit changes. Without this, rollback at end.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with psycopg.connect(f"dbname={args.prod_db}") as prod, psycopg.connect(f"dbname={args.staging_db}") as staging:
        staging.read_only = True
        merger = Merger(prod, staging, args.apply)
        try:
            merger.run()
            if args.apply:
                prod.commit()
                print("COMMITTED")
            else:
                prod.rollback()
                print("ROLLED BACK")
        except Exception:
            prod.rollback()
            raise


if __name__ == "__main__":
    main()
