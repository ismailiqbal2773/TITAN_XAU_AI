const fs=require('fs'),path=require('path');const{imageSize}=require('image-size');const docx=require('docx');
const{Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,PageBreak,ImageRun,Table,TableRow,TableCell,WidthType,BorderStyle,TableOfContents,StyleLevel,Footer,Header,PageNumber,NumberFormat,ShadingType,TabStopType,TabStopPosition,VerticalAlign}=docx;
const C={navy:'14213D',crimson:'C8102E',muted:'4A5568',stripe:'F8FAFC',border:'CBD5E1',text:'14213D'};
const DIR='/home/z/my-project/scripts/licensing/diagrams/png';const OUT='/home/z/my-project/download/TITAN_Commercial_Licensing_Architecture_v1.0.docx';
function p(t,o={}){const r=(Array.isArray(t)?t:[{text:t}]).map(x=>new TextRun({text:x.text,bold:x.bold||o.bold,italics:x.italic||o.italic,color:x.color||o.color||C.text,size:(x.size||o.size||22),font:'Liberation Serif'}));return new Paragraph({children:r,spacing:{after:160,line:312},alignment:o.alignment||AlignmentType.JUSTIFIED})}
function h1(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.navy,size:40,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_1,spacing:{before:480,after:240},pageBreakBefore:true,border:{bottom:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:4}}})}
function h2(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.navy,size:28,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_2,spacing:{before:320,after:160}})}
function h3(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.crimson,size:24,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_3,spacing:{before:240,after:120}})}
function bullet(t){return new Paragraph({children:[new TextRun({text:t,size:22,font:'Liberation Serif',color:C.text})],bullet:{level:0},spacing:{after:80,line:280}})}
function code(t){return new Paragraph({children:[new TextRun({text:t,size:18,font:'DejaVu Sans Mono',color:C.text})],spacing:{before:120,after:200,line:240},shading:{type:ShadingType.CLEAR,color:'auto',fill:C.stripe},border:{left:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:6}},indent:{left:240,right:240}})}
function caption(t){return new Paragraph({children:[new TextRun({text:t,italics:true,size:18,font:'Liberation Serif',color:C.muted})],alignment:AlignmentType.CENTER,spacing:{before:60,after:280}})}
function diagram(f,w=6.5){const fp=path.join(DIR,f);if(!fs.existsSync(fp))return p(`[Missing: ${f}]`,{italic:true,color:C.crimson});const b=fs.readFileSync(fp);const d=imageSize(b);const a=d.height/d.width;const wp=w*96;const hp=wp*a;return new Paragraph({children:[new ImageRun({data:b,transformation:{width:wp,height:hp},type:'png'})],alignment:AlignmentType.CENTER,spacing:{before:200,after:100}})}
function table(h,r){const n=h.length;const w=Array(n).fill(100/n);const td=9000;const hc=h.map((x,i)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:x,bold:true,color:'FFFFFF',size:20,font:'Liberation Serif'})]})],shading:{type:ShadingType.CLEAR,color:'auto',fill:C.navy},width:{size:Math.round(w[i]*td/100),type:WidthType.DXA},margins:{top:80,bottom:80,left:100,right:100},verticalAlign:VerticalAlign.CENTER}));const hr=new TableRow({children:hc,tableHeader:true,cantSplit:true});const dr=r.map((row,ri)=>new TableRow({children:row.map((c,i)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:String(c),size:18,font:'Liberation Serif',color:C.text})],spacing:{line:240}})],shading:ri%2===1?{type:ShadingType.CLEAR,color:'auto',fill:C.stripe}:undefined,width:{size:Math.round(w[i]*td/100),type:WidthType.DXA},margins:{top:60,bottom:60,left:100,right:100},verticalAlign:VerticalAlign.TOP})),cantSplit:true}));return new Table({rows:[hr,...dr],width:{size:td,type:WidthType.DXA},borders:{top:{style:BorderStyle.SINGLE,size:6,color:C.navy},bottom:{style:BorderStyle.SINGLE,size:6,color:C.navy},left:{style:BorderStyle.SINGLE,size:4,color:C.border},right:{style:BorderStyle.SINGLE,size:4,color:C.border},insideHorizontal:{style:BorderStyle.SINGLE,size:4,color:C.border},insideVertical:{style:BorderStyle.SINGLE,size:4,color:C.border}}})}
function spacer(a=200){return new Paragraph({children:[],spacing:{after:a}})}

