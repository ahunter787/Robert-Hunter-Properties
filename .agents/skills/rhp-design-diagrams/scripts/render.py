"""Render editable scene books to vector SVG and Letter PDFs (tooling only)."""

import argparse
import html
import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


def gray(color):
    color = color.lstrip("#")
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    value = round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    return f"#{value:02x}{value:02x}{value:02x}"


def render(book, stem, *, grayscale=False):
    suffix = "-grayscale" if grayscale else ""
    output = Path(str(stem) + suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output) + ".pdf", invariant=1)
    pdf.setTitle(book["title"] + (" - grayscale" if grayscale else ""))
    pdf.setAuthor("Robert Hunter Properties - Design study")
    for index, page in enumerate(book["pages"], 1):
        w, h = page.get("width", 792), page.get("height", 612)
        if (w, h) not in ((792, 612), (612, 792)):
            raise ValueError("Use US Letter portrait or landscape")
        pdf.setPageSize((w, h))
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}pt" height="{h}pt" '
            f'viewBox="0 0 {w} {h}">',
            f"<title>{html.escape(page['title'])}</title>",
            f'<rect width="{w}" height="{h}" fill="white"/>',
        ]
        elements = [
            {"type": "text", "x": 30, "y": 44, "text": page["title"], "size": 18, "bold": True},
            {
                "type": "text",
                "x": 30,
                "y": 63,
                "text": page.get("subtitle", "Proposal - synthetic data"),
                "size": 9,
            },
            *page["elements"],
            {
                "type": "text",
                "x": 30,
                "y": h - 17,
                "text": f"RHP Design | Proposal | Synthetic data | {index}",
                "size": 9,
            },
        ]
        for element in elements:
            kind = element["type"]
            x, y = element["x"], element["y"]
            color = element.get("fill", "#202326")
            stroke = element.get("stroke", "#9b9b9b")
            if grayscale:
                color, stroke = gray(color), gray(stroke)
            if not 0 <= x <= w or not 0 <= y <= h:
                raise ValueError(f"Element outside page: {element}")
            if kind == "text":
                size = element.get("size", 11)
                font = "Helvetica-Bold" if element.get("bold") else "Helvetica"
                text = element["text"]
                if pdf.stringWidth(text, font, size) + x > w - 15:
                    raise ValueError(f"Text overflows page: {text}")
                pdf.setFont(font, size)
                pdf.setFillColor(HexColor(color))
                pdf.drawString(x, h - y, text)
                weight = "bold" if element.get("bold") else "normal"
                svg.append(
                    f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" '
                    f'font-size="{size}" font-weight="{weight}" fill="{color}">'
                    f"{html.escape(text)}</text>"
                )
            elif kind == "rect":
                ew, eh = element["w"], element["h"]
                if x + ew > w or y + eh > h:
                    raise ValueError("Rectangle overflows page")
                pdf.setFillColor(HexColor(color))
                pdf.setStrokeColor(HexColor(stroke))
                pdf.setDash()
                pdf.rect(x, h - y - eh, ew, eh, stroke=1, fill=1)
                svg.append(
                    f'<rect x="{x}" y="{y}" width="{ew}" height="{eh}" '
                    f'fill="{color}" stroke="{stroke}"/>'
                )
            elif kind == "line":
                x2, y2 = element["x2"], element["y2"]
                pdf.setStrokeColor(HexColor(stroke))
                pdf.setDash(3, 3) if element.get("dash") else pdf.setDash()
                pdf.line(x, h - y, x2, h - y2)
                dash = ' stroke-dasharray="3 3"' if element.get("dash") else ""
                svg.append(f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" stroke="{stroke}"{dash}/>')
            else:
                raise ValueError(f"Unknown element type: {kind}")
        svg.append("</svg>")
        Path(f"{output}-{index:02}.svg").write_text("\n".join(svg))
        pdf.showPage()
    pdf.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    book = json.loads(args.source.read_text())
    render(book, args.output)
    render(book, args.output, grayscale=True)


if __name__ == "__main__":
    main()
