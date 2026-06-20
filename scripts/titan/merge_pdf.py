"""
TITAN XAU AI — Merge cover + body PDFs and run QA.
"""
import os
import subprocess
from pypdf import PdfReader, PdfWriter

A4_W, A4_H = 595.28, 841.89  # A4 in points

def normalize_page_to_a4(page):
    """Force-scale every page to exact A4 dimensions."""
    from pypdf.generic import RectangleObject
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    if abs(w - A4_W) > 0.5 or abs(h - A4_H) > 0.5:
        page.scale_to(A4_W, A4_H)
    # Also force-set the mediabox to exact A4 to eliminate sub-point drift
    page.mediabox = RectangleObject([0, 0, A4_W, A4_H])
    if hasattr(page, 'cropbox') and page.cropbox is not None:
        page.cropbox = RectangleObject([0, 0, A4_W, A4_H])
    return page

def merge(cover_pdf, body_pdf, output_pdf):
    writer = PdfWriter()
    # Cover as page 1
    cover_page = PdfReader(cover_pdf).pages[0]
    writer.add_page(normalize_page_to_a4(cover_page))
    # Body pages
    for page in PdfReader(body_pdf).pages:
        writer.add_page(normalize_page_to_a4(page))
    writer.add_metadata({
        '/Title': 'TITAN XAU AI — Architecture Specification',
        '/Author': 'TITAN Quant Research',
        '/Creator': 'TITAN Architecture Workbench',
        '/Subject': 'Institutional-grade AI trading system architecture for XAUUSD',
        '/Keywords': 'XAUUSD, MT5, trading system, architecture, C++, Python, AI',
    })
    with open(output_pdf, 'wb') as f:
        writer.write(f)
    print(f'[merge] Final PDF: {output_pdf}')
    print(f'[merge] Total pages: {len(PdfReader(output_pdf).pages)}')

if __name__ == '__main__':
    base = '/home/z/my-project/scripts/titan'
    merge(
        cover_pdf=os.path.join(base, 'cover.pdf'),
        body_pdf=os.path.join(base, 'body.pdf'),
        output_pdf='/home/z/my-project/download/TITAN_XAU_AI_Architecture_v1.0.pdf',
    )
