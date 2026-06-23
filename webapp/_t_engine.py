import sys, os
sys.path.insert(0, r"c:\projects\Project_BPS\webapp")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"

# Load dotenv manual
from dotenv import load_dotenv
load_dotenv(r"c:\projects\Project_BPS\webapp\.env")

import django
django.setup()
from apps.ekstraksi.engine import detect_headers, col_edges, clean_page
import pdfplumber

pdf = pdfplumber.open(r"..\kabupaten-tasikmalaya-dalam-angka-2026.pdf")
for pno in [46, 47, 58, 61, 79, 85, 97]:
    try:
        p = pdf.pages[pno - 1]
        cp = clean_page(p)
        edges = col_edges(cp)
        if edges:
            h = detect_headers(p, edges)
            names = [(x["nama"] if isinstance(x, dict) else str(x)) for x in (h or [])[:4]]
            print("p" + str(pno) + ": OK  " + str(names))
        else:
            print("p" + str(pno) + ": no edges")
    except Exception as e:
        print("p" + str(pno) + ": ERROR " + type(e).__name__ + ": " + str(e))
print("DONE")
