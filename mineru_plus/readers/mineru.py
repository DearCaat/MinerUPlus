"""Primary reader. The reader is a backend (mineru_plus/backends), chosen in the config file under "primary_reader";
this module holds the accessors the checks use on its output: pages, units, blocks, markdown and figure bodies.

On born-digital pages the primary reader copies the PDF text layer into its text blocks (planted test 10-28: 47 of 47
shifted numbers in text blocks came from a hidden layer); figure and chart regions are read from the image."""
import json
from pathlib import Path
from .. import backends


def read(pdf, out_dir):
    out_dir = Path(out_dir)
    if (out_dir / "structured_content.json").exists():
        return json.loads((out_dir / "reader_meta.json").read_text())
    return backends.get("primary_reader").read(Path(pdf), out_dir)


def markdown(out_dir):
    d = Path(out_dir)
    for name in ("full.md", "markdown.md"):
        if (d / name).exists():
            return (d / name).read_text(errors="ignore")
    return next(d.glob("*.md")).read_text(errors="ignore")


def pages(out_dir):
    """structured_content pages: {page: [(block index, block), ...]}"""
    s = json.loads((Path(out_dir) / "structured_content.json").read_text())
    return {p["page_idx"] + 1: list(enumerate(p["blocks"])) for p in s["pages"]}


def units(page_blocks):
    """a page's texts with nested captions and footnotes as units of their own: [(uid, type, part)]. uid is the block
    index, or 'i.captions.k' / 'i.footnotes.k' for a part nested in block i; type of a nested part is the block type
    with _caption / _footnote; part is the dict holding content and bbox"""
    out = []
    for i, b in page_blocks:
        out.append((i, b["type"], b))
        for k in ("captions", "footnotes"):
            for j, c in enumerate(b.get(k) or []):
                out.append((f"{i}.{k}.{j}", b["type"] + "_" + k[:-1], c))
    return out


def unit(page_blocks, uid):
    """(type, part) of one unit of a page"""
    for u, t, b in units(page_blocks):
        if u == uid:
            return t, b
    raise KeyError(uid)


def blocks(out_dir):
    """Blocks of structured_content.json as (page, type, bbox, text); bbox normalised to the page (0-1)."""
    return [{"page": pg, "order": i, "type": b["type"], "sub_type": b.get("sub_type"), "bbox": b.get("bbox"),
             "text": b.get("content") or ""} for pg, bl in pages(out_dir).items() for i, b in bl]


def figure_bodies(out_dir):
    """What the reader declares as the body of a figure or chart (middle_json image_body / chart_body) and the
    text it generated for it: a transcription of the graphic (mermaid, chart values), not running text. A reader
    that writes no middle_json.json declares none."""
    path = Path(out_dir) / "middle_json.json"
    if not path.exists():
        return []
    m = json.loads(path.read_text())
    res = []

    def walk(o, page):
        if isinstance(o, dict):
            if o.get("type") in ("image_body", "chart_body") and isinstance(o.get("content"), str) and o["content"].strip():
                res.append({"page": page, "type": o["type"], "bbox": o.get("bbox"),
                            "image_path": o.get("image_path"), "text": o["content"]})
            for v in o.values():
                walk(v, page)
        elif isinstance(o, list):
            for v in o:
                walk(v, page)
    for pg in m["pages"]:
        walk(pg["blocks"], pg["page_idx"] + 1)
    return res
