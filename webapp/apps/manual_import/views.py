from __future__ import annotations

from typing import Any
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ImportUpload, ImportLog
from .services import load_workbook_from_upload, ManualImportTemplateBuilder
from apps.katalog.models import Publikasi, Bab, Tabel, KolomTabel
from apps.referensi.models import Indikator, Wilayah
from apps.data.models import Fakta


MASTER_YEAR = 2026


def _error(reason: str, code: str = "invalid"):
    return {"valid": False, "errors": [{"code": code, "detail": reason}]}


def _ok():
    return {"valid": True, "errors": [], "warnings": []}


def _read_required_sheet(workbook, name: str):
    try:
        return workbook[name]
    except Exception:
        return None


def _collect_wilayah_master():
    wilayah_qs = list(
        Wilayah.objects.filter(jenis__in=[Wilayah.Jenis.KABUPATEN, Wilayah.Jenis.KECAMATAN])
        .order_by("-dibuat_pada")
    )
    wilayah_map: dict[int, dict[str, Any]] = {}
    for w in wilayah_qs:
        wilayah_map[w.id] = {
            "id": w.id,
            "nama": w.nama,
            "jenis": w.jenis,
        }
    return wilayah_map


def _collect_indikator_master():
    ind_qs = list(
        Indikator.objects.filter(kolom_set__tabel__bab__publikasi__tahun_terbit=MASTER_YEAR)
        .distinct()
        .order_by("nama")
    )
    ind_map: dict[int, dict[str, Any]] = {}
    for ind in ind_qs:
        ind_map[ind.id] = {
            "id": ind.id,
            "nama": ind.nama,
            "satuan": ind.satuan or "",
            "tipe_nilai": ind.tipe_nilai or "",
            "canonical_code": "",
        }
    return ind_map


def _safe_numeric(value: Any):
    if value in (None, "", "-"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".").replace(" ", "")
    try:
        return float(text)
    except Exception:
        return None


def _extract_bab_sheet(bab_nomor: int, ws, indikator_map: dict, wilayah_map: dict):
    """Validate and extract data from one bab data sheet.

    Returns a dict with the same shape as the per-bab portion of the payload:
      {valid, errors, warnings, summary, data_rows, header, indikator_header_indexes}
    """
    errors = []
    warnings_list = []
    header = []
    headers_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])
    for idx, value in enumerate(headers_row, start=1):
        header.append((idx, (value or "").strip()))

    wilayah_header_idx = next(((i, v) for i, v in header if v == "wilayah_id"), None)
    nama_wilayah_header_idx = next(((i, v) for i, v in header if v == "nama_wilayah"), None)
    if not wilayah_header_idx or not nama_wilayah_header_idx:
        return _error("Header harus memiliki 'wilayah_id' dan 'nama_wilayah'.", "invalid_structure")

    indikator_header_indexes = [
        (idx, label) for idx, label in header if label not in ("", "wilayah_id", "nama_wilayah")
    ]
    if not indikator_header_indexes:
        return _error("Tidak ada indikator di header.", "invalid_structure")

    wilayah_set = set(wilayah_map.keys())
    kabupaten_ids = {wid for wid, info in wilayah_map.items() if info["jenis"] == Wilayah.Jenis.KABUPATEN}
    kabupaten_id = next(
        (wid for wid, info in wilayah_map.items()
         if info["nama"] == "Kabupaten Tasikmalaya" and info["jenis"] == Wilayah.Jenis.KABUPATEN),
        None,
    )

    unmatched_labels = []
    for label, idx in [(label, idx) for idx, label in indikator_header_indexes]:
        matched_id = next((i for i, info in indikator_map.items() if info["nama"] == label), None)
        if matched_id is None:
            unmatched_labels.append(label)

    if unmatched_labels:
        # strict mode: unknown indicators are fatal errors
        detail = "Indikator tak dikenali: " + ", ".join(unmatched_labels[:10])
        errors.append({"code": "unknown_indicator", "detail": detail})

    present_wilayah_ids = set()
    seen_wilayah = set()
    data_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        wilayah_value = row[wilayah_header_idx[0] - 1] if wilayah_header_idx and len(row) >= wilayah_header_idx[0] else None
        if wilayah_value in (None, ""):
            continue
        try:
            wilayah_id = int(wilayah_value)
        except Exception:
            errors.append({"code": "invalid_wilayah", "detail": f"wilayah_id tidak valid: {wilayah_value}"})
            continue

        if wilayah_id not in wilayah_set:
            errors.append({"code": "unknown_wilayah", "detail": f"wilayah_id {wilayah_id} tidak ditemukan di master."})
            continue

        if wilayah_id in seen_wilayah:
            if "duplicate_wilayah" not in [e.get("code") for e in errors]:
                errors.append({"code": "duplicate_wilayah", "detail": f"Ada duplikat wilayah_id={wilayah_id} di DATA."})
        seen_wilayah.add(wilayah_id)
        present_wilayah_ids.add(wilayah_id)

        row_data = {
            "wilayah_id": wilayah_id,
            "nama_wilayah": wilayah_map[wilayah_id]["nama"],
            "values": {},
        }
        for idx, label in indikator_header_indexes:
            value = row[idx - 1] if idx <= len(row) else None
            row_data["values"][label] = value
        data_rows.append(row_data)

    if kabupaten_ids and kabupaten_id not in present_wilayah_ids:
        warnings_list.append({"code": "missing_kabupaten", "detail": "Baris Kabupaten Tasikmalaya tidak ditemukan."})

    hard_errors = [e for e in errors if e.get("code") != "unknown_indicator"]

    valid = len(hard_errors) == 0

    return {
        "valid": valid,
        "errors": hard_errors,
        "warnings": warnings_list,
        "summary": {
            "header_columns": len(header),
            "indikator_columns": len(indikator_header_indexes),
            "wilayah_present": len(present_wilayah_ids),
            "wilayah_required": len(kabupaten_ids) + len([w for w in wilayah_map if wilayah_map[w]["jenis"] == Wilayah.Jenis.KECAMATAN]),
            "data_rows": len(data_rows),
            "unmatched_indicator_labels": unmatched_labels,
        },
        "data_rows": data_rows,
        "header": header,
        "indikator_header_indexes": indikator_header_indexes,
    }


