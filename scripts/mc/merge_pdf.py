"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/mc/cover.pdf'
BODY = '/home/z/my-project/scripts/mc/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Monte_Carlo_Framework_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Monte Carlo Framework',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 15: 10,000 simulations, random trade order, slippage, spread, survival score, pass/fail criteria',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, Monte Carlo, simulation, survival score, risk of ruin, validation',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
