"""Turn the deck's speaker notes into a talk-script PDF.

    python presentation/build_script.py deck.pptx script.pdf
"""
import sys

from pptx import Presentation
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

VIOLET, GRAY, INK = HexColor("#57068C"), HexColor("#6B6B78"), HexColor("#1C1B22")
WPM = 150

h_title = ParagraphStyle("t", fontName="Times-Bold", fontSize=22, leading=26, textColor=VIOLET, spaceAfter=4)
h_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=11, leading=15, textColor=GRAY, spaceAfter=16)
slide_h = ParagraphStyle("h", fontName="Times-Bold", fontSize=13.5, leading=17, textColor=VIOLET)
meta = ParagraphStyle("m", fontName="Helvetica-Oblique", fontSize=8.5, leading=12, textColor=GRAY, alignment=2)
body = ParagraphStyle("b", fontName="Helvetica", fontSize=10.5, leading=15.5, textColor=INK, spaceAfter=7)


def clock(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(src, out):
    prs = Presentation(src)
    items = []
    for i, slide in enumerate(prs.slides, 1):
        title = slide.shapes.title.text if slide.shapes.title is not None else f"Slide {i}"
        notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        items.append((i, title.replace("\n", " "), notes))
    t = 0.0
    story = [Paragraph("GuardEQ — Final Presentation Script", h_title)]
    total = sum(len(n.split()) for _, _, n in items) / WPM * 60 + 3 * len(items)
    story.append(Paragraph(f"Rohit Shidid (RRS6770) · ECE-GY 6263 Game Theory, Fall 2026<br/>{len(items)} slides · about "
                           f"{clock(total)} spoken · numbers are read from the final results", h_sub))
    doc = BaseDocTemplate(out, pagesize=LETTER, leftMargin=0.9 * inch, rightMargin=0.9 * inch, topMargin=0.8 * inch,
                          bottomMargin=0.85 * inch, title="GuardEQ — Final Presentation Script", author="Rohit Shidid")

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(0.9 * inch, 0.55 * inch, "GuardEQ — final presentation script · Rohit Shidid")
        canvas.drawRightString(LETTER[0] - 0.9 * inch, 0.55 * inch, f"Page {d.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)], onPage=footer)])
    for i, title, notes in items:
        start = t
        t += len(notes.split()) / WPM * 60 + 3
        head = Table([[Paragraph(f"Slide {i} &nbsp;|&nbsp; {esc(title)}", slide_h), Paragraph(f"{clock(start)} – {clock(t)}", meta)]],
                     colWidths=[doc.width - 1.2 * inch, 1.2 * inch],
                     style=TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                       ("LINEBELOW", (0, 0), (-1, -1), 0.75, VIOLET)]))
        paras = [p for p in notes.split("\n") if p.strip()] or ["(no notes)"]
        story.append(KeepTogether([head, Spacer(1, 6), Paragraph(esc(paras[0]), body)]))
        story += [Paragraph(esc(p), body) for p in paras[1:]]
        story.append(Spacer(1, 8))
    doc.build(story)
    print(f"wrote {out} ({clock(t)})")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
