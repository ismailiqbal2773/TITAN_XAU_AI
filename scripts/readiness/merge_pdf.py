"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/readiness/cover.pdf'
BODY = '/home/z/my-project/scripts/readiness/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Production_Readiness_Review_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Production Readiness Review',
    '/Author': 'TITAN Quant Research Audit Office',
    '/Subject': 'Module 17: 13-category audit of 16 modules, 90/100 threshold, 7 critical issues, CONDITIONAL APPROVAL',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, production readiness, audit, code review, security, validation, certification',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
