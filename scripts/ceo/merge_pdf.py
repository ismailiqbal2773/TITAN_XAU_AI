"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/ceo/cover.pdf'
BODY = '/home/z/my-project/scripts/ceo/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Meta_AI_CEO_Supervisor_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Meta AI CEO Supervisor',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 18: Meta AI CEO Supervisor — governance layer, 6 health scores, 8 detectors, 5 control actions, 145 tests',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, CEO, supervisor, governance, meta-AI, health scores, detectors, control actions',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
