import os
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
A4_W, A4_H = 595.28, 841.89
def normalize(page):
    box = page.mediabox; w, h = float(box.width), float(box.height)
    if abs(w - A4_W) > 0.5 or abs(h - A4_H) > 0.5: page.scale_to(A4_W, A4_H)
    page.mediabox = RectangleObject([0, 0, A4_W, A4_H])
    if hasattr(page, 'cropbox') and page.cropbox is not None: page.cropbox = RectangleObject([0, 0, A4_W, A4_H])
    return page
base = '/home/z/my-project/scripts/risk_engine'
writer = PdfWriter()
writer.add_page(normalize(PdfReader(os.path.join(base, 'cover.pdf')).pages[0]))
for page in PdfReader(os.path.join(base, 'body.pdf')).pages: writer.add_page(normalize(page))
writer.add_metadata({'/Title': 'TITAN XAU AI — Institutional Risk Engine', '/Author': 'TITAN Quant Research', '/Creator': 'TITAN Architecture Workbench', '/Subject': 'Institutional Risk Engine: 4 modes, 12 controls, kill switch, capital preservation', '/Keywords': 'XAUUSD, risk engine, kill switch, circuit breaker, drawdown, capital preservation'})
out = '/home/z/my-project/download/TITAN_Institutional_Risk_Engine_v1.0.pdf'
with open(out, 'wb') as f: writer.write(f)
print(f'[merge] Final PDF: {out}')
print(f'[merge] Total pages: {len(PdfReader(out).pages)}')
