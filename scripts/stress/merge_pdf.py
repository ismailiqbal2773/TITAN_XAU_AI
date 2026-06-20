"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/stress/cover.pdf'
BODY = '/home/z/my-project/scripts/stress/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Stress_Testing_Framework_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Stress Testing Framework',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 16: 6 stress scenarios, recovery logic, failure logic, certification criteria',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, stress testing, flash crash, recovery, kill-switch, certification',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