def _extract_upload_payload(workbook, publication_year: int):
    ws_wilayah = _read_required_sheet(workbook, "_WILAYAH_")
    ws_indikator = _read_required_sheet(workbook, "_INDIKATOR_")
    ws_meta = _read_required_sheet(workbook, "_METADATA_")

    if not all([ws_wilayah, ws_indikator, ws_meta]):
        return _error("Template Excel tidak lengkap. Butuh _METADATA_, _WILAYAH_, _INDIKATOR_.")

    meta = {}
    for row in ws_meta.iter_rows(min_row=2, values_only=True):
        if row and row[0] is not None:
            meta[row[0]] = str(row[1]).strip() if row[1] is not None else ""

    if meta.get("master_tahun") != str(MASTER_YEAR):
        return _error("Template bukan keluaran master 2026.", "bad_template")

    wilayah_map = _collect_wilayah_master()
    indikator_map = _collect_indikator_master()

    # Find all bab data sheets (any sheet not in the reserved set)
    reserved = {"_METADATA_", "_WILAYAH_", "_INDIKATOR_"}
    bab_sheets = []
    for name in workbook.sheetnames:
        if name not in reserved:
            bab_nomor = ManualImportTemplateBuilder.parse_bab_from_sheet(name)
            if bab_nomor is not None:
                bab_sheets.append((bab_nomor, name, workbook[name]))

    if not bab_sheets:
        return _error("Tidak ada sheet data BAB_xx ditemukan di template.", "invalid_structure")

    all_errors = []
    all_warnings = []
    total_data_rows = 0
    total_indikator = 0
    per_bab: dict[int, dict] = {}

    # Build bab lookup
    bab_lookup = {}
    for b in Bab.objects.filter(
        publikasi__tahun_terbit=MASTER_YEAR
    ).values("nomor", "nama"):
        bab_lookup[b["nomor"]] = b["nama"]

    for bab_nomor, sheet_name, ws in bab_sheets:
        bab_result = _extract_bab_sheet(bab_nomor, ws, indikator_map, wilayah_map)
        bab_result["bab_nama"] = bab_lookup.get(bab_nomor, f"Bab {bab_nomor}")
        bab_result["bab_nomor"] = bab_nomor

        per_bab[bab_nomor] = bab_result
        total_data_rows += bab_result["summary"]["data_rows"]
        total_indikator += bab_result["summary"]["indikator_columns"]
        all_errors.extend(bab_result["errors"])
        all_warnings.extend(bab_result["warnings"])

    hard_errors = [e for e in all_errors]

    report = _ok()
    if hard_errors:
        report["valid"] = False
        report["errors"] = hard_errors
    report["warnings"] = all_warnings

    return {
        "valid": report["valid"],
        "errors": report["errors"],
        "warnings": report["warnings"],
        "summary": {
            "publication_year": publication_year,
            "master_source_year": MASTER_YEAR,
            "babs_count": len(per_bab),
            "total_data_rows": total_data_rows,
            "total_indikator_columns": total_indikator,
        },
        "babs": per_bab,
        "wilayah_map": wilayah_map,
        "indikator_map": indikator_map,
        "mode": "strict",
    }


