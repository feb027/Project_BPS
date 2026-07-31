from __future__ import annotations

from typing import Any
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.db.models import Max
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from .models import ImportUpload, ImportLog
from .services import load_workbook_from_upload, ManualImportTemplateBuilder
from apps.katalog.models import Publikasi, Bab, Tabel, KolomTabel
from apps.referensi.models import Indikator, Wilayah, Rincian
from apps.data.models import Fakta


MASTER_YEAR = 2026

# Real kecamatan (IDs 1-39) + official kabupaten (ID 40)
_KECAMATAN_IDS = list(range(1, 40))
_KABUPATEN_IDS = [40]


def _error(reason: str, code: str = "invalid"):
    return {"valid": False, "errors": [{"code": code, "detail": reason}], "warnings": []}


def _ok():
    return {"valid": True, "errors": [], "warnings": []}


def _read_required_sheet(workbook, name: str):
    try:
        return workbook[name]
    except Exception:
        return None


def _collect_wilayah_master():
    """Return only the 39 real kecamatan + 1 kabupaten."""
    wilayah_qs = list(
        Wilayah.objects.filter(id__in=_KECAMATAN_IDS + _KABUPATEN_IDS)
        .order_by("id")
    )
    wilayah_map: dict[int, dict[str, Any]] = {}
    for w in wilayah_qs:
        wilayah_map[w.id] = {
            "id": w.id,
            "nama": w.nama,
            "jenis": w.jenis,
        }
    return wilayah_map


def _collect_rincian_master():
    """Return all rincian items as a dict for validation."""
    rincian_qs = list(Rincian.objects.all().order_by("id"))
    return {r.id: {"id": r.id, "nama": r.nama} for r in rincian_qs}


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


def _extract_table_sheet(
    tabel_id: int, ws, indikator_map: dict, wilayah_map: dict, rincian_map: dict,
):
    """Validate and extract data from one per-table data sheet (T_0101_...).

    Returns {valid, errors, warnings, summary, data_rows, header, indikator_header_indexes}
    handling both wilayah-id and rincian-id based rows.
    """
    errors = []
    warnings_list = []
    header = []
    headers_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])
    for idx, value in enumerate(headers_row, start=1):
        header.append((idx, (value or "").strip()))

    # Determine if this is a wilayah-based or rincian-based sheet
    row_id_col = next(((i, v) for i, v in header if v in ("wilayah_id", "rincian_id")), None)
    row_name_col = next(((i, v) for i, v in header if v in ("nama_wilayah", "nama_rincian")), None)
    if not row_id_col or not row_name_col:
        return _error("Header harus memiliki 'wilayah_id'/'rincian_id' dan nama terkait.", "invalid_structure")

    is_rincian_sheet = row_id_col[1] == "rincian_id"

    indikator_header_indexes = [
        (idx, label) for idx, label in header
        if label not in ("", "wilayah_id", "nama_wilayah", "rincian_id", "nama_rincian")
    ]
    if not indikator_header_indexes:
        return _error("Tidak ada indikator di header.", "invalid_structure")

    row_id_set = set(rincian_map.keys()) if is_rincian_sheet else set(wilayah_map.keys())

    unmatched_labels = []
    for _, label in indikator_header_indexes:
        matched_id = next((i for i, info in indikator_map.items() if info["nama"] == label), None)
        if matched_id is None:
            unmatched_labels.append(label)

    if unmatched_labels:
        detail = "Indikator tak dikenali: " + ", ".join(unmatched_labels[:10])
        errors.append({"code": "unknown_indicator", "detail": detail})

    seen_ids = set()
    data_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_value = row[row_id_col[0] - 1] if row_id_col and len(row) >= row_id_col[0] else None
        if row_value in (None, ""):
            continue
        try:
            row_id = int(row_value)
        except Exception:
            errors.append({"code": "invalid_id", "detail": f"ID tidak valid: {row_value}"})
            continue

        if row_id not in row_id_set:
            errors.append({
                "code": "unknown_id",
                "detail": f"{'rincian' if is_rincian_sheet else 'wilayah'}_id {row_id} tidak ditemukan di master.",
            })
            continue

        if row_id in seen_ids:
            if "duplicate_id" not in [e.get("code") for e in errors]:
                errors.append({"code": "duplicate_id", "detail": f"Ada duplikat id={row_id} di DATA."})
        seen_ids.add(row_id)

        row_data: dict[str, Any] = {
            "row_id": row_id,
            "row_name": row[row_name_col[0] - 1] if row_name_col and len(row) >= row_name_col[0] else "",
            "values": {},
            "is_rincian": is_rincian_sheet,
        }
        for idx, label in indikator_header_indexes:
            value = row[idx - 1] if idx <= len(row) else None
            row_data["values"][label] = value
        data_rows.append(row_data)

    hard_errors = [e for e in errors if e.get("code") != "unknown_indicator"]

    return {
        "valid": len(hard_errors) == 0,
        "errors": hard_errors,
        "warnings": warnings_list,
        "summary": {
            "header_columns": len(header),
            "indikator_columns": len(indikator_header_indexes),
            "rows_present": len(seen_ids),
            "data_rows": len(data_rows),
            "unmatched_indicator_labels": unmatched_labels,
        },
        "data_rows": data_rows,
        "header": header,
        "indikator_header_indexes": indikator_header_indexes,
    }


