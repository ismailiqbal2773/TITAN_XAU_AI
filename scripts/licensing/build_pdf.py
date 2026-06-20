"""
TITAN XAU AI — Commercial Licensing Architecture (Module 11)
Body content + PDF builder.
"""
import os, sys, hashlib
sys.path.insert(0, '/home/z/my-project/skills/pdf/scripts')
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, HRFlowable, Image
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

FONT_DIR = '/usr/share/fonts'
pdfmetrics.registerFont(TTFont('FreeSerif', f'{FONT_DIR}/truetype/freefont/FreeSerif.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Bold', f'{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Italic', f'{FONT_DIR}/truetype/freefont/FreeSerifItalic.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-BoldItalic', f'{FONT_DIR}/truetype/freefont/FreeSerifBoldItalic.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC-Bold', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf'))
registerFontFamily('FreeSerif', normal='FreeSerif', bold='FreeSerif-Bold', italic='FreeSerif-Italic', boldItalic='FreeSerif-BoldItalic')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans')
registerFontFamily('NotoSerifSC', normal='NotoSerifSC', bold='NotoSerifSC-Bold')
try:
    from pdf import install_font_fallback; install_font_fallback()
except Exception: pass

HEADER_FILL = colors.HexColor('#14213D'); ACCENT = colors.HexColor('#C8102E')
TEXT_PRIMARY = colors.HexColor('#14213D'); TEXT_MUTED = colors.HexColor('#4A5568')
BORDER = colors.HexColor('#CBD5E1'); SECTION_BG = colors.HexColor('#F8FAFC')
CARD_BG = colors.HexColor('#F1F5F9'); TABLE_STRIPE = colors.HexColor('#F8FAFC')
DIAGRAM_DIR = '/home/z/my-project/scripts/licensing/diagrams/png'

S = {}
S['h1'] = ParagraphStyle('h1', fontName='FreeSerif-Bold', fontSize=20, leading=26, textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10, alignment=TA_LEFT)
S['h2'] = ParagraphStyle('h2', fontName='FreeSerif-Bold', fontSize=14, leading=18, textColor=HEADER_FILL, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
S['h3'] = ParagraphStyle('h3', fontName='FreeSerif-Bold', fontSize=11.5, leading=15, textColor=ACCENT, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT)
S['body'] = ParagraphStyle('body', fontName='FreeSerif', fontSize=10.5, leading=16, textColor=TEXT_PRIMARY, spaceBefore=0, spaceAfter=8, alignment=TA_JUSTIFY)
S['bullet'] = ParagraphStyle('bullet', fontName='FreeSerif', fontSize=10.5, leading=15, textColor=TEXT_PRIMARY, leftIndent=18, bulletIndent=4, spaceBefore=2, spaceAfter=4, alignment=TA_LEFT)
S['code'] = ParagraphStyle('code', fontName='DejaVuSans', fontSize=9, leading=12, textColor=TEXT_PRIMARY, leftIndent=14, rightIndent=14, spaceBefore=6, spaceAfter=8, backColor=SECTION_BG, borderColor=BORDER, borderWidth=0.5, borderPadding=8, alignment=TA_LEFT)
S['caption'] = ParagraphStyle('caption', fontName='FreeSerif-Italic', fontSize=9, leading=12, textColor=TEXT_MUTED, alignment=TA_CENTER, spaceBefore=4, spaceAfter=14)
S['th'] = ParagraphStyle('th', fontName='FreeSerif-Bold', fontSize=9.5, leading=12, textColor=colors.white, alignment=TA_LEFT)
S['td'] = ParagraphStyle('td', fontName='FreeSerif', fontSize=9, leading=12, textColor=TEXT_PRIMARY, alignment=TA_LEFT)

def h1(text, n=None):
    d = f'Chapter {n} — {text}' if n else text
    k = f'h1_{hashlib.md5(d.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{k}"/><b>{d}</b>', S['h1']); p.bookmark_name=k; p.bookmark_level=0; p.bookmark_text=d; p.bookmark_key=k; return p
def h2(t):
    k = f'h2_{hashlib.md5(t.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{k}"/><b>{t}</b>', S['h2']); p.bookmark_name=k; p.bookmark_level=1; p.bookmark_text=t; p.bookmark_key=k; return p
def h3(t): return Paragraph(f'<b>{t}</b>', S['h3'])
def p(t): return Paragraph(t, S['body'])
def bullet(t): return Paragraph(f'• {t}', S['bullet'])
def code(t):
    t = t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>')
    return Paragraph(f'<font name="DejaVuSans">{t}</font>', S['code'])
def caption(t): return Paragraph(t, S['caption'])
def diagram(f, w=170):
    path = os.path.join(DIAGRAM_DIR, f)
    if not os.path.exists(path): return Paragraph(f'<i>[Missing: {f}]</i>', S['caption'])
    tw = w*mm; from PIL import Image as I; pil=I.open(path); a=pil.height/pil.width; th=tw*a
    mh=230*mm
    if th>mh: th=mh; tw=th/a
    img=Image(path, width=tw, height=th); img.hAlign='CENTER'; return img
def table(d, cw=None):
    w=[]
    for i,r in enumerate(d):
        wr=[]
        for c in r:
            if isinstance(c,str): wr.append(Paragraph(c, S['th'] if i==0 else S['td']))
            else: wr.append(c)
        w.append(wr)
    av=170*mm
    if cw is None: n=len(d[0]); cw=[av/n]*n
    else: t=sum(cw); s=av/t; cw=[x*s for x in cw]
    t=Table(w, colWidths=cw, hAlign='CENTER', repeatRows=1)
    sc=[('BACKGROUND',(0,0),(-1,0),HEADER_FILL),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('GRID',(0,0),(-1,-1),0.4,BORDER),('LINEBELOW',(0,0),(-1,0),1.2,HEADER_FILL)]
    for i in range(1,len(d)):
        if i%2==0: sc.append(('BACKGROUND',(0,i),(-1,i),TABLE_STRIPE))
    t.setStyle(TableStyle(sc)); return t

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, f):
        if hasattr(f,'bookmark_name'):
            self.notify('TOCEntry', (getattr(f,'bookmark_level',0), getattr(f,'bookmark_text',''), self.page, getattr(f,'bookmark_key','')))