# ── API Views ──────────────────────────────────────────────────────


@api_view(["POST"])
def generate_template(request):
    try:
        publication_year = int(request.data.get("publication_year", ""))
    except Exception:
        return Response({"error": "publication_year harus angka."}, status=status.HTTP_400_BAD_REQUEST)

    builder = ManualImportTemplateBuilder(publication_year=publication_year)
    workbook = builder.build()

    workbook.save(f"/tmp/manual_import_template_{publication_year}.xlsx")
    with open(f"/tmp/manual_import_template_{publication_year}.xlsx", "rb") as f:
        data = f.read()

    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f"attachment; filename=template_bps_master_{MASTER_YEAR}_{publication_year}.xlsx"
    return response


@api_view(["POST"])
def upload(request):
    upload_file = request.FILES.get("file")
    if not upload_file:
        return Response({"error": "File Excel wajib diupload."}, status=status.HTTP_400_BAD_REQUEST)

    publication_year = request.data.get("publication_year")
    if publication_year is None:
        return Response({"error": "publication_year wajib diisi."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        publication_year = int(publication_year)
    except Exception:
        return Response({"error": "publication_year harus angka."}, status=status.HTTP_400_BAD_REQUEST)

    upload_obj = ImportUpload(
        publication_year=publication_year,
        master_source_year=MASTER_YEAR,
        mode="strict",
        original_filename=upload_file.name,
        file=upload_file,
        status=ImportUpload.Status.UPLOADED,
    )
    upload_obj.save()

    try:
        workbook = load_workbook_from_upload(upload_file)
        payload = _extract_upload_payload(workbook, publication_year)
    except Exception as e:
        upload_obj.status = ImportUpload.Status.REJECTED
        upload_obj.validation_report = {"valid": False, "errors": [{"detail": str(e)}]}
        upload_obj.processed_at = timezone.now()
        upload_obj.save()
        return Response({"upload_id": upload_obj.id, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    upload_obj.validation_report = {
        "valid": payload["valid"],
        "errors": payload["errors"],
        "warnings": payload["warnings"],
        "summary": payload["summary"],
    }
    if payload["valid"]:
        upload_obj.status = ImportUpload.Status.VALIDATED
        # Count total rows across all bab sheets
        total_rows = sum(b["summary"]["data_rows"] for b in payload["babs"].values())
        total_ind = sum(b["summary"]["indikator_columns"] for b in payload["babs"].values())
        upload_obj.preview_summary = {
            "data_rows": total_rows,
            "indikator_count": total_ind,
            "babs_count": len(payload["babs"]),
        }
    else:
        upload_obj.status = ImportUpload.Status.REJECTED
    upload_obj.processed_at = timezone.now()
    upload_obj.save()

    # Build per-bab preview (first 50 rows per bab)
    preview_babs = {}
    for bab_nomor, bab_result in payload["babs"].items():
        preview_babs[str(bab_nomor)] = {
            "bab_nama": bab_result["bab_nama"],
            "summary": bab_result["summary"],
            "valid": bab_result["valid"],
            "errors": bab_result["errors"],
            "warnings": bab_result["warnings"],
            "preview_rows": bab_result["data_rows"][:50],
            "preview_row_count": len(bab_result["data_rows"]),
        }

    preview = {
        "upload_id": str(upload_obj.id),
        "publication_year": publication_year,
        "master_source_year": MASTER_YEAR,
        "mode": "strict",
        "validation": {
            "is_valid": payload["valid"],
            "errors": payload["errors"],
            "warnings": payload["warnings"],
        },
        "summary": payload["summary"],
        "babs": preview_babs,
    }
    return Response({"upload_id": upload_obj.id, "preview": preview}, status=status.HTTP_200_OK)


@api_view(["GET"])
def preview(request, pk: str):
    try:
        upload = ImportUpload.objects.get(pk=pk)
    except ImportUpload.DoesNotExist:
        return Response({"error": "Upload tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

    return Response({"preview": upload.preview_summary, "validation": upload.validation_report})


@api_view(["POST"])
def commit(request, pk: str):
    try:
        upload = ImportUpload.objects.get(pk=pk)
    except ImportUpload.DoesNotExist:
        return Response({"error": "Upload tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

    if upload.status != ImportUpload.Status.VALIDATED:
        return Response({"error": "Upload belum valid atau sudah diproses."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        workbook = load_workbook_from_upload(upload.file)
        payload = _extract_upload_payload(workbook, upload.publication_year)

        if not payload["valid"]:
            return Response({"error": "Data tidak valid.", "validation": payload}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    wilayah_map = payload["wilayah_map"]
    indikator_map = payload["indikator_map"]

    master_publikasi = Publikasi.objects.get(tahun_terbit=MASTER_YEAR)
    from django.db import transaction

    total_faktas_inserted = 0
    total_skipped = 0
    tables_affected = []

    with transaction.atomic():
        for bab_nomor, bab_result in payload["babs"].items():
            if not bab_result["valid"] or not bab_result["data_rows"]:
                continue

            try:
                target_bab = Bab.objects.get(publikasi=master_publikasi, nomor=bab_nomor)
            except Bab.DoesNotExist:
                continue

            # Create one table per bab for imported data
            table_title = f"Imported Manual {upload.publication_year}"
            target_tabel, _ = Tabel.objects.get_or_create(
                bab=target_bab,
                judul=table_title,
                defaults={
                    "tipe_baris": Tabel.TipeBaris.KECAMATAN,
                    "nomor_tabel": f"99.{bab_nomor}",
                    "nama_ringkas": f"IM {upload.publication_year} Bab {bab_nomor}",
                },
            )

            data_rows = bab_result["data_rows"]
            indikator_header_indexes = bab_result["indikator_header_indexes"]

            for row in data_rows:
                wilayah_id = row["wilayah_id"]
                for _, label in indikator_header_indexes:
                    indikator_id = next(
                        (i for i, info in indikator_map.items() if info["nama"] == label),
                        None,
                    )
                    if indikator_id is None:
                        total_skipped += 1
                        continue
                    nilai_num = _safe_numeric(row["values"].get(label))
                    nilai_teks = None if nilai_num is not None else str(row["values"].get(label)).strip()

                    kolom, _ = KolomTabel.objects.get_or_create(
                        tabel=target_tabel,
                        indikator_id=indikator_id,
                        defaults={"urutan": 1},  # placeholder; gets recalculated below
                    )

                    Fakta.objects.create(
                        tabel=target_tabel,
                        wilayah=Wilayah.objects.get(id=wilayah_id),
                        kolom=kolom,
                        tahun=upload.publication_year,
                        nilai_num=nilai_num,
                        nilai_teks=nilai_teks or "-",
                    )
                    total_faktas_inserted += 1

            tables_affected.append({
                "tabel_id": target_tabel.id,
                "judul": target_tabel.judul,
                "bab_nomor": bab_nomor,
                "faktas": len(data_rows) * len(indikator_header_indexes),
            })

        upload.status = ImportUpload.Status.COMMITTED
        upload.processed_at = timezone.now()
        upload.save()

        ImportLog.objects.create(
            upload=upload,
            user=request.user,
            publication_year=upload.publication_year,
            master_source_year=MASTER_YEAR,
            mode="strict",
            status=ImportLog.Status.COMMITTED,
            raw_filename=upload.original_filename,
            validation_report=upload.validation_report,
            preview_summary=upload.preview_summary,
            tables_affected=tables_affected,
            faktas_inserted=total_faktas_inserted,
            committed_at=timezone.now(),
        )

    return Response({
        "status": "committed",
        "faktas_inserted": total_faktas_inserted,
        "skipped_rows": total_skipped,
        "tables_affected": tables_affected,
    })


# ── Page View ───────────────────────────────────────────────────────


def page(request: HttpRequest):
    credential = request.META.get("REMOTE_USER") or ""
    return TemplateResponse(
        request,
        "manual_import/page.html",
        {"api_basic_auth": credential},
    )


def placeholder(request):
    return JsonResponse({"status": "ok", "phase": "phase1_scaffold"})
