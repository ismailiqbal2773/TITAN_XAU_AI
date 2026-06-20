"""Merge cover.pdf + body.pdf -> final download PDF."""
from pypdf import PdfWriter, PdfReader
import os, shutil

COVER = '/home/z/my-project/scripts/validator/cover.pdf'
BODY = '/home/z/my-project/scripts/validator/body.pdf'
OUT = '/home/z/my-project/download/TITAN_Validator_Specification_v1.0.pdf'

writer = PdfWriter()
for src in [COVER, BODY]:
    reader = PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)

writer.add_metadata({
    '/Title': 'TITAN XAU AI — validator.py Specification',
    '/Author': 'TITAN Quant Research',
    '/Subject': 'Module 12: Validation framework — 8 suites, 144 checks, scoring, certification workflow',
    '/Creator': 'TITAN Architecture Workbench',
    '/Keywords': 'TITAN, XAUUSD, validator, certification, automated checks, risk, AI, execution, licensing',
})

with open(OUT, 'wb') as f:
    writer.write(f)

size = os.path.getsize(OUT) / 1024
pages = len(PdfReader(OUT).pages)
print(f'[merge] Final PDF: {OUT}')
print(f'[merge] Pages: {pages}  ·  Size: {size:.1f} KB')
