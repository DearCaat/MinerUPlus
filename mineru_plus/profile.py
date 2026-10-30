"""Page profile from the PDF itself: what each page offers as evidence.

Counts read from the PDF only; no thresholds. Whether a page's text layer can be trusted is decided later by how well it agrees with an
independent visual reading of the same page (check.align), not by rules on single glyphs: a glyph such as
'¼' is a fault on one font (mako) and a correct character elsewhere.
"""
import pymupdf
from . import layer as LY


def profile(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages = []
    for i in range(doc.page_count):
        pg = LY.page(doc, i)
        t = LY.text(pg)
        words = len(t.split())
        pages.append({
            "page": pg.number + 1,
            "size": [round(pg.rect.width, 1), round(pg.rect.height, 1)],
            "rotation": pg.rotation,
            "words": words,
            "images": len(pg.get_images()),
            "private_use_glyphs": sum("\ue000" <= c <= "\uf8ff" for c in t),
            "replacement_chars": t.count("\ufffd"),
        })
    meta = doc.metadata or {}
    return {"pages": pages, "n_pages": len(pages),
            "pages_without_text_layer": [p["page"] for p in pages if p["words"] == 0],
            "producer": meta.get("producer"), "creator": meta.get("creator")}