def _extract_upload_payload(workbook, publication_year: int):
    ws_meta = _read_required_sheet(workbook, "_METADATA_")
    ws_wilayah = _read_required_sheet(workbook, "_WILAYAH_")
    ws_rincian = _read_required_sheet(workbook, "_RINCIAN_")
    ws_indikator = _read_required_sheet(workbook, "_INDIKATOR_")

    if not all([ws_meta, ws_wilayah, ws_rincian, ws_indikator]):
        return _error("Template Excel tidak lengkap. Butuh _METADATA_, _WILAYAH_, _RINCIAN_, _INDIKATOR_.")

    meta = {}
    for row in ws_meta.iter_rows(min_row=2, values_only=True):
        if row and row[0] is not None:
            meta[row[0]] = str(row[1]).strip() if row[1] is not None else ""

    if meta.get("master_tahun") != str(MASTER_YEAR):
        return _error("Template bukan keluaran master 2026.", "bad_template")

    wilayah_map = _collect_wilayah_master()
    rincian_map = _collect_rincian_master()
    indikator_map = _collect_indikator_master()

    # Find all T_ data sheets
    reserved = {"_METADATA_", "_WILAYAH_", "_INDIKATOR_", "_RINCIAN_"}
    table_sheets = []
    for name in workbook.sheetnames:
        if name not in reserved:
            table_sheets.append((name, workbook[name]))

    if not table_sheets:
        return _error("Tidak ada sheet data T_xx ditemukan di template.", "invalid_structure")

    # Build a {indikator_name → tabel_id} lookup from the _INDIKATOR_ sheet
    ind_name_to_tabel: dict[str, int] = {}
    for row in ws_indikator.iter_rows(min_row=2, values_only=True):
        if row and row[0] is not None and len(row) >= 5:
            ind_name = str(row[1]).strip() if row[1] else ""
            tabel_id = row[4]
            if ind_name and tabel_id:
                ind_name_to_tabel[ind_name] = int(tabel_id)

    all_errors = []
    all_warnings = []
    total_data_rows = 0
    total_indikator = 0
    per_table: dict[int, dict] = {}

    for sheet_name, ws in table_sheets:
        # Determine tabel_id from the _INDIKATOR_ mapping by matching headers
        headers_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])
        header_labels = {(str(v).strip() if v else "") for v in headers_row}
        # Find tabel_id by matching indicator columns
        matched_tabel_id = None
        for label in header_labels:
            if label and label not in ("", "wilayah_id", "nama_wilayah", "rincian_id", "nama_rincian"):
                tid = ind_name_to_tabel.get(label)
                if tid is not None:
                    matched_tabel_id = tid
                    break

        if matched_tabel_id is None:
            # Try to match by looking at the sheet name pattern
            bab_nomor = ManualImportTemplateBuilder.parse_bab_from_sheet(sheet_name)
            if bab_nomor is not None:
                all_warnings.append({
                    "code": "unmatched_sheet",
                    "detail": f"Sheet '{sheet_name}' tidak bisa dicocokkan dengan tabel. Dilewati.",
                })
            continue

        table_result = _extract_table_sheet(
            matched_tabel_id, ws, indikator_map, wilayah_map, rincian_map
        )
        table_result["tabel_id"] = matched_tabel_id

        per_table.setdefault(matched_tabel_id, table_result)
        total_data_rows += table_result["summary"]["data_rows"]
        total_indikator += table_result["summary"]["indikator_columns"]
        all_errors.extend(table_result["errors"])
        all_warnings.extend(table_result["warnings"])

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
            "tables_count": len(per_table),
            "total_data_rows": total_data_rows,
            "total_indikator_columns": total_indikator,
        },
        "tables": per_table,
        "wilayah_map": wilayah_map,
        "rincian_map": rincian_map,
        "indikator_map": indikator_map,
        "mode": "strict",
    }


