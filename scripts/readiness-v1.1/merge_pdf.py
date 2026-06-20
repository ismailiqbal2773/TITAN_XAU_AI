"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/readiness-v1.1/cover.pdf'
BODY = '/home/z/my-project/scripts/readiness-v1.1/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Production_Ready_v1.1_REMEDIATION_COMPLETE.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Production Ready v1.1 Remediation Complete',
    '/Author': 'TITAN Quant Research Audit Office',
    '/Subject': 'Module 17 v1.1: 4 CONDITIONAL categories fixed, all 13 now >= 90/100, PRODUCTION READY (spec level)',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, production ready, remediation complete, 92.5/100, spec level certified',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