function buildCover(){return[
new Paragraph({children:[new TextRun({text:'TITAN  ·  QUANT  RESEARCH',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:120},alignment:AlignmentType.LEFT}),
new Paragraph({children:[new TextRun({text:'TITAN XAU AI',size:56,font:'Liberation Serif',color:C.navy,bold:true})],spacing:{after:80}}),
new Paragraph({children:[new TextRun({text:'INSTITUTIONAL  TRADING  SYSTEMS',size:18,font:'JetBrains Mono',color:C.muted})],spacing:{after:720},border:{bottom:{color:C.navy,size:18,style:BorderStyle.SINGLE,space:4}}}),
new Paragraph({children:[new TextRun({text:'M O D U L E   1 1   ·   L I C E N S I N G',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
new Paragraph({children:[new TextRun({text:'Commercial',size:52,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:' Licensing',size:52,font:'Liberation Serif',color:C.crimson,bold:true})],spacing:{after:360,line:240}}),
new Paragraph({children:[new TextRun({text:'Hardware lock: CPUID + Motherboard ID + Windows SID. Online + offline activation. RSA-4096 JWT. Monthly/Quarterly/Yearly expiry. 5-layer anti-crack. 3 tiers. Server-side heartbeat + revocation.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
new Paragraph({children:[new TextRun({text:'KEY FEATURES',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
table(['Feature','Value'],[['Hardware lock','3-factor (CPUID + MB ID + Windows SID)'],['Activation','Online (~2s) + Offline (email, 24h)'],['License expiry','Monthly / Quarterly / Yearly'],['Anti-crack','5 layers (obfuscation, tamper, anti-debug, anti-VM, behavioral)'],['Crypto','RSA-4096 + AES-256 + TLS 1.3'],['Tiers','Starter $12k / Pro $48k / Enterprise $180k']],null),
spacer(360),
new Paragraph({children:[new TextRun({text:'Prepared by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'TITAN Quant Research',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Reviewed by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'CTO · Security Officer · Legal',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Classification  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'COMMERCIAL — LICENSEE DISTRIBUTION',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Version  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'v1.0  ·  19 June 2026',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:0},border:{top:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}}}),
new Paragraph({children:[new PageBreak()]}),
]}

function buildToc(){return[
new Paragraph({children:[new TextRun({text:'Table of Contents',bold:true,size:44,font:'Liberation Serif',color:C.navy})],spacing:{after:240},border:{bottom:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:4}}}),
new Paragraph({children:[new TextRun({text:'Right-click the table below and choose "Update Field" to refresh page numbers.',italics:true,size:18,color:C.muted,font:'Liberation Serif'})],spacing:{after:280}}),
new TableOfContents('Table of Contents',{hyperlink:true,headingStyleRange:'1-3',stylesWithLevels:[new StyleLevel('Heading1',1),new StyleLevel('Heading2',2),new StyleLevel('Heading3',3)]}),
new Paragraph({children:[new PageBreak()]}),
]}

function buildBody(){const c=[];
c.push(h1('Chapter 1 — Executive Summary'));
c.push(p('The Commercial Licensing Architecture (CLA) is Module 11 of the TITAN XAU AI trading system. It is the system\'s commercial protection layer — a hardware-locked, cryptographically signed, anti-crack licensing framework that ensures only authorized licensees can operate the TITAN trading system. The CLA binds each license to the physical hardware via a 3-factor composite fingerprint (CPUID + Motherboard ID + Windows SID), issues RSA-4096 signed JWT license tokens, and enforces feature gating, expiry, and revocation through client-side validation and server-side heartbeat.'));
c.push(p('The architecture supports both online activation (~2 seconds) and offline activation (email-based, up to 24 hours). License tokens are cached locally in AES-256 encrypted form with the key derived from the hardware fingerprint — a stolen license file cannot be used on a different machine. The 1-hour heartbeat cycle ensures the server can revoke or renew licenses in near-real-time. A 7-day grace period allows continued trading during network outages before graceful shutdown.'));
c.push(p('Three license expiry types: Monthly (Starter, 30 days), Quarterly (Pro, 90 days), Yearly (Enterprise, 365 days). 5-layer anti-crack defense: code obfuscation, tamper detection, anti-debug, anti-VM, behavioral analytics. Server-side heartbeat is the ultimate backstop — even if all client-side protections are bypassed, the system cannot operate without a valid server-issued JWT.'));

c.push(h1('Chapter 2 — Architecture Overview'));
c.push(p('The CLA is organized into 5 layers: hardware fingerprint, activation engine, license server, anti-crack defense, and license expiry/enforcement. A 6th layer (audit) records every licensing event.'));
c.push(diagram('d01_architecture.png',6.5));
c.push(caption('Figure 2.1 — CLA architecture: 5 layers + audit.'));

c.push(h2('Layer Responsibilities'));
c.push(h3('L1 — Hardware Fingerprint'));
c.push(p('3 identifiers: CPUID (CPU manufacturer + model), Motherboard ID (baseboard serial), Windows SID (machine GUID). Each SHA-256 hashed, combined into composite: SHA-256(CPUID_hash + MB_hash + SID_hash). Unique per physical machine. 3 activations/year for legitimate hardware changes.'));

c.push(h3('L2 — Activation Engine'));
c.push(p('Online: HTTPS POST to license server with tenant_id + hw_fingerprint, receive RSA-4096 signed JWT. ~2s. Offline: generate request code, email to TITAN support, receive activation key. Up to 24h. Both produce same JWT format.'));

c.push(h3('L3 — License Server (SaaS)'));
c.push(p('AWS-hosted: JWT Issuer (RSA-4096, HSM-backed), TenantManager (CRUD + billing, 3 activations/year), RevocationService (revoke -> next heartbeat triggers graceful shutdown).'));

c.push(h3('L4 — Anti-Crack Defense (5 layers)'));
c.push(p('Code obfuscation (symbol strip + LTO + Cython + string encryption), tamper detection (SHA-256 checksum + IAT), anti-debug (IsDebuggerPresent + NtQuery + RDTSC), anti-VM (MAC OUI + CPUID hypervisor), behavioral (geo-IP + multi-IP + concurrent).'));

c.push(h3('L5 — License Expiry & Enforcement'));
c.push(p('ExpiryManager checks JWT on every heartbeat (1h). Monthly/Quarterly/Yearly. 7-day grace -> graceful shutdown. FeatureGate enforces tier-based access (hard boundary).'));

c.push(h1('Chapter 3 — Hardware Lock'));
c.push(p('3-factor composite fingerprint binds license to physical hardware. CPUID + Motherboard ID + Windows SID, each SHA-256 hashed, combined into composite. Cannot be spoofed without physical hardware replacement. 3 activations/year for legitimate changes.'));
c.push(table(['Identifier','Source','Changes When'],[['CPUID','CPUID instruction (EAX/EBX/ECX/EDX)','CPU replaced'],['Motherboard ID','SMBIOS/DMI baseboard serial','Motherboard replaced'],['Windows SID','Registry MachineGuid','Windows reinstalled']],null));

c.push(h1('Chapter 4 — Activation Workflow'));
c.push(p('Complete lifecycle: hardware fingerprint -> activation (online/offline) -> server validation -> JWT -> cached -> trading -> heartbeat -> renew/revoke -> grace -> shutdown.'));
c.push(diagram('d02_activation.png',6.0));
c.push(caption('Figure 4.1 — Activation workflow with online/offline paths, heartbeat, grace, expiry.'));

c.push(h2('Heartbeat Protocol'));
c.push(code(`Every 1 hour:
  Client -> Server: HTTPS POST /v1/heartbeat
    payload: {tenant_id, hw_fingerprint, current_jwt}
  Server -> Client: OK / RENEW / REVOKE / BLOCK
  If heartbeat fails: 7-day grace, retry every 15min, P2 alert
  After 7 days: graceful shutdown (flatten + halt)`));

c.push(h2('License Expiry Types'));
c.push(table(['Type','Duration','Tier','Grace'],[['Monthly','30 days','Starter ($12k/yr)','7 days'],['Quarterly','90 days','Pro ($48k/yr)','7 days'],['Yearly','365 days','Enterprise ($180k/yr)','7 days']],null));

c.push(h1('Chapter 5 — Security Design'));
c.push(p('4-layer crypto: RSA-4096 (signing, HSM-backed), AES-256-GCM (storage, key from hw_fp), TLS 1.3 + mTLS (transport), SHA-256 (fingerprinting). Key management: RSA private key never leaves HSM, public key embedded in binary. AES key derived from hw_fingerprint via PBKDF2 (100k iterations), never stored.'));
c.push(diagram('d03_security.png',6.5));
c.push(caption('Figure 5.1 — Cryptographic stack and key management.'));

c.push(h1('Chapter 6 — Anti-Crack Design'));
c.push(p('5 independent layers. Goal: raise crack cost above license price, delay crack 6+ months per release. Server-side heartbeat is ultimate backstop.'));
c.push(diagram('d04_anticrack.png',6.5));
c.push(caption('Figure 6.1 — 5-layer anti-crack defense.'));

c.push(h2('Crack Resistance Philosophy'));
c.push(p('No client-side protection is unbreakable. The CLA raises the cost above the license price. Each layer adds 1-4 weeks delay. Combined: 6+ months per release. Server-side heartbeat cannot be bypassed by client-side cracking.'));

c.push(h1('Chapter 7 — License Tier Matrix'));
c.push(p('3 tiers: Starter ($12k, 1 strategy, $50k cap, monthly), Pro ($48k, 3 strategies, $500k cap, quarterly), Enterprise ($180k, unlimited, yearly, white-label, on-prem). FeatureGate enforces at runtime — hard boundary.'));
c.push(diagram('d05_tiers_tests.png',6.5));
c.push(caption('Figure 7.1 — Tier matrix and validation tests.'));

c.push(h1('Chapter 8 — Validation Tests'));
c.push(p('120 tests: unit (70), integration (30), chaos (20). Critical: JWT signature verified, hw_fp match, expired -> shutdown, revoked -> halt < 1h, tamper -> halt, feature gate blocks, copied license -> hw mismatch, VM clone -> detected.'));

c.push(h1('Chapter 9 — Integration with TITAN Core'));
c.push(p('CLA is the first module loaded and last unloaded. No module starts until LicenseValidator verifies JWT. License check at startup + every 1h heartbeat. On failure: graceful shutdown (flatten + halt + P1 alert).'));
c.push(code(`TITAN startup:
  1. LicenseValidator.load() -> load cached JWT
  2. Verify RSA signature (embedded public key)
  3. Check expiry -> if expired: grace period
  4. Check hw_fingerprint -> if mismatch: REJECT
  5. Extract claims (tier, features, max_capital)
  6. FeatureGate.activate(claims)
  7. Start heartbeat timer (1h)
  8. If all OK: start trading modules
  9. If any FAIL: graceful shutdown

TITAN shutdown (on license failure):
  1. Halt new orders
  2. Cancel pending
  3. Flatten all positions
  4. Notify operator (P1)
  5. Audit log: license_fail + reason
  6. Exit non-zero`));

return c;}

async function main(){
console.log('[build] Generating TITAN Commercial Licensing Architecture DOCX...');
const doc=new Document({creator:'TITAN Quant Research',title:'TITAN XAU AI — Commercial Licensing Architecture',description:'Commercial Licensing Architecture',subject:'Licensing',
styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
sections:[
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Commercial Licensing Architecture',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v1.0  ·  COMMERCIAL',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},children:buildBody()},
]});
const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
