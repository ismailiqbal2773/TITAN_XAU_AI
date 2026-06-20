"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os

COVER = '/home/z/my-project/scripts/weighting/cover.pdf'
BODY = '/home/z/my-project/scripts/weighting/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Live_Intelligent_Model_Weighting_Engine_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — Live Intelligent Model Weighting Engine',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 19: Dynamic model weighting, 4 algorithms, Meta-Bandit, 7 metrics, 95 tests, benchmarks',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, dynamic weighting, Bayesian, MAB, Thompson Sampling, Meta-Bandit, online learning',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
