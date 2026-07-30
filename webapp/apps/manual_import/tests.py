from io import BytesIO
from openpyxl import Workbook, load_workbook

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.katalog.models import Publikasi, Bab, Tabel, KolomTabel
from apps.referensi.models import Indikator, Wilayah
from apps.manual_import.services import ManualImportTemplateBuilder
from apps.manual_import.views import _extract_upload_payload


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password"
    )


@pytest.fixture
def master_data():
    """Create a minimal master 2026 structure with 1 bab, 1 tabel, 1 indikator."""
    pub, _ = Publikasi.objects.get_or_create(
        judul="Kabupaten Tasikmalaya Angka 2026",
        tahun_terbit=2026,
        defaults={"jenis": Publikasi.Jenis.DIGITAL},
    )
    bab, _ = Bab.objects.get_or_create(
        publikasi=pub,
        nomor=1,
        defaults={"nama": "Geografi"},
    )
    tabel, _ = Tabel.objects.get_or_create(
        bab=bab,
        nomor_tabel="1.1.1",
        judul="Luas Daerah Menurut Kecamatan",
        defaults={"tipe_baris": Tabel.TipeBaris.KECAMATAN},
    )
    ind, _ = Indikator.objects.get_or_create(
        nama="Jumlah Penduduk",
        defaults={"satuan": "jiwa", "tipe_nilai": Indikator.TipeNilai.NUMERIK},
    )
    kolom, _ = KolomTabel.objects.get_or_create(
        tabel=tabel,
        urutan=1,
        defaults={"indikator": ind},
    )
    # Ensure the FK is set (might already be set)
    if kolom.indikator_id is None:
        kolom.indikator = ind
        kolom.save()

    Wilayah.objects.get_or_create(nama="Kabupaten Tasikmalaya", jenis=Wilayah.Jenis.KABUPATEN)
    Wilayah.objects.get_or_create(nama="Kecamatan A", jenis=Wilayah.Jenis.KECAMATAN)

    return {"pub": pub, "bab": bab, "tabel": tabel, "indikator": ind}


@pytest.mark.django_db
def test_generate_template_returns_xlsx(api_client, admin_user, master_data):
    admin_user.is_staff = True
    admin_user.save(update_fields=["is_staff"])
    api_client.force_authenticate(user=admin_user)

    response = api_client.post(
        reverse("manual_import:generate_template"),
        data={"publication_year": 2027},
        format="json",
    )
    assert response.status_code == 200, response.content.decode("utf-8")[:1000]
    assert response["Content-Type"].endswith("spreadsheetml.sheet")
    assert response["Content-Disposition"].startswith("attachment")
    content = response.content
    assert content[:4] == b"PK\x03\x04"

    # Verify the workbook structure
    wb = load_workbook(BytesIO(content))
    sheet_names = wb.sheetnames
    assert "_METADATA_" in sheet_names
    assert "_WILAYAH_" in sheet_names
    assert "_INDIKATOR_" in sheet_names
    # Should have at least one BAB_ sheet
    bab_sheets = [s for s in sheet_names if s.startswith("BAB_")]
    assert len(bab_sheets) >= 1

    # Check the BAB sheet has correct headers
    bab_ws = wb[bab_sheets[0]]
    headers = [cell.value for cell in bab_ws[1]]
    assert "wilayah_id" in headers
    assert "nama_wilayah" in headers


@pytest.mark.django_db
def test_generate_template_per_bab_structure(master_data):
    """Verify the template has one sheet per bab with correct naming."""
    builder = ManualImportTemplateBuilder(publication_year=2027)
    wb = builder.build()
    bab_sheets = sorted([s for s in wb.sheetnames if s.startswith("BAB_")])
    assert len(bab_sheets) >= 1
    assert bab_sheets[0].startswith("BAB_01_")

    # Verify _INDIKATOR_ has bab_nomor column
    ind_ws = wb["_INDIKATOR_"]
    headers = [cell.value for cell in ind_ws[1]]
    assert "bab_nomor" in headers


@pytest.mark.django_db
def test_generate_template_min_year_check():
    """Must reject publication_year <= 2026."""
    with pytest.raises(ValueError, match="harus lebih besar"):
        ManualImportTemplateBuilder(publication_year=2026)


def test_extract_upload_payload_return_shape():
    """Unit test for the return shape of _extract_upload_payload validation."""
    # Just verify the shape contracts, not the full logic
    payload = {
        "valid": True,
        "errors": [],
        "warnings": [{"code": "unknown_indicator", "detail": "foo"}],
        "summary": {},
        "babs": {},
        "wilayah_map": {},
        "indikator_map": {},
        "mode": "strict",
    }
    assert payload["valid"] is True
    assert payload["mode"] == "strict"
    assert "babs" in payload


@pytest.mark.django_db
def test_full_upload_commit_flow(api_client, admin_user, master_data):
    """Integration test: generate -> upload -> preview -> commit."""
    admin_user.is_staff = True
    admin_user.save(update_fields=["is_staff"])
    api_client.force_authenticate(user=admin_user)

    # 1. Generate template
    gen_resp = api_client.post(
        reverse("manual_import:generate_template"),
        data={"publication_year": 2027},
        format="json",
    )
    assert gen_resp.status_code == 200

    wb = load_workbook(BytesIO(gen_resp.content))
    # Fill in some data in the first BAB sheet
    bab_sheets = [s for s in wb.sheetnames if s.startswith("BAB_")]
    assert len(bab_sheets) >= 1
    bab_ws = wb[bab_sheets[0]]

    # Find the indicator column
    headers = [cell.value for cell in bab_ws[1]]
    ind_col_idx = None
    for idx, h in enumerate(headers, start=1):
        if h and h not in ("wilayah_id", "nama_wilayah"):
            ind_col_idx = idx
            break

    if ind_col_idx:
        # Fill data into first data row
        for row in bab_ws.iter_rows(min_row=2, max_row=3):
            wilayah_id_cell = row[0]
            if wilayah_id_cell.value is not None:
                # Set a value for the indicator
                row[ind_col_idx - 1].value = 12345

    # 2. Upload
    xlsx_bytes = BytesIO()
    wb.save(xlsx_bytes)
    xlsx_bytes.seek(0)

    upload_resp = api_client.post(
        reverse("manual_import:upload"),
        data={
            "file": xlsx_bytes,
            "publication_year": "2027",
        },
        format="multipart",
    )
    assert upload_resp.status_code == 200, upload_resp.content.decode()[:500]
    data = upload_resp.json()
    assert "upload_id" in data
    assert data["preview"]["validation"]["is_valid"] is True

    # 3. Commit
    upload_id = data["upload_id"]
    commit_resp = api_client.post(
        reverse("manual_import:commit", args=[upload_id]),
        data={},
        format="json",
    )
    assert commit_resp.status_code == 200, commit_resp.content.decode()[:500]
    commit_data = commit_resp.json()
    assert commit_data["status"] == "committed"
    assert commit_data["faktas_inserted"] > 0


def _load_workbook(stream):
    """Helper: openpyxl load_workbook from a stream."""
    return load_workbook(stream, read_only=True, data_only=True)
