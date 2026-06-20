"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/wfa/cover.pdf'
BODY = '/home/z/my-project/scripts/wfa/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Walk_Forward_Testing_Framework_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Walk-Forward Testing Framework',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 14: Train/Validate/Test/Roll-Forward methodology, WFE scoring, pass criteria, reporting',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, walk-forward, WFE, overfitting, out-of-sample, validation, certification',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
