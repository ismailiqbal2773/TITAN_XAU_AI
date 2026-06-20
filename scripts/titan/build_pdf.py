"""
TITAN XAU AI — Architecture Document PDF Builder
=================================================
Generates the body PDF via ReportLab, with TOC and all chapters.
The cover is generated separately as HTML→PDF via html2poster.js and merged.

Usage:
    python3 /home/z/my-project/scripts/titan/build_pdf.py
"""
import os
import sys
import hashlib
import platform

# Add scripts/titan to path so we can import content modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
# Also add the pdf skill scripts dir for install_font_fallback
sys.path.insert(0, '/home/z/my-project/skills/pdf/scripts')

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, HRFlowable, Image,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ─── Font registration ────────────────────────────────────────────────────
FONT_DIR = '/usr/share/fonts'

def register_fonts():
    """Register all required fonts."""
    # English serif
    pdfmetrics.registerFont(TTFont('FreeSerif', f'{FONT_DIR}/truetype/freefont/FreeSerif.ttf'))
    pdfmetrics.registerFont(TTFont('FreeSerif-Bold', f'{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf'))
    pdfmetrics.registerFont(TTFont('FreeSerif-Italic', f'{FONT_DIR}/truetype/freefont/FreeSerifItalic.ttf'))
    pdfmetrics.registerFont(TTFont('FreeSerif-BoldItalic', f'{FONT_DIR}/truetype/freefont/FreeSerifBoldItalic.ttf'))

    # Sans for headings (Liberation Sans = clean institutional)
    pdfmetrics.registerFont(TTFont('LibSans', f'{FONT_DIR}/truetype/liberation/LiberationSans-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('LibSans-Bold', f'{FONT_DIR}/truetype/liberation/LiberationSans-Bold.ttf'))

    # Mono for code
    pdfmetrics.registerFont(TTFont('DejaVuSans', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono-Bold.ttf'))

    # CJK (in case any strings need fallback)
    pdfmetrics.registerFont(TTFont('NotoSerifSC', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSerifSC-Bold', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf'))

    registerFontFamily('FreeSerif', normal='FreeSerif', bold='FreeSerif-Bold',
                       italic='FreeSerif-Italic', boldItalic='FreeSerif-BoldItalic')
    registerFontFamily('LibSans', normal='LibSans', bold='LibSans-Bold')
    registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans-Bold')
    registerFontFamily('NotoSerifSC', normal='NotoSerifSC', bold='NotoSerifSC-Bold')

register_fonts()

# Install font fallback (handles any rare CJK characters that slip through)
try:
    from pdf import install_font_fallback
    install_font_fallback()
except Exception as e:
    print(f'[warn] install_font_fallback not available: {e}')

# ─── Import content ───────────────────────────────────────────────────────
from content_part1 import build_story as build_part1
from content_part2 import build_part2

# ─── TocDocTemplate ───────────────────────────────────────────────────────
class TocDocTemplate(SimpleDocTemplate):
    """SimpleDocTemplate that captures bookmark info for TOC."""
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

# ─── Header & Footer ──────────────────────────────────────────────────────
PAGE_BG = colors.HexColor('#FFFFFF')
HEADER_FILL = colors.HexColor('#14213D')
ACCENT = colors.HexColor('#C8102E')
TEXT_MUTED = colors.HexColor('#4A5568')
BORDER = colors.HexColor('#CBD5E1')

def header_footer(canvas, doc):
    """Draw header and footer on every page (except cover)."""
    canvas.saveState()
    page_num = doc.page

    # Skip header/footer on TOC pages (pages 1-3)
    if page_num <= 3:
        canvas.restoreState()
        return

    # Header — hairline rule + title (right) + chapter (left)
    canvas.setStrokeColor(HEADER_FILL)
    canvas.setLineWidth(0.6)
    canvas.line(20*mm, A4[1] - 18*mm, A4[0] - 20*mm, A4[1] - 18*mm)

    canvas.setFont('FreeSerif-Italic', 8.5)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(20*mm, A4[1] - 14*mm, 'TITAN XAU AI — Architecture Specification')

    canvas.setFont('FreeSerif-Bold', 8.5)
    canvas.setFillColor(ACCENT)
    canvas.drawRightString(A4[0] - 20*mm, A4[1] - 14*mm, 'v1.0  ·  COMMERCIAL — LICENSEE')

    # Footer — page number (right) + classification (left) + hairline
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(20*mm, 18*mm, A4[0] - 20*mm, 18*mm)

    canvas.setFont('FreeSerif-Italic', 8)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(20*mm, 12*mm, '© 2026 TITAN Quant Research  ·  Proprietary & Confidential')

    canvas.setFont('FreeSerif-Bold', 9)
    canvas.setFillColor(HEADER_FILL)
    canvas.drawRightString(A4[0] - 20*mm, 12*mm, f'{page_num}')

    # Crimson accent dot
    canvas.setFillColor(ACCENT)
    canvas.circle(A4[0] - 25*mm, 14.5*mm, 1.0, fill=1, stroke=0)

    canvas.restoreState()

# ─── TOC styles ───────────────────────────────────────────────────────────
toc_h1_style = ParagraphStyle('TOC_H1', fontName='FreeSerif-Bold', fontSize=11, leading=16,
                               textColor=HEADER_FILL, leftIndent=0, spaceBefore=4)
toc_h2_style = ParagraphStyle('TOC_H2', fontName='FreeSerif', fontSize=10, leading=14,
                               textColor=colors.black, leftIndent=18, spaceBefore=1)

# ─── Build story ──────────────────────────────────────────────────────────
def build_full_story():
    story = []

    # ─── TOC page ────────────────────────────────────────────────────────
    story.append(Paragraph('<b>Table of Contents</b>',
                           ParagraphStyle('TOC_Title', fontName='FreeSerif-Bold', fontSize=22,
                                          leading=28, textColor=HEADER_FILL, alignment=TA_LEFT,
                                          spaceAfter=18)))
    story.append(HRFlowable(width='100%', thickness=2, color=ACCENT, spaceBefore=0, spaceAfter=18))

    toc = TableOfContents()
    toc.levelStyles = [toc_h1_style, toc_h2_style]
    story.append(toc)
    story.append(PageBreak())

    # ─── Body content ────────────────────────────────────────────────────
    story.extend(build_part1())
    story.extend(build_part2())

    return story

# ─── Main ─────────────────────────────────────────────────────────────────
def main():
    output_path = '/home/z/my-project/scripts/titan/body.pdf'

    doc = TocDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=24*mm, bottomMargin=22*mm,
        title='TITAN XAU AI — Architecture Specification',
        author='TITAN Quant Research',
        subject='Institutional-grade AI trading system architecture for XAUUSD',
        creator='TITAN Architecture Workbench',
    )

    story = build_full_story()

    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f'[build] Body PDF written: {output_path}')

    # Report stats
    from pypdf import PdfReader
    r = PdfReader(output_path)
    print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__':
    main()
