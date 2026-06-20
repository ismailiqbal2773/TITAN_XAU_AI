"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/backtest/cover.pdf'
BODY = '/home/z/my-project/scripts/backtest/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Institutional_Backtesting_Framework_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Institutional Backtesting Framework',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 13: Tick data, spread, commission, swap, slippage — process, metrics, reporting, failure criteria',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, backtesting, tick data, slippage, commission, swap, spread, metrics, certification',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
