"""Merge exec engine cover + body PDFs."""
import os
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

A4_W, A4_H = 595.28, 841.89

def normalize(page):
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    if abs(w - A4_W) > 0.5 or abs(h - A4_H) > 0.5:
        page.scale_to(A4_W, A4_H)
    page.mediabox = RectangleObject([0, 0, A4_W, A4_H])
    if hasattr(page, 'cropbox') and page.cropbox is not None:
        page.cropbox = RectangleObject([0, 0, A4_W, A4_H])
    return page

def main():
    base = '/home/z/my-project/scripts/exec_engine'
    writer = PdfWriter()
    writer.add_page(normalize(PdfReader(os.path.join(base, 'cover.pdf')).pages[0]))
    for page in PdfReader(os.path.join(base, 'body.pdf')).pages:
        writer.add_page(normalize(page))
    writer.add_metadata({
        '/Title': 'TITAN XAU AI — Institutional Execution Engine',
        '/Author': 'TITAN Quant Research',
        '/Creator': 'TITAN Architecture Workbench',
        '/Subject': 'Institutional Execution Engine architecture for ultra-low-latency order execution',
        '/Keywords': 'XAUUSD, MT5, execution engine, low latency, async, tick-based, EQS',
    })
    out = '/home/z/my-project/download/TITAN_Institutional_Execution_Engine_v1.0.pdf'
    with open(out, 'wb') as f:
        writer.write(f)
    print(f'[merge] Final PDF: {out}')
    print(f'[merge] Total pages: {len(PdfReader(out).pages)}')

if __name__ == '__main__':
    main()