def hf(c, d):
    c.saveState(); pn=d.page
    if pn<=2: c.restoreState(); return
    c.setStrokeColor(HEADER_FILL); c.setLineWidth(0.6); c.line(20*mm, A4[1]-18*mm, A4[0]-20*mm, A4[1]-18*mm)
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Commercial Licensing Architecture')
    c.setFont('FreeSerif-Bold',8.5); c.setFillColor(ACCENT); c.drawRightString(A4[0]-20*mm, A4[1]-14*mm, 'v1.0  ·  COMMERCIAL')
    c.setStrokeColor(BORDER); c.setLineWidth(0.3); c.line(20*mm, 18*mm, A4[0]-20*mm, 18*mm)
    c.setFont('FreeSerif-Italic',8); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, 12*mm, '© 2026 TITAN Quant Research  ·  Proprietary & Confidential')
    c.setFont('FreeSerif-Bold',9); c.setFillColor(HEADER_FILL); c.drawRightString(A4[0]-20*mm, 12*mm, f'{pn}')
    c.setFillColor(ACCENT); c.circle(A4[0]-25*mm, 14.5*mm, 1.0, fill=1, stroke=0); c.restoreState()

t1=ParagraphStyle('t1',fontName='FreeSerif-Bold',fontSize=11,leading=16,textColor=HEADER_FILL,leftIndent=0,spaceBefore=4)
t2=ParagraphStyle('t2',fontName='FreeSerif',fontSize=10,leading=14,textColor=colors.black,leftIndent=18,spaceBefore=1)

