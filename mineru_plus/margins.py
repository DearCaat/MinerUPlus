"""Page margins: running headers, footers, page numbers and side notes. MinerU recognises them as blocks but leaves
many out of its markdown (9 papers, 10-29: 186 headers, 153 footers, 83 page numbers, 69 side notes missing). They
are content of the paper (journal, volume, dates, DOIs, author-manuscript notices), so every one missing from the
running text is written to a closing section of full.md, page by page, keeping the running text clean.

Each is checked against the text layer of its box where the page has one (born-digital pages: the layer is the
document's own text). A margin block whose characters differ from the layer is an open issue with its page; pages
without a text layer, and logos drawn as images (no layer text in the box), are written as read and counted."""
import collections, re
import pymupdf
from .readers import mineru as MR
from .check.two_readings import toks, printed_map
from .check import dropped as DR
from .check.tables import layer_tokens
from . import layer as LY

MARGIN = ("header", "footer", "page_number", "aside_text", "page_footnote")
NAMES = {"header": "header", "footer": "footer", "page_number": "page number", "aside_text": "side note",
         "page_footnote": "page footnote"}
WS = re.compile(r"\s+")


def _same_words(lay, text):
    """the same words, the lines in another order: the layer of a side note set vertically runs its lines bottom to
    top (10-29, medRxiv: the copyright notice on every page, 24 pages reported as differing, word for word equal)"""
    norm = lambda ws: collections.Counter("".join(x for c in w for x in DR._norm_char(c)) for w in ws)
    mine = toks(printed_map(text)[0])
    return norm(w for w in lay if w.strip()) == norm(mine)


def _alnum(text):
    return "".join(c.lower() for c, _ in DR.plain_map(text) if c.isalnum())


def _outlined(pg, r, drawings):
    """glyphs drawn as curves in the box apart from its layer words: part of what the box prints is not in the layer
    (11-03, PTA-05 and PTA-10: the CellPress logo draws 'Ce' and 'Press' as curves around a layer 'll', and the
    block read 'll' matched the layer)"""
    words = [pymupdf.Rect(w[:4]) for w in LY.words(pg, r)]
    for d in drawings:
        q = pymupdf.Rect(d["rect"])
        if q.height >= 0.3 * r.height and (q & r).get_area() > 0.5 * q.get_area() and \
                any(it[0] == "c" for it in d["items"]) and not any(q.intersects(w) for w in words):
            return True
    return False


def add(pdf, mdir, md, no_layer_pages=()):
    pdf = pymupdf.open(pdf) if not isinstance(pdf, pymupdf.Document) else pdf
    pages = MR.pages(mdir)
    md_alnum = _alnum(md)
    paras = collections.Counter(_alnum(p) for p in re.split(r"\n\s*\n", md))
    used = collections.Counter()

    def already(text):
        """the reader wrote this block into the running text: a paragraph of its own, or (four words or more) inside
        one in other markup (11-02, PTA-09: the affiliation footnote of page 1 with a link). Each occurrence stands for
        one block: a running head printed on every page is not 'in the text' because a citation names the journal, and
        a logo read 'll' is no word of the text (11-02, PTA-05: the CellPress head of the odd pages was left out)"""
        k = _alnum(text)
        if k and paras[k] > used["p", k]:
            used["p", k] += 1
            return True
        if k and len(text.split()) >= 4 and md_alnum.count(k) > used["s", k]:
            used["s", k] += 1
            return True
        return False
    lines, issues, stats, drawn = [], [], collections.Counter(), {}
    for pg in sorted(pages):
        for bi, b in pages[pg]:
            if b["type"] not in MARGIN:
                continue
            text = (b.get("content") or "").strip()
            if not text:
                continue
            stats[b["type"]] += 1
            if already(text):
                stats["already in text"] += 1
                continue
            stats["written"] += 1
            lines.append(f"- p{pg} {NAMES[b['type']]}: {WS.sub(' ', text)}")
            if pg in no_layer_pages or not b.get("bbox"):
                stats["unverified (no text layer)"] += 1
                continue
            lay = layer_tokens(pdf, pg, b["bbox"])
            # printed characters on both sides: markdown escapes and tags of the block dropped, spacing ignored
            # (letter-spaced running heads split words differently on the layer)
            lc = "".join(c for w in lay for ch in w for c in DR._norm_char(ch))
            bc = "".join(c for c, _ in DR.plain_map(text))
            if len(lc) < 0.5 * len(bc):               # little or nothing on the layer there: a logo or badge drawn as an image
                                            # (10-29: the CellPress logo holds only 'll' in its box)
                stats["read from an image (little or no layer text in its box)"] += 1
                # written as read and reported: a badge's reading can be broken (11-02: 'heck k for' for the
                # 'Check for updates' badge)
                issues.append({"kind": "margin text read from an image, not checked", "page": pg, "block": bi,
                               "type": b["type"], "text": text, "layer": " ".join(lay)[:500]})
                continue
            page = LY.page(pdf, pg - 1)
            box = pymupdf.Rect(b["bbox"][0] * page.rect.width, b["bbox"][1] * page.rect.height,
                               b["bbox"][2] * page.rect.width, b["bbox"][3] * page.rect.height) * page.derotation_matrix
            if pg not in drawn:
                drawn[pg] = page.get_drawings()
            if _outlined(page, box, drawn[pg]):
                stats["read from an image (glyphs drawn as curves beside the layer text in its box)"] += 1
                issues.append({"kind": "margin text read from an image, not checked", "page": pg, "block": bi,
                               "type": b["type"], "text": text, "layer": " ".join(lay)[:500]})
                continue
            if lc == bc or _same_words(lay, text):
                stats["equal to the text layer"] += 1
            else:
                stats["differs from the text layer"] += 1
                issues.append({"kind": "margin text differs from the text layer", "page": pg, "block": bi,
                               "type": b["type"], "text": text, "layer": " ".join(lay)[:500]})
    # the same margin text differing the same way on many pages is one finding (a running head or logo)
    grouped = {}
    for i in issues:
        g = grouped.setdefault((i["type"], i["text"], i["layer"]), {**i, "pages": []})
        g["pages"].append(i["page"])
    issues = [{k: v for k, v in g.items() if k not in ("page", "block")} for g in grouped.values()]
    if lines:
        md = md.rstrip("\n") + "\n\n## Page headers, footers and page numbers\n\n" + "\n".join(lines) + "\n"
    return md, dict(stats), issues
