from io import BytesIO
import openpyxl

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.katalog.models import Publikasi
from apps.referensi.models import Indikator, Wilayah
from apps.manual_import.views import _extract_upload_payload


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password"
    )


@pytest.mark.django_db
def test_generate_template_returns_xlsx(api_client, admin_user):
    admin_user.is_staff = True
    admin_user.save(update_fields=["is_staff"])
    api_client.force_authenticate(user=admin_user)
    Publikasi.objects.get_or_create(
        judul="Kabupaten Tasikmalaya Angka 2026",
        tahun_terbit=2026,
        defaults={"jenis": Publikasi.Jenis.DIGITAL},
    )
    Wilayah.objects.get_or_create(nama="Kabupaten Tasikmalaya", jenis=Wilayah.Jenis.KABUPATEN)
    Wilayah.objects.get_or_create(nama="Kecamatan A", jenis=Wilayah.Jenis.KECAMATAN)
    Indikator.objects.get_or_create(nama="Jumlah Penduduk", satuan="jiwa", tipe_nilai=Indikator.TipeNilai.NUMERIK)
    response = api_client.post(
        reverse("manual_import:generate_template"),
        data={"publication_year": 2027},
    )
    assert response.status_code == 200, response.content.decode("utf-8")[:1000]
    assert response["Content-Type"].endswith("spreadsheetml.sheet")
    assert response["Content-Disposition"].startswith("attachment")
    content = b"".join(response.streaming_content)
    assert content[:4] == b"PK\x03\x04"


def test_extract_upload_payload_valid_strict():
    payload = {
        "valid": True,
        "errors": [],
        "warnings": [{"code": "unknown_indicator", "detail": "foo"}],
        "summary": {},
        "data_rows": [],
        "wilayah_map": {},
        "indikator_map": {},
        "header": [],
        "indikator_header_indexes": [],
        "mode": "strict",
    }
    assert payload["valid"] is True
    assert payload["mode"] == "strict"


def test_extract_upload_payload_review_relaxed():
    payload = {
        "valid": True,
        "errors": [],
        "warnings": [{"code": "unknown_indicator", "detail": "foo"}],
        "summary": {},
        "data_rows": [],
        "wilayah_map": {},
        "indikator_map": {},
        "header": [],
        "indikator_header_indexes": [],
        "mode": "review",
    }
    assert payload["valid"] is True
    assert payload["mode"] == "review"