# ── API Views ──────────────────────────────────────────────────────


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@csrf_exempt
def generate_template(request):
    try:
        publication_year = int(request.data.get("publication_year", ""))
    except Exception:
        return Response({"error": "publication_year harus angka."}, status=status.HTTP_400_BAD_REQUEST)

    bab_id = request.data.get("bab_id")
    if bab_id is not None:
        try:
            bab_id = int(bab_id)
        except (ValueError, TypeError):
            return Response({"error": "bab_id harus angka."}, status=status.HTTP_400_BAD_REQUEST)

    builder = ManualImportTemplateBuilder(
        publication_year=publication_year,
        bab_id=bab_id,
    )
    workbook = builder.build()

    workbook.save(f"/tmp/manual_import_template_{publication_year}.xlsx")
    with open(f"/tmp/manual_import_template_{publication_year}.xlsx", "rb") as f:
        data = f.read()

    # Build descriptive filename
    bab_label = ""
    if bab_id is not None:
        try:
            bab = Bab.objects.get(pk=bab_id)
            bab_label = f"_bab{bab.nomor}"
        except Bab.DoesNotExist:
            pass

    filename = f"template_bps_master_{MASTER_YEAR}{bab_label}_{publication_year}.xlsx"
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@csrf_exempt
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
        # Count total rows across all table sheets
        total_rows = sum(t["summary"]["data_rows"] for t in payload["tables"].values())
        total_ind = sum(t["summary"]["indikator_columns"] for t in payload["tables"].values())
        upload_obj.preview_summary = {
            "data_rows": total_rows,
            "indikator_count": total_ind,
            "tables_count": len(payload["tables"]),
        }
    else:
        upload_obj.status = ImportUpload.Status.REJECTED
    upload_obj.processed_at = timezone.now()
    upload_obj.save()

    # Build per-table preview (first 50 rows per table)
    preview_tables = {}
    for tabel_id, table_result in payload["tables"].items():
        preview_tables[str(tabel_id)] = {
            "tabel_id": tabel_id,
            "summary": table_result["summary"],
            "valid": table_result["valid"],
            "errors": table_result["errors"],
            "warnings": table_result["warnings"],
            "preview_rows": table_result["data_rows"][:50],
            "preview_row_count": len(table_result["data_rows"]),
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
        "tables": preview_tables,
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
@authentication_classes([])
@permission_classes([])
@csrf_exempt
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
    rincian_map = payload["rincian_map"]
    indikator_map = payload["indikator_map"]

    from django.db import transaction

    total_faktas_inserted = 0
    total_faktas_diperbarui = 0
    total_skipped = 0
    tables_affected = []

    try:
        with transaction.atomic():
            # Find or create publikasi for the target year
            target_publikasi, _ = Publikasi.objects.get_or_create(
                tahun_terbit=upload.publication_year,
                defaults={
                    "judul": f"Kabupaten Tasikmalaya Angka {upload.publication_year}",
                    "jenis": Publikasi.Jenis.DIGITAL,
                },
            )

            for tabel_id, table_result in payload["tables"].items():
                if not table_result["valid"] or not table_result["data_rows"]:
                    continue

                try:
                    master_tabel = Tabel.objects.get(pk=tabel_id)
                except Tabel.DoesNotExist:
                    continue

                # Find or create Bab under target publikasi
                target_bab, _ = Bab.objects.get_or_create(
                    publikasi=target_publikasi,
                    nomor=master_tabel.bab.nomor,
                    defaults={"nama": master_tabel.bab.nama},
                )

                # Create one table per source table (mirroring master)
                target_tabel, _ = Tabel.objects.get_or_create(
                    bab=target_bab,
                    nomor_tabel=master_tabel.nomor_tabel,
                    defaults={
                        "judul": master_tabel.judul,
                        "tipe_baris": master_tabel.tipe_baris,
                        "nama_ringkas": master_tabel.nama_ringkas,
                    },
                )

                data_rows = table_result["data_rows"]
                indikator_header_indexes = table_result["indikator_header_indexes"]

                for row in data_rows:
                    row_id = row["row_id"]
                    is_rincian = row.get("is_rincian", False)

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

                        # Use existing kolom or create with next available urutan
                        existing = KolomTabel.objects.filter(
                            tabel=target_tabel, indikator_id=indikator_id
                        ).first()
                        if existing:
                            kolom = existing
                        else:
                            max_urut = (
                                KolomTabel.objects.filter(tabel=target_tabel)
                                .aggregate(m=Max("urutan"))["m"]
                                or 0
                            )
                            kolom = KolomTabel.objects.create(
                                tabel=target_tabel,
                                indikator_id=indikator_id,
                                urutan=max_urut + 1,
                            )

                        if is_rincian:
                            _, dibuat = Fakta.objects.update_or_create(
                                tabel=target_tabel,
                                kolom=kolom,
                                wilayah=None,
                                rincian=Rincian.objects.get(id=row_id),
                                tahun=upload.publication_year,
                                defaults={
                                    "nilai_num": nilai_num,
                                    "nilai_teks": nilai_teks or "-",
                                    "dibuat_oleh": request.user if request.user.is_authenticated else None,
                                },
                            )
                        else:
                            _, dibuat = Fakta.objects.update_or_create(
                                tabel=target_tabel,
                                kolom=kolom,
                                wilayah=Wilayah.objects.get(id=row_id),
                                rincian=None,
                                tahun=upload.publication_year,
                                defaults={
                                    "nilai_num": nilai_num,
                                    "nilai_teks": nilai_teks or "-",
                                    "dibuat_oleh": request.user if request.user.is_authenticated else None,
                                },
                            )
                        if dibuat:
                            total_faktas_inserted += 1
                        else:
                            total_faktas_diperbarui += 1

                tables_affected.append({
                    "tabel_id": target_tabel.id,
                    "judul": target_tabel.judul,
                    "bab_nomor": master_tabel.bab.nomor,
                    "faktas": len(data_rows) * len(indikator_header_indexes),
                })

            upload.status = ImportUpload.Status.COMMITTED
            upload.processed_at = timezone.now()
            upload.save()

            ImportLog.objects.create(
                upload=upload,
                user=request.user if request.user.is_authenticated else None,
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
            "faktas_diperbarui": total_faktas_diperbarui,
            "skipped_rows": total_skipped,
            "tables_affected": tables_affected,
            "publikasi_id": target_publikasi.id,
        })

    except Exception as e:
        return Response(
            {
                "error": f"Gagal commit ({type(e).__name__}): {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ── Page View ───────────────────────────────────────────────────────


def page(request: HttpRequest):
    credential = request.META.get("REMOTE_USER") or ""
    bab_list = list(
        Bab.objects.filter(publikasi__tahun_terbit=MASTER_YEAR)
        .order_by("nomor")
        .values("id", "nomor", "nama")
    )
    return TemplateResponse(
        request,
        "manual_import/page.html",
        {
            "api_basic_auth": credential,
            "bab_list": bab_list,
        },
    )


def placeholder(request):
    return JsonResponse({"status": "ok", "phase": "phase1_scaffold"})
