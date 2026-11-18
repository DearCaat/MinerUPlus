"""Where each issue handed on is, on the page and in full.md, for whoever settles it (11-18 文浩, on issues given
without a crop: 「没有roi我都不知道在哪」).

Of the 273 issues of 26 parses (0.5.10) about a hundred had no crop: text only the primary read, text-layer words
outside every block, disagreements whose passage was not found once in its block, margin text, spaced words. And an
issue's quoted strings are those of the check that raised it, read before later steps wrote into the text (11-18
arbitration: the paper line's full.md already printed the ',' an issue still called '.'), so the stretch of full.md
printed at the place is given with it: that is the text an edit changes.

Each issue gets "roi": [{"page", "box" (the page normalised 0-1), "crop", "placed_by", "md"}] for its places, or
"roi": null and "roi_missing" with the reason. The place is, in this order:
  the check's own box      (confirm._places: the dropped record, the disagreement's or the unread run's box, the
                            table's or equation's block, the margin blocks)
  the issue's block        a block or nested caption the issue names, its whole box
  the text layer's words   the issue's layer words or quoted text found as consecutive words of the page's text
                           layer, once
Nothing is guessed: a string found in more than one place gives no place."""
import re
from pathlib import Path
import pymupdf
from .. import layer as LY
from ..readers import mineru as MR
from . import confirm as CF
from .coverage import INVISIBLE

QUOTES = ("layer_words", "layer", "text", "primary", "parse")


def _norm_box(pg, r):
    """a rectangle in unrotated page coordinates as a box of the displayed page, normalised"""
    d = r * pg.rotation_matrix
    W, H = pg.rect.width, pg.rect.height
    return [round(d.x0 / W, 4), round(d.y0 / H, 4), round(d.x1 / W, 4), round(d.y1 / H, 4)]


def _block(D, doc, issue):
    page, uid = issue.get("page"), issue.get("block")
    if issue.get("kind") == "disagreement" and issue.get("id") in D["dis"]:
        d = D["dis"][issue["id"]]
        page, uid = d.get("page"), (d.get("blocks") or [None])[0]
    if not isinstance(page, int) or uid is None or page not in D["pages"]:
        return None
    part = next((b for u, _, b in MR.units(D["pages"][page]) if str(u) == str(uid)), None)
    if not part or not part.get("bbox"):
        return None
    return [(page, CF._rect_norm(LY.page(doc, page - 1), part["bbox"]), True, None)]


def _boxes(doc, issue):
    """the boxes the check gave for the layer words (coverage: words outside every block), one place per line"""
    page, nbs = issue.get("page"), issue.get("layer_boxes")
    if not isinstance(page, int) or not nbs or not 1 <= page <= len(doc):
        return None
    pg = LY.page(doc, page - 1)
    lines = []
    for nb in sorted(nbs, key=lambda b: (b[1], b[0])):
        r = CF._rect_norm(pg, nb)
        if lines and min(lines[-1].y1, r.y1) - max(lines[-1].y0, r.y0) > 0.5 * min(lines[-1].height, r.height):
            lines[-1] |= r
        else:
            lines.append(r)
    return [(page, r, True, None) for r in lines]


def _key(s):
    return "".join(c.lower() for c in s if c.isalnum())


def _bare(s):
    return INVISIBLE.sub("", s).strip()


def _layer_words(doc, issue):
    page = issue.get("page")
    if not isinstance(page, int) or not 1 <= page <= len(doc):
        return None
    pg = LY.page(doc, page - 1)
    ws = [(w[4], pymupdf.Rect(w[:4])) for w in LY.words(pg)]
    for k in QUOTES:
        q = issue.get(k)
        q = " ".join(q) if isinstance(q, list) else q
        if not isinstance(q, str) or not q.strip():
            continue
        toks = q.split()
        # words of letters or digits compared by those; a run of marks ('__________', '|') as written, without the
        # spaces and zero-width characters a layer word carries ('| ')
        keys = [_key(t) or _bare(t) for t in toks]
        wkeys = [_key(t) or _bare(t) for t, _ in ws]
        hits = [i for i in range(len(ws) - len(keys) + 1) if wkeys[i:i + len(keys)] == keys]
        if len(hits) == 1:
            r = pymupdf.Rect(ws[hits[0]][1])
            for _, b in ws[hits[0]:hits[0] + len(keys)]:
                r |= b
            return [(page, r, True, None)]
        if len(hits) > 1:
            return "several places"
    return None


def attach(out, pdf, issues, work):
    """issues with roi set; returns the counts of how they were placed"""
    out, work = Path(out), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    D, doc = CF._load(out), pymupdf.open(pdf)
    counts = {}
    for n, issue in enumerate(issues):
        how, places = "the check's own box", None
        try:
            places = CF._places(D, doc, issue)
        except (KeyError, TypeError, ValueError):
            places = None
        if not places:
            how, places = "the issue's block", _block(D, doc, issue)
        if not places:
            how, places = "the check's boxes of the layer words", _boxes(doc, issue)
        if not places:
            how, places = "the text layer's words", _layer_words(doc, issue)
        own = issue.get("crop") or (issue.get("crops") or [None])[0]
        if (not places or isinstance(places, str)) and own:
            # the check's own crop without a box (accents in a formula)
            issue["roi"] = [{"page": issue.get("page"), "box": None, "crop": own, "placed_by": "the check's crop",
                             "md": None}]
            counts["the check's crop"] = counts.get("the check's crop", 0) + 1
            continue
        if not places or isinstance(places, str):
            issue["roi"] = None
            issue["roi_missing"] = ("its words are on the page in several places" if places == "several places"
                                    else "no box, block or text-layer words of it found")
            counts["not placed"] = counts.get("not placed", 0) + 1
            continue
        roi = []
        for j, (page, r, mark, at_md) in enumerate(places):
            pg = LY.page(doc, page - 1)
            st = CF.text_at(D, doc, issue, page, r, mark, at_md)
            roi.append({"page": page, "box": _norm_box(pg, r),
                        "crop": CF._crop(doc, page, r, mark, work / f"i{n}.{j}.png"), "placed_by": how,
                        "md": D["md"][st[0]:st[1]] if st else None})
        issue["roi"] = roi
        counts[how] = counts.get(how, 0) + 1
    return counts
