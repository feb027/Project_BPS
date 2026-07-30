from __future__ import annotations

import uuid
from io import BytesIO
from typing import Any

from django.utils import timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation

from apps.katalog.models import Publikasi, Bab, KolomTabel
from apps.referensi.models import Indikator, Wilayah


def load_workbook_from_upload(upload_file) -> Any:
    if hasattr(upload_file, "seek"):
        upload_file.seek(0)
    return load_workbook(upload_file, read_only=True, data_only=True)


class ManualImportTemplateBuilder:
    MASTER_YEAR = 2026
    SHEET_PREFIX = "BAB_"

    def __init__(self, publication_year: int):
        if publication_year <= self.MASTER_YEAR:
            raise ValueError("publication_year harus lebih besar dari master year 2026")
        self.publication_year = publication_year
        self.master_publikasi = Publikasi.objects.get(tahun_terbit=self.MASTER_YEAR)

    def build(self) -> Workbook:
        wb = Workbook()
        ws_meta = wb.active
        ws_meta.title = "_METADATA_"
        self._build_metadata(ws_meta)

        ws_wilayah = wb.create_sheet("_WILAYAH_")
        self._build_wilayah_reference(ws_wilayah)

        # Build INDICATOR reference sheet — also returns per-bab indicator groups
        ws_indikator = wb.create_sheet("_INDIKATOR_")
        bab_indikator_map = self._build_indikator_reference(ws_indikator)

        # Build one DATA sheet per bab
        babs = list(
            Bab.objects.filter(publikasi=self.master_publikasi).order_by("nomor")
        )
        for bab in babs:
            indikator_ids = bab_indikator_map.get(bab.nomor, [])
            if not indikator_ids:
                continue
            ws = wb.create_sheet(self._sheet_name(bab))
            self._build_bab_data_sheet(ws, bab, indikator_ids)

        self._lock_template(wb)
        return wb

    @staticmethod
    def _sheet_name(bab: Any) -> str:
        """Excel-compatible sheet name (max 31 chars)."""
        raw = f"BAB_{bab.nomor:02d}_{bab.nama}"
        return raw[:31]

    @staticmethod
    def parse_bab_from_sheet(sheet_name: str) -> int | None:
        """Reverse-lookup bab_nomor from a sheet name like 'BAB_01_Geografi'."""
        if not sheet_name.startswith(ManualImportTemplateBuilder.SHEET_PREFIX):
            return None
        try:
            return int(sheet_name[4:6])
        except (ValueError, IndexError):
            return None

    def _build_metadata(self, ws) -> None:
        ws.append(["key", "value"])
        rows = [
            ("master_tahun", str(self.MASTER_YEAR)),
            ("template_version", "1.1"),
            ("publication_year", str(self.publication_year)),
            ("generated_at", timezone.now().isoformat()),
            ("canonical_batch", str(uuid.uuid4())),
        ]
        for row in rows:
            ws.append(row)
        ws["A1"].font = Font(bold=True)
        ws["B1"].font = Font(bold=True)
        ws.column_dimensions["A"].width = 24
        ws.column_dimensions["B"].width = 48
        ws.protection.sheet = True

    def _build_wilayah_reference(self, ws) -> dict[int, tuple[str, str]]:
        ws.append(["wilayah_id", "nama", "jenis"])
        wilayah_qs = list(
            Wilayah.objects.filter(
                jenis__in=[Wilayah.Jenis.KABUPATEN, Wilayah.Jenis.KECAMATAN]
            )
            .order_by("id")
        )
        wilayah_map: dict[int, tuple[str, str]] = {}
        if not wilayah_qs:
            raise ValueError("Data wilayah master 2026 belum diisi.")
        for w in wilayah_qs:
            wilayah_map[w.id] = (w.nama, w.jenis)
            ws.append([w.id, w.nama, w.jenis])
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 32
        ws.column_dimensions["C"].width = 16
        ws.protection.sheet = True
        return wilayah_map

    def _build_indikator_reference(self, ws) -> dict[int, list[int]]:
        """Build _INDIKATOR_ sheet with a bab_nomor column.

        Returns {bab_nomor: [indikator_id, ...]} for building per-bab data sheets.
        """
        ws.append(
            ["indikator_id", "canonical_code", "nama", "satuan", "tipe_nilai", "bab_nomor"]
        )

        indikator_qs = list(
            Indikator.objects.filter(
                kolom_set__tabel__bab__publikasi=self.master_publikasi,
            )
            .distinct()
            .order_by("nama")
        )
        if not indikator_qs:
            raise ValueError("Indikator master 2026 belum tersedia.")

        # Map each indicator → first bab it belongs to
        indikator_bab: dict[int, int] = {}
        for ind in indikator_qs:
            bab_ids = (
                KolomTabel.objects.filter(indikator=ind)
                .values_list("tabel__bab__nomor", flat=True)
                .distinct()
            )
            if bab_ids:
                indikator_bab[ind.id] = list(bab_ids)[0]

        # Build return map: bab_nomor → [indikator_ids]
        bab_map: dict[int, list[int]] = {}
        for ind_id, bab_nomor in indikator_bab.items():
            bab_map.setdefault(bab_nomor, []).append(ind_id)

        for ind in indikator_qs:
            ws.append(
                [
                    ind.id,
                    "",
                    ind.nama,
                    ind.satuan or "",
                    ind.tipe_nilai or "",
                    indikator_bab.get(ind.id, ""),
                ]
            )

        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 24
        ws.column_dimensions["C"].width = 40
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 14
        ws.column_dimensions["F"].width = 12
        ws.protection.sheet = True
        return bab_map

    def _build_bab_data_sheet(
        self,
        ws,
        bab: Any,
        indikator_ids: list[int],
    ) -> None:
        """Build one data sheet for a single bab.

        Columns: wilayah_id, nama_wilayah, indikator_1, indikator_2, …
        """
        indikators = list(
            Indikator.objects.filter(id__in=indikator_ids).order_by("nama")
        )

        # Header row
        headers = ["wilayah_id", "nama_wilayah"]
        for ind in indikators:
            headers.append(ind.nama)
        ws.append(headers)

        # Pre-fill wilayah rows
        wilayah_ids = list(
            Wilayah.objects.filter(
                jenis__in=[Wilayah.Jenis.KABUPATEN, Wilayah.Jenis.KECAMATAN]
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        wilayah_lookup = {
            w.id: w.nama
            for w in Wilayah.objects.filter(id__in=wilayah_ids)
        }

        for idx, wilayah_id in enumerate(wilayah_ids, start=2):
            ws.cell(row=idx, column=1, value=wilayah_id)
            ws.cell(row=idx, column=2, value=wilayah_lookup.get(wilayah_id, ""))

        # Dropdown validation for wilayah_id column
        last_row = 1 + len(wilayah_ids)
        data_validation = DataValidation(
            type="list",
            formula1=f"=_WILAYAH_!$A$2:$A${last_row}",
            allow_blank=False,
            showErrorMessage=True,
            errorTitle="Wilayah tidak valid",
            error="Pilih wilayah_id dari daftar master.",
        )
        ws.add_data_validation(data_validation)
        data_validation.add(f"A2:A{last_row}")

        # Style header row
        header_fill = PatternFill("solid", fgColor="D9E6F2")
        for cell in ws[1]:
            if cell.value:
                cell.font = Font(bold=True)
                cell.fill = header_fill
                cell.protection = Protection(locked=True)

        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 32
        ws.freeze_panes = "A2"

    def _lock_template(self, wb: Workbook) -> None:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.protection.locked is None:
                        cell.protection = Protection(locked=False)

    def to_bytes(self) -> bytes:
        wb = self.build()
        stream = BytesIO()
        wb.save(stream)
        return stream.getvalue()