def build_story():
    s=[]
    s.append(Paragraph('<b>Table of Contents</b>', ParagraphStyle('tt',fontName='FreeSerif-Bold',fontSize=22,leading=28,textColor=HEADER_FILL,alignment=TA_LEFT,spaceAfter=18)))
    s.append(HRFlowable(width='100%', thickness=2, color=ACCENT, spaceBefore=0, spaceAfter=18))
    toc=TableOfContents(); toc.levelStyles=[t1,t2]; s.append(toc); s.append(PageBreak())

    s.append(h1('Executive Summary',1))
    s.append(p('The Commercial Licensing Architecture (CLA) is Module 11 of the TITAN XAU AI trading system. It is the system\'s commercial protection layer — a hardware-locked, cryptographically signed, anti-crack licensing framework that ensures only authorized licensees can operate the TITAN trading system. The CLA binds each license to the physical hardware of the licensee\'s VPS via a 3-factor composite fingerprint (CPUID + Motherboard ID + Windows SID), issues RSA-4096 signed JWT license tokens via a SaaS license server, and enforces feature gating, expiry management, and revocation through a combination of client-side validation and server-side heartbeat.'))
    s.append(p('The architecture supports both online activation (HTTPS to license server, ~2 seconds) and offline activation (request code via email, up to 24 hours) for air-gapped deployments. License tokens are cached locally in AES-256 encrypted form, with the encryption key derived from the hardware fingerprint — meaning a stolen license file cannot be used on a different machine. The system enforces a 1-hour heartbeat cycle: every hour, the client sends its hardware fingerprint and current JWT to the server, which responds with OK, RENEW (new JWT), or REVOKE. If the heartbeat fails (network issue), a 7-day grace period allows continued trading with prominent alerts; after 7 days, the system gracefully shuts down (halt new orders, flatten positions, halt).'))
    s.append(p('Three license expiry types are supported: Monthly (Starter tier, 30-day renewal), Quarterly (Pro tier, 90-day renewal), and Yearly (Enterprise tier, 365-day renewal). All renewals are automatic if billing is active; if billing fails, the license enters the 7-day grace period before shutdown. The CLA also implements 5-layer anti-crack defense: code obfuscation (symbol stripping, LTO, Cython compilation, string encryption), tamper detection (SHA-256 binary checksum, IAT verification), anti-debug (IsDebuggerPresent, NtQueryInformationProcess, RDTSC timing), anti-VM (MAC OUI check, CPUID hypervisor bit), and behavioral analytics (geo-IP tracking, multi-IP detection, concurrent session flagging).'))
    s.append(p('The design philosophy is pragmatic: the goal is not to create unbreakable protection (which is impossible for client-side software) but to raise the crack cost above the license price. Each anti-crack layer is independent — cracking one does not bypass the others. The server-side heartbeat is the ultimate backstop: even if all client-side protections are bypassed, the system cannot operate without a valid server-issued JWT, and the server tracks all activations, geo-IPs, and usage patterns to detect and revoke unauthorized use.'))

    s.append(h1('Architecture Overview',2))
    s.append(p('The CLA is organized into 5 layers: hardware fingerprint (3-factor composite), activation engine (online + offline), license server (SaaS, JWT issuance), anti-crack defense (5 layers), and license expiry/enforcement. A 6th layer (audit) records every licensing event.'))
    s.append(diagram('d01_architecture.png',170))
    s.append(caption('Figure 2.1 — CLA architecture: 5 layers + audit, showing hardware fingerprint, activation, server, anti-crack, and enforcement.'))

    s.append(h2('Layer Responsibilities'))
    s.append(h3('L1 — Hardware Fingerprint'))
    s.append(p('Three hardware identifiers are collected and hashed: CPUID (CPU manufacturer + model + stepping via CPUID instruction), Motherboard ID (baseboard serial number via SMBIOS/DMI/WMI), and Windows SID (machine GUID from registry). Each is SHA-256 hashed individually, then combined into a composite fingerprint: SHA-256(CPUID_hash + MB_hash + SID_hash). This composite is unique per physical machine and cannot be changed without replacing physical hardware. Routine hardware changes (adding RAM, replacing a failed disk) do not affect the fingerprint — only CPU, motherboard, or Windows reinstall triggers a re-activation.'))

    s.append(h3('L2 — Activation Engine'))
    s.append(p('Online activation: HTTPS POST to license server with tenant_id + hw_fingerprint. Server validates, issues RSA-4096 signed JWT. Latency: ~2 seconds. Offline activation: client generates a request code (base64-encoded hw_fingerprint + tenant_id), operator emails it to TITAN support, support generates an activation key (offline JWT), operator enters key. Latency: up to 24 hours. Both paths produce the same JWT format.'))

    s.append(h3('L3 — License Server (SaaS)'))
    s.append(p('AWS-hosted SaaS with 3 components: JWT Issuer (RSA-4096 signing, HSM-backed key), TenantManager (CRUD + billing integration, 3 activations/year auto, additional requires support ticket), and RevocationService (revoke → next heartbeat triggers graceful shutdown). The server enforces: max 3 activations per year (hardware changes), 1 concurrent session per tenant (same hw_fp from multiple IPs = flag), and billing status check on every heartbeat.'))

    s.append(h3('L4 — Anti-Crack Defense (5 layers)'))
    s.append(p('Code obfuscation (symbol strip + LTO + Cython + string encryption), tamper detection (SHA-256 checksum + IAT check), anti-debug (IsDebuggerPresent + NtQuery + RDTSC), anti-VM (MAC OUI + CPUID hypervisor), behavioral analytics (geo-IP + multi-IP + concurrent). Each layer is independent — cracking one does not bypass others.'))

    s.append(h3('L5 — License Expiry & Enforcement'))
    s.append(p('ExpiryManager checks JWT expiry on every heartbeat (1h). Three expiry types: Monthly (30 days, Starter), Quarterly (90 days, Pro), Yearly (365 days, Enterprise). 7-day grace period after expiry → graceful shutdown (flatten + halt). FeatureGate enforces tier-based access (Starter/Pro/Enterprise) — a hard boundary that cannot be bypassed by configuration.'))

    s.append(PageBreak())

    s.append(h1('Hardware Lock — 3-Factor Fingerprint',3))
    s.append(p('The hardware lock is the CLA\'s foundation. It binds each license to the physical hardware of the licensee\'s VPS, preventing license sharing and unauthorized copying. Three identifiers are collected, individually hashed, and combined into a composite fingerprint.'))
    s.append(table([
        ['Identifier', 'Source', 'Collection Method', 'Hash', 'Changes When'],
        ['CPUID', 'CPU manufacturer + model + stepping', 'CPUID instruction (EAX/EBX/ECX/EDX)', 'SHA-256 (64 hex)', 'CPU replaced'],
        ['Motherboard ID', 'Baseboard serial number', 'SMBIOS/DMI · WMI Win32_BaseBoard.SerialNumber', 'SHA-256 (64 hex)', 'Motherboard replaced'],
        ['Windows SID', 'Machine GUID', 'Registry: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid', 'SHA-256 (64 hex)', 'Windows reinstalled'],
    ], cw=[18, 28, 30, 14, 14]))
    s.append(Spacer(1, 8))
    s.append(p('Composite fingerprint: SHA-256(CPUID_hash + MB_hash + SID_hash). This 64-character hex string is unique per physical machine and is included in every JWT claim. On every heartbeat, the server verifies that the hw_fingerprint in the JWT matches the one sent by the client — if they differ, the license is invalid.'))
    s.append(p('Activation policy: 3 activations per year are allowed automatically (to accommodate legitimate hardware changes like RAM upgrades or disk replacements). Additional activations require a support ticket and are granted at TITAN\'s discretion. This policy is lenient enough for legitimate users but prevents mass license sharing.'))

    s.append(PageBreak())

    s.append(h1('Activation Workflow',4))
    s.append(p('The activation workflow (Figure 4.1) documents the complete lifecycle: hardware fingerprint → activation (online/offline) → server validation → JWT received → cached → trading enabled → heartbeat (1h) → renew/revoke → grace period → shutdown.'))
    s.append(diagram('d02_activation.png',170))
    s.append(caption('Figure 4.1 — Complete activation workflow: online + offline paths, heartbeat, grace period, expiry types.'))

    s.append(h2('Online Activation'))
    s.append(p('HTTPS POST to https://license.titan.io/v1/activate with payload: {tenant_id, hw_fingerprint}. Server validates tenant, checks billing, checks activation count, issues RSA-4096 signed JWT with claims: {tier, features, max_capital, expiry, hw_fp}. Client receives JWT, encrypts with AES-256 (key derived from hw_fingerprint), caches at /var/lib/titan/license.jwt. Latency: ~2 seconds.'))

    s.append(h2('Offline Activation'))
    s.append(p('For air-gapped deployments (Enterprise tier with on-prem license server): client generates a request code (base64-encoded {tenant_id, hw_fingerprint, timestamp}). Operator emails this code to TITAN support. Support verifies and generates an activation key (offline JWT with same claims, signed with same RSA key). Operator enters key in the client. The key is validated identically to online JWT. Latency: up to 24 hours (manual process).'))

    s.append(h2('Heartbeat Protocol'))
    s.append(code("""Every 1 hour:
  Client → Server: HTTPS POST /v1/heartbeat
    payload: {tenant_id, hw_fingerprint, current_jwt}
  
  Server → Client: one of:
    OK       → continue trading (JWT still valid)
    RENEW    → new JWT (expiry approaching, auto-renew)
    REVOKE   → license revoked (flatten + grace period)
    BLOCK    → billing failed or activation limit exceeded

  If heartbeat fails (network):
    → enter 7-day grace period
    → retry every 15 minutes
    → P2 alert to operator
    → after 7 days: graceful shutdown (flatten + halt)"""))

    s.append(h2('License Expiry Types'))
    s.append(table([
        ['Type', 'Duration', 'Tier', 'Renewal', 'Grace Period', 'Auto-Renew'],
        ['Monthly', '30 days', 'Starter ($12k/yr)', 'Every 30 days', '7 days', 'Yes (if billing OK)'],
        ['Quarterly', '90 days', 'Pro ($48k/yr)', 'Every 90 days', '7 days', 'Yes (if billing OK)'],
        ['Yearly', '365 days', 'Enterprise ($180k/yr)', 'Every 365 days', '7 days', 'Yes (if billing OK)'],
    ], cw=[14, 14, 28, 18, 14, 12]))
    s.append(Spacer(1, 8))

    s.append(PageBreak())

    s.append(h1('Security Design',5))
    s.append(p('The CLA uses a 4-layer cryptographic stack: RSA-4096 for license signing (server-side, HSM-backed), AES-256-GCM for license storage (client-side, key derived from hw_fingerprint), TLS 1.3 with mTLS for transport, and SHA-256 for hardware fingerprinting. Key management follows AWS KMS best practices: private keys never leave the HSM, public keys are embedded in the client binary at build time.'))
    s.append(diagram('d03_security.png',170))
    s.append(caption('Figure 5.1 — Cryptographic stack, key management lifecycle, and security layer summary.'))

    s.append(h2('Key Management'))
    s.append(bullet('RSA signing key pair: Generated in AWS KMS (HSM-backed). Private key never leaves HSM. Public key embedded in client binary at build time. Rotation: annual with 30-day overlap.'))
    s.append(bullet('AES storage key: Derived from hw_fingerprint via PBKDF2 (100k iterations). Never stored on disk. Re-derived on each startup. Unique per machine.'))
    s.append(bullet('mTLS client certificate: Embedded in client binary. Rotation: 90 days. Certificate pinning enforced (no fallback).'))
    s.append(bullet('Hardware fingerprint: Computed at runtime from 3 hardware identifiers. Never stored. Cannot be spoofed without physical hardware replacement.'))

    s.append(PageBreak())

    s.append(h1('Anti-Crack Design',6))
    s.append(p('The CLA deploys 5 independent anti-crack layers. Each layer addresses a different class of attacker and adds independent delay. The goal is not unbreakability (impossible for client-side software) but raising the crack cost above the license price, with each release delaying cracks by 6+ months.'))
    s.append(diagram('d04_anticrack.png',170))
    s.append(caption('Figure 6.1 — 5-layer anti-crack defense: obfuscation, tamper, anti-debug, anti-VM, behavioral.'))

    s.append(h2('Crack Resistance Philosophy'))
    s.append(p('No client-side protection is unbreakable — a determined attacker with sufficient time and resources can always crack client-side software. The CLA\'s goal is pragmatic: raise the cost of cracking above the price of a legitimate license. Each anti-crack layer adds 1-4 weeks of delay for a skilled reverser. Combined, the 5 layers delay a crack by 6+ months per release. Combined with the server-side heartbeat (which cannot be bypassed by client-side cracking), the CLA provides effective protection for a commercial product.'))

    s.append(h2('Server-Side Backstop'))
    s.append(p('The server-side heartbeat is the ultimate backstop. Even if all 5 client-side anti-crack layers are bypassed, the system cannot operate without a valid server-issued JWT. The server tracks: all activations per tenant (max 3/year), geo-IP of every heartbeat (multi-IP flag), concurrent sessions (same hw_fp from multiple IPs), and heartbeat frequency anomalies. Any suspicious behavior is flagged for review, and severe violations trigger automatic revocation.'))

    s.append(h1('License Tier Matrix',7))
    s.append(p('Three tiers gate features, capital ceiling, and support level. The FeatureGate enforces these boundaries at runtime — a hard architectural boundary that cannot be bypassed by configuration.'))
    s.append(diagram('d05_tiers_tests.png',170))
    s.append(caption('Figure 7.1 — 3-tier matrix and validation test cases.'))

    s.append(h1('Validation Tests',8))
    s.append(p('The CLA is validated through 120 tests across 3 categories: unit (70, covering hw fingerprint, JWT verification, activation, expiry, feature gate), integration (30, covering online/offline activation, heartbeat, revocation), and chaos (20, covering tamper, copy, VM clone). All tests are CI-gated.'))
    s.append(p('Critical tests: JWT signature verification (RSA-4096), hw_fingerprint match on every check, expired license → graceful shutdown, revoked license → halt within 1h, tamper detection → halt + audit, feature gate blocks unauthorized features, copied license → hw mismatch → blocked, VM clone → anti-VM or behavioral detection.'))

    s.append(h1('Integration with TITAN Core',9))
    s.append(p('The CLA integrates with every TITAN component as a pre-condition: no module starts until the LicenseValidator has verified the JWT and confirmed the feature gate. The license check runs at startup and on every heartbeat (1h). If the license is invalid, expired, or revoked, the system enters the grace period or shuts down gracefully (flatten + halt). The CLA is the first module loaded and the last module unloaded in the TITAN lifecycle.'))
    s.append(code("""TITAN startup sequence:
  1. LicenseValidator.load() → load cached JWT
  2. Verify RSA signature (embedded public key)
  3. Check expiry → if expired: grace period
  4. Check hw_fingerprint → if mismatch: REJECT
  5. Extract claims (tier, features, max_capital)
  6. FeatureGate.activate(claims) → enable/disable features
  7. Start heartbeat timer (1h)
  8. → If all OK: start trading modules
  9. → If any FAIL: graceful shutdown

TITAN shutdown sequence (on license failure):
  1. Halt new orders (atomic flag)
  2. Cancel pending orders
  3. Flatten all positions
  4. Notify operator (P1 PagerDuty)
  5. Audit log: license_fail + reason
  6. Exit with non-zero status"""))

    return s

def main():
    out = '/home/z/my-project/scripts/licensing/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Commercial Licensing Architecture', author='TITAN Quant Research', subject='Commercial Licensing: hardware lock, activation, anti-crack, expiry, tier management', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
