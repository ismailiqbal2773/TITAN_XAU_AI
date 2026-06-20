"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/titan-v2/cover.pdf'
BODY = '/home/z/my-project/scripts/titan-v2/body.pdf'
OUT = '/home/z/my-project/download/TITAN_XAU_AI_Architecture_v2.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Master Architecture v2.0',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 1 v2.0: 20 modules, AI stack, 7 diagrams, 6 NFRs, Champion/Challenger, validation, licensing, roadmap, readiness',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, architecture, institutional, AI trading, 20 modules, Champion/Challenger, NFRs, validation',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
