"""Render a Markdown file to PDF, styled to match the app's warm-earth palette.
Pure Python — uses `markdown` for HTML conversion and `xhtml2pdf` for PDF.

Usage:
    python scripts/_md_to_pdf.py docs/USER_GUIDE.md docs/USER_GUIDE.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown
from xhtml2pdf import pisa


CSS = """
@page { size: A4; margin: 22mm 18mm 22mm 18mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt;
       color: #3a2418; line-height: 1.45; }
h1 { font-family: "Times New Roman", Georgia, serif; color: #6f3a23;
     font-size: 22pt; margin: 0 0 6pt; border-bottom: 1.2pt solid #c89759;
     padding-bottom: 4pt; }
h2 { font-family: "Times New Roman", Georgia, serif; color: #a85a3a;
     font-size: 15pt; margin: 18pt 0 6pt; }
h3 { font-family: "Times New Roman", Georgia, serif; color: #6f3a23;
     font-size: 12pt; margin: 14pt 0 4pt; }
p, ul, ol { margin: 4pt 0 6pt; }
li { margin: 1pt 0; }
code { font-family: "Courier New", monospace; font-size: 9.5pt;
       background: #f2e1cf; padding: 1pt 3pt; border-radius: 2pt;
       color: #6f3a23; }
pre { background: #ece2c9; padding: 6pt 8pt; border-left: 2pt solid #c89759;
      font-family: "Courier New", monospace; font-size: 9pt;
      white-space: pre-wrap; margin: 6pt 0 8pt; }
blockquote { border-left: 2pt solid #c89759; padding: 4pt 10pt; margin: 6pt 0;
             background: #f5ecd9; color: #7c6650; font-style: italic; }
table { border-collapse: collapse; margin: 6pt 0 10pt; font-size: 9.5pt; }
th, td { border: 0.5pt solid #d8c4a4; padding: 3pt 6pt; }
th { background: #ece2c9; color: #6f3a23; }
strong { color: #6f3a23; }
hr { border: 0; border-top: 0.5pt solid #d8c4a4; margin: 12pt 0; }
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{body}
</body></html>"""


def convert(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        text,
        extensions=["fenced_code", "tables", "sane_lists"],
    )
    full_html = HTML_TEMPLATE.format(css=CSS, body=html_body)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with pdf_path.open("wb") as out:
        result = pisa.CreatePDF(src=full_html, dest=out, encoding="utf-8")
    if result.err:
        raise SystemExit(f"PDF generation failed with {result.err} error(s)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: _md_to_pdf.py <input.md> <output.pdf>")
        sys.exit(2)
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"wrote {sys.argv[2]}")
