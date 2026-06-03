"""
PDF Builder — GoF Builder Pattern
Parses LLM markdown output and renders styled PDFs.
Templates: classic, modern_tech, multicolumn, minimalist
"""

import io
import re
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ── Markdown parser ───────────────────────────────────────────────────────────

def clean_md(text: str) -> str:
    """Strip common markdown markers so they don't appear literally in PDFs."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)   # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)         # *italic*
    text = re.sub(r'__(.+?)__', r'\1', text)          # __bold__
    text = re.sub(r'_(.+?)_', r'\1', text)            # _italic_
    text = re.sub(r'^#{1,6}\s*', '', text)             # ## headings
    text = re.sub(r'`(.+?)`', r'\1', text)             # `code`
    text = text.replace('■', '-').replace('□', '')
    return text.strip()


def parse_resume(text: str):
    """
    Parse LLM resume text into structured blocks.
    Returns list of (kind, content):
      'name'    — first non-empty line (person's name)
      'contact' — second line (email/phone/location)
      'heading' — section header (## or ALL CAPS or ends with :)
      'bullet'  — bullet point
      'body'    — regular paragraph
      'empty'   — blank line
    """
    blocks = []
    lines = text.split('\n')
    name_found = False
    contact_found = False

    for line in lines:
        raw = line.strip()
        if not raw:
            blocks.append(('empty', ''))
            continue

        cleaned = clean_md(raw)
        if not cleaned:
            blocks.append(('empty', ''))
            continue

        # Detect section headings: ##, ALL CAPS short line, or ends with ":"
        is_heading = (
            raw.startswith('#') or
            (cleaned.isupper() and len(cleaned) < 55) or
            (cleaned.rstrip(':').isupper() and len(cleaned) < 55) or
            (cleaned.endswith(':') and len(cleaned) < 40 and cleaned[0].isupper())
        )

        # Detect bullets
        is_bullet = raw.lstrip().startswith(('•', '-', '*', '–', '▸', '·'))

        if not name_found and not is_heading and not is_bullet:
            blocks.append(('name', cleaned))
            name_found = True
        elif name_found and not contact_found and not is_heading and not is_bullet:
            blocks.append(('contact', cleaned))
            contact_found = True
        elif is_heading:
            blocks.append(('heading', re.sub(r'^#+\s*', '', cleaned).rstrip(':').strip()))
        elif is_bullet:
            blocks.append(('bullet', re.sub(r'^[•\-\*–▸·]\s*', '', cleaned).strip()))
        else:
            blocks.append(('body', cleaned))

    return blocks


# ── Base Builder ─────────────────────────────────────────────────────────────

class PDFBuilder:
    def __init__(self):
        self._buffer = io.BytesIO()
        self._styles = getSampleStyleSheet()

    def build(self, text: str) -> bytes:
        raise NotImplementedError

    def _get_bytes(self) -> bytes:
        self._buffer.seek(0)
        return self._buffer.read()


# ── Template 1: Classic ───────────────────────────────────────────────────────
# Centered name, clean horizontal rules, traditional serif-like look

class ClassicBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=0.9*inch, rightMargin=0.9*inch,
            topMargin=0.8*inch, bottomMargin=0.8*inch)

        dark = colors.HexColor("#1a1a1a")
        rule_color = colors.HexColor("#333333")

        name_style = ParagraphStyle("CName", fontName="Helvetica-Bold",
            fontSize=20, alignment=TA_CENTER, textColor=dark,
            spaceAfter=4, leading=24)
        contact_style = ParagraphStyle("CContact", fontName="Helvetica",
            fontSize=9.5, alignment=TA_CENTER, textColor=colors.HexColor("#555"),
            spaceAfter=8, leading=13)
        heading_style = ParagraphStyle("CHead", fontName="Helvetica-Bold",
            fontSize=10, textColor=dark, spaceBefore=10, spaceAfter=3, leading=13)
        body_style = ParagraphStyle("CBody", fontName="Helvetica",
            fontSize=10, leading=14, textColor=dark, spaceAfter=3)
        bullet_style = ParagraphStyle("CBullet", fontName="Helvetica",
            fontSize=10, leading=14, textColor=dark,
            leftIndent=14, spaceAfter=2)

        story = []
        for kind, content in parse_resume(text):
            if kind == 'name':
                story.append(Paragraph(content, name_style))
                story.append(HRFlowable(width="100%", thickness=1.5,
                                        color=rule_color, spaceAfter=4))
            elif kind == 'contact':
                story.append(Paragraph(content, contact_style))
            elif kind == 'heading':
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor("#aaa"),
                                        spaceBefore=8, spaceAfter=2))
                story.append(Paragraph(content.upper(), heading_style))
            elif kind == 'bullet':
                story.append(Paragraph(f"• {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 4))

        doc.build(story)
        return self._get_bytes()


# ── Template 2: Modern Tech ───────────────────────────────────────────────────
# Bold name left-aligned, indigo section bars, clean sans-serif

class ModernTechBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=0.75*inch, rightMargin=0.75*inch,
            topMargin=0.75*inch, bottomMargin=0.75*inch)

        accent = colors.HexColor("#4f46e5")
        dark = colors.HexColor("#0f172a")
        light_accent = colors.HexColor("#eef2ff")

        name_style = ParagraphStyle("MTName", fontName="Helvetica-Bold",
            fontSize=24, textColor=dark, spaceAfter=2, leading=28)
        contact_style = ParagraphStyle("MTContact", fontName="Helvetica",
            fontSize=9, textColor=colors.HexColor("#64748b"),
            spaceAfter=10, leading=13)
        heading_style = ParagraphStyle("MTHead", fontName="Helvetica-Bold",
            fontSize=9, textColor=accent, spaceBefore=12, spaceAfter=4,
            leading=11, backColor=light_accent, borderPad=5,
            leftIndent=-6, rightIndent=-6)
        body_style = ParagraphStyle("MTBody", fontName="Helvetica",
            fontSize=9.5, leading=14, textColor=dark, spaceAfter=3)
        bullet_style = ParagraphStyle("MTBullet", fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=dark,
            leftIndent=12, spaceAfter=2)

        story = []
        for kind, content in parse_resume(text):
            if kind == 'name':
                story.append(Paragraph(content, name_style))
            elif kind == 'contact':
                story.append(Paragraph(content, contact_style))
                story.append(HRFlowable(width="100%", thickness=2,
                                        color=accent, spaceAfter=4))
            elif kind == 'heading':
                story.append(Spacer(1, 4))
                story.append(Paragraph(f"  {content.upper()}  ", heading_style))
            elif kind == 'bullet':
                story.append(Paragraph(f"▸  {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 3))

        doc.build(story)
        return self._get_bytes()


# ── Template 3: Multicolumn ───────────────────────────────────────────────────
# Left sidebar (contact/skills), right main content — like reference screenshot

class MulticolumnBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        W, H = LETTER
        buf = self._buffer

        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

        sidebar_w = 2.0 * inch
        gap = 0.2 * inch
        main_w = W - sidebar_w - gap - 1.2 * inch
        margin_top = 0.8 * inch
        margin_bot = 0.8 * inch
        margin_left = 0.5 * inch

        sidebar_color = colors.HexColor("#1e293b")
        accent = colors.HexColor("#38bdf8")
        white = colors.white
        dark = colors.HexColor("#1a1a2e")

        # Styles for sidebar
        s_name = ParagraphStyle("MCsName", fontName="Helvetica-Bold",
            fontSize=16, textColor=white, leading=20, spaceAfter=4)
        s_contact_head = ParagraphStyle("MCsContactH", fontName="Helvetica-Bold",
            fontSize=8, textColor=accent, leading=11,
            spaceBefore=10, spaceAfter=3)
        s_contact = ParagraphStyle("MCsContact", fontName="Helvetica",
            fontSize=8, textColor=colors.HexColor("#cbd5e1"), leading=12, spaceAfter=2)

        # Styles for main area
        m_heading = ParagraphStyle("MCmHead", fontName="Helvetica-Bold",
            fontSize=10, textColor=dark, spaceBefore=10, spaceAfter=3,
            leading=13, borderPad=0)
        m_body = ParagraphStyle("MCmBody", fontName="Helvetica",
            fontSize=9.5, leading=14, textColor=dark, spaceAfter=3)
        m_bullet = ParagraphStyle("MCmBullet", fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=dark,
            leftIndent=12, spaceAfter=2)
        m_title = ParagraphStyle("MCmTitle", fontName="Helvetica-Bold",
            fontSize=9.5, leading=13, textColor=dark, spaceAfter=1)

        blocks = parse_resume(text)

        # Split: first heading group (contact/skills) → sidebar; rest → main
        sidebar_story = []
        main_story = []

        # Name and contact go to sidebar
        sidebar_headings = {'contact', 'skills', 'education', 'certifications',
                            'languages', 'interests', 'summary'}
        main_headings = {'experience', 'work experience', 'projects',
                         'achievements', 'accomplishments', 'awards'}

        current_section = 'sidebar'
        for kind, content in blocks:
            if kind == 'name':
                sidebar_story.append(Paragraph(content, s_name))
            elif kind == 'contact' and not sidebar_story[-1:] or \
                 (sidebar_story and isinstance(sidebar_story[-1], Paragraph) and
                  sidebar_story[-1].style.name == 'MCsName'):
                sidebar_story.append(Paragraph(content, s_contact))
            elif kind == 'heading':
                low = content.lower()
                if any(h in low for h in main_headings):
                    current_section = 'main'
                else:
                    current_section = 'sidebar'

                if current_section == 'sidebar':
                    sidebar_story.append(Paragraph(content.upper(), s_contact_head))
                else:
                    main_story.append(HRFlowable(width="100%", thickness=0.5,
                                                  color=colors.HexColor("#cbd5e1"),
                                                  spaceBefore=4, spaceAfter=2))
                    main_story.append(Paragraph(content.upper(), m_heading))
            elif kind == 'bullet':
                if current_section == 'sidebar':
                    sidebar_story.append(Paragraph(f"• {content}", s_contact))
                else:
                    main_story.append(Paragraph(f"• {content}", m_bullet))
            elif kind == 'body':
                if current_section == 'sidebar':
                    sidebar_story.append(Paragraph(content, s_contact))
                else:
                    main_story.append(Paragraph(content, m_body))
            elif kind == 'empty':
                if current_section == 'sidebar':
                    sidebar_story.append(Spacer(1, 3))
                else:
                    main_story.append(Spacer(1, 3))

        # Build as a two-column table
        doc = SimpleDocTemplate(buf, pagesize=LETTER,
            leftMargin=0.5*inch, rightMargin=0.5*inch,
            topMargin=0.5*inch, bottomMargin=0.5*inch)

        from reportlab.platypus import KeepInFrame

        avail_h = H - 1.0*inch
        sidebar_frame = KeepInFrame(sidebar_w, avail_h, sidebar_story,
                                     mode='shrink')
        main_frame = KeepInFrame(main_w, avail_h, main_story,
                                  mode='shrink')

        table = Table([[sidebar_frame, main_frame]],
                      colWidths=[sidebar_w + 0.1*inch, main_w + 0.4*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), sidebar_color),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 12),
            ('RIGHTPADDING', (0, 0), (0, 0), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('LEFTPADDING', (1, 0), (1, 0), 16),
        ]))

        doc.build([table])
        return self._get_bytes()


# ── Template 4: Minimalist ────────────────────────────────────────────────────
# Max whitespace, thin lines, elegant grey accents

class MinimalistBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=1.1*inch, rightMargin=1.1*inch,
            topMargin=1.0*inch, bottomMargin=1.0*inch)

        near_black = colors.HexColor("#111111")
        grey = colors.HexColor("#6b7280")
        light_rule = colors.HexColor("#e5e7eb")

        name_style = ParagraphStyle("MinName", fontName="Helvetica-Bold",
            fontSize=22, textColor=near_black, spaceAfter=3, leading=26)
        contact_style = ParagraphStyle("MinContact", fontName="Helvetica",
            fontSize=9, textColor=grey, spaceAfter=14, leading=13)
        heading_style = ParagraphStyle("MinHead", fontName="Helvetica-Bold",
            fontSize=8.5, textColor=grey, spaceBefore=14, spaceAfter=5,
            leading=11, charSpace=1.5)
        body_style = ParagraphStyle("MinBody", fontName="Helvetica",
            fontSize=10, leading=16, textColor=near_black, spaceAfter=4)
        bullet_style = ParagraphStyle("MinBullet", fontName="Helvetica",
            fontSize=10, leading=15, textColor=near_black,
            leftIndent=14, spaceAfter=3)

        story = []
        for kind, content in parse_resume(text):
            if kind == 'name':
                story.append(Paragraph(content, name_style))
            elif kind == 'contact':
                story.append(Paragraph(content, contact_style))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=light_rule, spaceAfter=6))
            elif kind == 'heading':
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=light_rule, spaceBefore=6))
                story.append(Paragraph(content.upper(), heading_style))
            elif kind == 'bullet':
                story.append(Paragraph(f"—  {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 5))

        doc.build(story)
        return self._get_bytes()


# ── Template 5: Executive Banner ─────────────────────────────────────────────
# Dark gray header bar with white ALL CAPS name, contact on right

class ExecutiveBannerBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        W, H = LETTER
        buf = self._buffer
        doc = SimpleDocTemplate(buf, pagesize=LETTER,
            leftMargin=0*inch, rightMargin=0*inch,
            topMargin=0*inch, bottomMargin=0.6*inch)

        banner_bg = colors.HexColor("#4a4a4a")
        white = colors.white
        dark = colors.HexColor("#1a1a1a")
        rule = colors.HexColor("#cccccc")

        name_style = ParagraphStyle("EBName", fontName="Helvetica-Bold",
            fontSize=20, textColor=white, leading=24, alignment=TA_LEFT)
        contact_banner_style = ParagraphStyle("EBContact", fontName="Helvetica",
            fontSize=8.5, textColor=colors.HexColor("#dddddd"), alignment=TA_RIGHT, leading=12)
        heading_style = ParagraphStyle("EBHead", fontName="Helvetica-Bold",
            fontSize=9.5, textColor=dark, spaceBefore=10, spaceAfter=3,
            leading=12, leftIndent=36)
        body_style = ParagraphStyle("EBBody", fontName="Helvetica",
            fontSize=10, leading=14, textColor=dark, spaceAfter=3, leftIndent=36)
        bullet_style = ParagraphStyle("EBBullet", fontName="Helvetica",
            fontSize=10, leading=13, textColor=dark, leftIndent=50, spaceAfter=2)

        blocks = parse_resume(text)
        name = next((c for k, c in blocks if k == 'name'), 'Your Name')
        contact = next((c for k, c in blocks if k == 'contact'), '')

        # Build banner as a table row
        banner_name = Paragraph(name.upper(), name_style)
        banner_contact = Paragraph(contact.replace(' | ', '\n').replace(' · ', '\n'), contact_banner_style)
        banner_table = Table([[banner_name, banner_contact]],
            colWidths=[4.5*inch, 3.6*inch])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), banner_bg),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (0,0), 36),
            ('RIGHTPADDING', (1,0), (1,0), 28),
            ('TOPPADDING', (0,0), (-1,-1), 18),
            ('BOTTOMPADDING', (0,0), (-1,-1), 18),
        ]))

        story = [banner_table, Spacer(1, 8)]

        for kind, content in blocks:
            if kind in ('name', 'contact'): continue
            if kind == 'heading':
                story.append(HRFlowable(width="88%", thickness=0.5, color=rule,
                                        spaceBefore=8, spaceAfter=3))
                story.append(Paragraph(content.upper(), heading_style))
            elif kind == 'bullet':
                story.append(Paragraph(f"• {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 3))

        doc.build(story)
        return self._get_bytes()


# ── Template 6: Bold Header ───────────────────────────────────────────────────
# Giant ALL CAPS name, thick rule, strong single-column

class BoldHeaderBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=0.75*inch, rightMargin=0.75*inch,
            topMargin=0.75*inch, bottomMargin=0.75*inch)

        dark = colors.HexColor("#111111")
        mid = colors.HexColor("#555555")

        name_style = ParagraphStyle("BHName", fontName="Helvetica-Bold",
            fontSize=26, textColor=dark, leading=30, spaceAfter=2)
        contact_style = ParagraphStyle("BHContact", fontName="Helvetica",
            fontSize=9, textColor=mid, spaceAfter=10, leading=13)
        heading_style = ParagraphStyle("BHHead", fontName="Helvetica-Bold",
            fontSize=10, textColor=dark, spaceBefore=12, spaceAfter=3, leading=13)
        body_style = ParagraphStyle("BHBody", fontName="Helvetica",
            fontSize=10, leading=14, textColor=dark, spaceAfter=3)
        bullet_style = ParagraphStyle("BHBullet", fontName="Helvetica",
            fontSize=10, leading=13, textColor=dark, leftIndent=14, spaceAfter=2)

        blocks = parse_resume(text)
        story = []

        for kind, content in blocks:
            if kind == 'name':
                story.append(Paragraph(content.upper(), name_style))
                story.append(HRFlowable(width="100%", thickness=3, color=dark, spaceAfter=4))
            elif kind == 'contact':
                story.append(Paragraph(content, contact_style))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor("#bbbbbb"), spaceAfter=6))
            elif kind == 'heading':
                story.append(Paragraph(content.upper(), heading_style))
                story.append(HRFlowable(width="100%", thickness=1, color=dark, spaceAfter=4))
            elif kind == 'bullet':
                story.append(Paragraph(f"• {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 4))

        doc.build(story)
        return self._get_bytes()


# ── Template 7: Split Two-Column ──────────────────────────────────────────────
# Centered name + divider, content in two equal columns

class SplitColumnBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        W, H = LETTER
        buf = self._buffer
        doc = SimpleDocTemplate(buf, pagesize=LETTER,
            leftMargin=0.7*inch, rightMargin=0.7*inch,
            topMargin=0.75*inch, bottomMargin=0.75*inch)

        dark = colors.HexColor("#1a1a1a")
        mid = colors.HexColor("#555555")
        rule = colors.HexColor("#999999")

        name_style = ParagraphStyle("SCName", fontName="Helvetica-Bold",
            fontSize=18, textColor=dark, alignment=TA_CENTER, spaceAfter=3, leading=22)
        contact_style = ParagraphStyle("SCContact", fontName="Helvetica",
            fontSize=9, textColor=mid, alignment=TA_CENTER, spaceAfter=10, leading=13)
        heading_style = ParagraphStyle("SCHead", fontName="Helvetica-Bold",
            fontSize=9.5, textColor=dark, spaceBefore=10, spaceAfter=3, leading=12)
        body_style = ParagraphStyle("SCBody", fontName="Helvetica",
            fontSize=9.5, leading=14, textColor=dark, spaceAfter=3)
        bullet_style = ParagraphStyle("SCBullet", fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=dark, leftIndent=12, spaceAfter=2)

        blocks = parse_resume(text)
        from reportlab.platypus import KeepInFrame

        # Header (full width)
        header = []
        name = next((c for k,c in blocks if k=='name'), 'Your Name')
        contact = next((c for k,c in blocks if k=='contact'), '')
        header.append(Paragraph(name, name_style))
        header.append(HRFlowable(width="100%", thickness=1, color=rule, spaceAfter=4))
        header.append(Paragraph(contact, contact_style))
        header.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=8))

        # Split sections into left and right columns
        sections = []
        current = None
        for kind, content in blocks:
            if kind in ('name', 'contact'): continue
            if kind == 'heading':
                current = {'title': content, 'items': []}
                sections.append(current)
            elif current:
                current['items'].append((kind, content))

        left_secs = sections[:len(sections)//2 + len(sections)%2]
        right_secs = sections[len(sections)//2 + len(sections)%2:]

        def build_col(secs):
            col = []
            for sec in secs:
                col.append(Paragraph(sec['title'].upper(), heading_style))
                col.append(HRFlowable(width="100%", thickness=0.5, color=rule, spaceAfter=3))
                for kind, content in sec['items']:
                    if kind == 'bullet': col.append(Paragraph(f"• {content}", bullet_style))
                    elif kind == 'body': col.append(Paragraph(content, body_style))
                    elif kind == 'empty': col.append(Spacer(1, 3))
            return col

        col_w = (W - 1.4*inch - 0.2*inch) / 2
        avail_h = H - 2.5*inch
        left_frame = KeepInFrame(col_w, avail_h, build_col(left_secs), mode='shrink')
        right_frame = KeepInFrame(col_w, avail_h, build_col(right_secs), mode='shrink')

        body_table = Table([[left_frame, right_frame]], colWidths=[col_w, col_w])
        body_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))

        doc.build(header + [body_table])
        return self._get_bytes()


# ── Template 8: Simple Sidebar ────────────────────────────────────────────────
# Narrow left contact sidebar, serif main content, black square icon

class SimpleSidebarBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        W, H = LETTER
        buf = self._buffer
        doc = SimpleDocTemplate(buf, pagesize=LETTER,
            leftMargin=0*inch, rightMargin=0.5*inch,
            topMargin=0*inch, bottomMargin=0.5*inch)

        sidebar_bg = colors.HexColor("#f5f5f5")
        dark = colors.HexColor("#1a1a1a")
        accent = colors.HexColor("#333333")

        s_name = ParagraphStyle("SSName", fontName="Helvetica-Bold",
            fontSize=11, textColor=dark, leading=15, spaceAfter=8)
        s_label = ParagraphStyle("SSLabel", fontName="Helvetica-Bold",
            fontSize=7.5, textColor=accent, leading=10, spaceBefore=10, spaceAfter=3,
            textTransform='uppercase')
        s_body = ParagraphStyle("SSBody", fontName="Helvetica",
            fontSize=8, textColor=colors.HexColor("#444"), leading=11, spaceAfter=2)

        m_heading = ParagraphStyle("SSMHead", fontName="Helvetica-Bold",
            fontSize=9.5, textColor=dark, spaceBefore=10, spaceAfter=3, leading=12)
        m_body = ParagraphStyle("SSMBody", fontName="Helvetica",
            fontSize=9.5, leading=14, textColor=dark, spaceAfter=3)
        m_bullet = ParagraphStyle("SSMBullet", fontName="Helvetica",
            fontSize=9.5, leading=13, textColor=dark, leftIndent=12, spaceAfter=2)

        blocks = parse_resume(text)
        sidebar_keys = {'contact','skills','education','certifications','languages','summary','profile'}
        main_keys = {'experience','work','projects','achievements','accomplishments'}

        name = next((c for k,c in blocks if k=='name'), 'Your Name')
        contact = next((c for k,c in blocks if k=='contact'), '')

        sidebar_story = []
        main_story = []

        sidebar_story.append(Paragraph(name, s_name))
        sidebar_story.append(Paragraph(contact.replace(' | ','\n').replace(' · ','\n'), s_body))

        current_section = 'sidebar'
        for kind, content in blocks:
            if kind in ('name','contact'): continue
            if kind == 'heading':
                low = content.lower()
                current_section = 'sidebar' if any(k in low for k in sidebar_keys) else 'main'
                if current_section == 'sidebar':
                    sidebar_story.append(Paragraph(content.upper(), s_label))
                else:
                    main_story.append(HRFlowable(width="100%", thickness=0.5,
                                                  color=colors.HexColor("#cccccc"), spaceAfter=3))
                    main_story.append(Paragraph(content, m_heading))
            elif kind == 'bullet':
                if current_section == 'sidebar': sidebar_story.append(Paragraph(f"• {content}", s_body))
                else: main_story.append(Paragraph(f"• {content}", m_bullet))
            elif kind == 'body':
                if current_section == 'sidebar': sidebar_story.append(Paragraph(content, s_body))
                else: main_story.append(Paragraph(content, m_body))
            elif kind == 'empty':
                if current_section == 'sidebar': sidebar_story.append(Spacer(1, 2))
                else: main_story.append(Spacer(1, 3))

        from reportlab.platypus import KeepInFrame
        sb_w = 2.1*inch
        main_w = W - sb_w - 0.5*inch
        avail_h = H - 0.5*inch
        sb_frame = KeepInFrame(sb_w, avail_h, sidebar_story, mode='shrink')
        main_frame = KeepInFrame(main_w, avail_h, main_story, mode='shrink')

        table = Table([[sb_frame, main_frame]], colWidths=[sb_w, main_w])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,0), sidebar_bg),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (0,0), 14),
            ('RIGHTPADDING', (0,0), (0,0), 12),
            ('TOPPADDING', (0,0), (-1,-1), 16),
            ('LEFTPADDING', (1,0), (1,0), 20),
        ]))
        doc.build([table])
        return self._get_bytes()


# ── Template 9: Professional Center ──────────────────────────────────────────
# Centered name + horizontal line, contact centered below, clean single col

class ProfessionalCenterBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=0.85*inch, rightMargin=0.85*inch,
            topMargin=0.85*inch, bottomMargin=0.85*inch)

        dark = colors.HexColor("#1a1a1a")
        mid = colors.HexColor("#666666")
        rule = colors.HexColor("#888888")

        name_style = ParagraphStyle("PCName", fontName="Helvetica-Bold",
            fontSize=20, textColor=dark, alignment=TA_CENTER, spaceAfter=4, leading=24)
        contact_style = ParagraphStyle("PCContact", fontName="Helvetica",
            fontSize=9, textColor=mid, alignment=TA_CENTER, spaceAfter=10, leading=13)
        heading_style = ParagraphStyle("PCHead", fontName="Helvetica-Bold",
            fontSize=10, textColor=dark, spaceBefore=10, spaceAfter=2, leading=13)
        body_style = ParagraphStyle("PCBody", fontName="Helvetica",
            fontSize=10, leading=15, textColor=dark, spaceAfter=3)
        bullet_style = ParagraphStyle("PCBullet", fontName="Helvetica",
            fontSize=10, leading=14, textColor=dark, leftIndent=14, spaceAfter=2)

        blocks = parse_resume(text)
        story = []

        for kind, content in blocks:
            if kind == 'name':
                story.append(Paragraph(content, name_style))
                story.append(HRFlowable(width="100%", thickness=1, color=rule, spaceAfter=5))
            elif kind == 'contact':
                story.append(Paragraph(content, contact_style))
                story.append(HRFlowable(width="60%", thickness=0.5,
                                        color=colors.HexColor("#cccccc"), spaceAfter=8))
            elif kind == 'heading':
                story.append(Spacer(1, 4))
                story.append(Paragraph(content, heading_style))
                story.append(HRFlowable(width="100%", thickness=0.5, color=rule, spaceAfter=4))
            elif kind == 'bullet':
                story.append(Paragraph(f"• {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 4))

        doc.build(story)
        return self._get_bytes()


# ── Template 10: Compact Pro ─────────────────────────────────────────────────
# Dense layout, max content per page, small fonts, two-col skills

class CompactProBuilder(PDFBuilder):
    def build(self, text: str) -> bytes:
        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=0.65*inch, rightMargin=0.65*inch,
            topMargin=0.65*inch, bottomMargin=0.65*inch)

        dark = colors.HexColor("#111111")
        mid = colors.HexColor("#555555")
        rule = colors.HexColor("#aaaaaa")

        name_style = ParagraphStyle("CPName", fontName="Helvetica-Bold",
            fontSize=15, textColor=dark, spaceAfter=1, leading=18)
        contact_style = ParagraphStyle("CPContact", fontName="Helvetica",
            fontSize=8.5, textColor=mid, spaceAfter=6, leading=12)
        heading_style = ParagraphStyle("CPHead", fontName="Helvetica-Bold",
            fontSize=9, textColor=dark, spaceBefore=7, spaceAfter=2, leading=11)
        body_style = ParagraphStyle("CPBody", fontName="Helvetica",
            fontSize=9, leading=13, textColor=dark, spaceAfter=2)
        bullet_style = ParagraphStyle("CPBullet", fontName="Helvetica",
            fontSize=9, leading=12, textColor=dark, leftIndent=12, spaceAfter=1)

        blocks = parse_resume(text)
        story = []

        for kind, content in blocks:
            if kind == 'name':
                story.append(Paragraph(content, name_style))
            elif kind == 'contact':
                story.append(Paragraph(content, contact_style))
                story.append(HRFlowable(width="100%", thickness=1.5, color=dark, spaceAfter=4))
            elif kind == 'heading':
                story.append(HRFlowable(width="100%", thickness=0.5, color=rule, spaceBefore=4, spaceAfter=2))
                story.append(Paragraph(content.upper(), heading_style))
            elif kind == 'bullet':
                story.append(Paragraph(f"• {content}", bullet_style))
            elif kind == 'body':
                story.append(Paragraph(content, body_style))
            elif kind == 'empty':
                story.append(Spacer(1, 2))

        doc.build(story)
        return self._get_bytes()


# ── Cover Letter ──────────────────────────────────────────────────────────────

class CoverLetterBuilder(PDFBuilder):
    """Builds a cover letter PDF styled to match the chosen resume template."""

    TEMPLATE_STYLES = {
        "classic":          ("#1a1a1a", "Helvetica",      "#333333", 1.0),
        "modern_tech":      ("#4f46e5", "Helvetica",      "#4f46e5", 0.85),
        "multicolumn":      ("#1e293b", "Helvetica",      "#1e293b", 0.85),
        "minimalist":       ("#9ca3af", "Helvetica",      "#e5e7eb", 1.1),
        "executive_banner": ("#4a4a4a", "Helvetica",      "#4a4a4a", 0.85),
        "bold_header":      ("#111111", "Helvetica-Bold", "#111111", 0.85),
        "split_column":     ("#1a1a1a", "Helvetica",      "#888888", 0.85),
        "simple_sidebar":   ("#1a1a1a", "Helvetica",      "#cccccc", 0.85),
        "professional":     ("#1a1a1a", "Helvetica",      "#888888", 1.0),
        "compact_pro":      ("#111111", "Helvetica",      "#111111", 0.85),
    }

    def build(self, text: str, template: str = "classic", name: str = "", contact: str = "") -> bytes:
        accent_hex, font, rule_hex, margin = self.TEMPLATE_STYLES.get(
            template, self.TEMPLATE_STYLES["classic"])

        doc = SimpleDocTemplate(self._buffer, pagesize=LETTER,
            leftMargin=margin*inch, rightMargin=margin*inch,
            topMargin=margin*inch, bottomMargin=margin*inch)

        accent = colors.HexColor(accent_hex)
        rule_color = colors.HexColor(rule_hex)
        dark = colors.HexColor("#1a1a1a")

        name_style = ParagraphStyle("CLName", fontName=font,
            fontSize=16, textColor=accent, leading=20, spaceAfter=2)
        contact_style = ParagraphStyle("CLContact", fontName="Helvetica",
            fontSize=9, textColor=colors.HexColor("#666666"), spaceAfter=10, leading=13)
        body_style = ParagraphStyle("CLBody", fontName="Helvetica",
            fontSize=11, leading=17, spaceAfter=14, textColor=dark)

        story = []

        # Letterhead matching template
        if name:
            story.append(Paragraph(
                name.upper() if template in ("executive_banner", "bold_header") else name,
                name_style))
        if contact:
            story.append(Paragraph(contact, contact_style))

        story.append(HRFlowable(width="100%", thickness=2 if template == "bold_header" else 0.75,
                                color=rule_color, spaceAfter=14))

        cleaned = clean_md(text)
        for para in cleaned.split("\n\n"):
            para = para.strip().replace("\n", " ")
            # Skip lines that look like "Hiring Manager City, ST" run together — fix spacing
            para = re.sub(r'(Manager|Director|Team)\s+([A-Z])', r'\1\n\2', para)
            if para:
                story.append(Paragraph(para, body_style))

        doc.build(story)
        return self._get_bytes()


# ── Registry ──────────────────────────────────────────────────────────────────

TEMPLATES = {
    "classic":           ("Classic",            "Centered name, traditional formatting — universal",          ClassicBuilder),
    "modern_tech":       ("Modern Tech",        "Bold left header, indigo accents — tech & engineering",      ModernTechBuilder),
    "multicolumn":       ("Multicolumn",        "Dark sidebar + main content — creative & standout",          MulticolumnBuilder),
    "minimalist":        ("Minimalist",         "Ultra-clean whitespace, grey accents — design & marketing",  MinimalistBuilder),
    "executive_banner":  ("Executive Banner",   "Dark gray header bar, white caps name — senior roles",       ExecutiveBannerBuilder),
    "bold_header":       ("Bold Header",        "Giant ALL CAPS name, strong rules — high impact",            BoldHeaderBuilder),
    "split_column":      ("Split Column",       "Centered name, two equal content columns — organized",       SplitColumnBuilder),
    "simple_sidebar":    ("Simple Sidebar",     "Light gray sidebar, serif main — clean professional",        SimpleSidebarBuilder),
    "professional":      ("Professional",       "Centered name + ruled divider, classic single column",       ProfessionalCenterBuilder),
    "compact_pro":       ("Compact Pro",        "Dense layout, max content per page — experienced candidates", CompactProBuilder),
}


def build_resume_pdf(text: str, template: str = "classic") -> bytes:
    builder_class = TEMPLATES.get(template, TEMPLATES["classic"])[2]
    return builder_class().build(text)


def build_cover_letter_pdf(text: str, template: str = "classic", name: str = "", contact: str = "") -> bytes:
    return CoverLetterBuilder().build(text, template=template, name=name, contact=contact)
