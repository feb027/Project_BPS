from __future__ import annotations

import uuid
from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from apps.katalog.models import Publikasi, Bab, Tabel, KolomTabel
from apps.referensi.models import Indikator, Wilayah
from apps.data.models import CanonicalIndicator


def load_workbook_from_upload(upload_file) -> Any:
    if hasattr(upload_file, "seek"):
        upload_file.seek(0)
    return Workbook(upload_file, read_only=True, data_only=True)


class ManualImportTemplateBuilder:
    MASTER_YEAR = 2026

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

        ws_indikator = wb.create_sheet("_INDIKATOR_")
        self._build_indikator_reference(ws_indikator)

        ws_data = wb.create_sheet("DATA")
        self._build_data_sheet(ws_data, ws_wilayah, ws_indikator)

        self._lock_template(wb)
        return wb

    def _build_metadata(self, ws) -> None:
        ws.append(["key", "value"])
        rows = [
            ("master_tahun", str(self.MASTER_YEAR)),
            ("template_version", "1.0"),
            ("publication_year", str(self.publication_year)),
            ("generated_at", datetime.utcnow().isoformat()),
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
            Wilayah.objects.filter(jenis__in=[Wilayah.Jenis.KABUPATEN, Wilayah.Jenis.KECAMATAN])
            .order_by("-created_at")
        )
        wilayah_map: dict[int, tuple[str, str]] = {}
        if not wilayah_qs:
            raise ValueError("Data wilayah master 2026 belum diisi.")
        for idx, w in enumerate(wilayah_qs, start=1):
            wilayah_map[w.id] = (w.nama, w.jenis)
            ws.append([w.id, w.nama, w.jenis])
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 32
        ws.column_dimensions["C"].width = 16
        ws.protection.sheet = True
        return wilayah_map

    def _build_indikator_reference(self, ws) -> None:
        ws.append(["indikator_id", "canonical_code", "nama", "satuan", "tipe_nilai"])
        indikator_qs = list(
            Indikator.objects.filter(
                kolomtabel__tabel__bab__publikasi=self.master_publikasi,
            )
            .distinct()
            .select_related("canonical_indicator")
            .order_by("canonical_indicator__code", "nama")
        )
        if not indikator_qs:
            raise ValueError("Indikator master 2026 belum tersedia.")
        for ind in indikator_qs:
            canonical = getattr(ind, "canonical_indicator", None)
            ws.append(
                [
                    ind.id,
                    getattr(canonical, "code", "") or "",
                    ind.nama,
                    ind.satuan or "",
                    ind.tipe_nilai or "",
                ]
            )
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 24
        ws.column_dimensions["C"].width = 40
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 14
        ws.protection.sheet = True

    def _build_data_sheet(
        self,
        ws,
        ws_wilayah: Any,
        ws_indikator: Any,
    ) -> None:
        headers = ["wilayah_id", "nama_wilayah"]
        for col_idx in range(3, ws_indikator.max_column + 1):
            headers.append(ws_indikator.cell(row=1, column=col_idx).value or f"kol_{col_idx}")
        ws.append(headers)

        wilayah_ids: list[int] = []
        for row_idx in range(2, ws_wilayah.max_row + 1):
            cell = ws_wilayah.cell(row=row_idx, column=1).value
            if isinstance(cell, int):
                wilayah_ids.append(cell)

        wilayah_lookup = {
            w.id: w.nama for w in Wilayah.objects.filter(id__in=wilayah_ids)
        }
        indikator_ids: list[int] = []
        for row_idx in range(2, ws_indikator.max_row + 1):
            cell = ws_indikator.cell(row=row_idx, column=1).value
            if isinstance(cell, int):
                indikator_ids.append(cell)

        for idx, wilayah_id in enumerate(wilayah_ids, start=2):
            ws.cell(row=idx, column=1, value=wilayah_id)
            ws.cell(row=idx, column=2, value=wilayah_lookup.get(wilayah_id))

        data_validation = DataValidation(
            type="list",
            formula1="=_WILAYAH_!$A$2:$A$40",
            allow_blank=False,
            showErrorMessage=True,
            errorTitle="Wilayah tidak valid",
            error="Pilih wilayah_id dari daftar master.",
        )
        ws.add_data_validation(data_validation)
        data_validation.add(f"A2:A{1 + len(wilayah_ids)}")

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
