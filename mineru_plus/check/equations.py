"""Display-equation check. MinerU and OXR both write LaTeX from the page image; spellings of the same formula differ
(spacing, braces, \\mathrm vs \\text, \\log vs log, \\tag{1} vs (1)), so both are reduced to a canonical string first.
Where they still differ, or OXR has no reading, the text layer inside the equation box is a third reading on
born-digital pages: when its letters and digits are those MinerU's LaTeX prints (as a multiset: a layer does not keep
the two-dimensional order of a formula), the characters are confirmed, not the layout. 10-29, 29 display equations in
31 documents: 18 equal OXR, 1 differed only by \\tag, 10 were figure labels OXR did not read as formulas."""
import collections, difflib, re, unicodedata
import pymupdf
from .. import layer as LY
from ..readers import mineru as MR, oxr as OX
from .two_readings import latex_plain

TAG = re.compile(r"\\tag\s*\{([^}]*)\}")
# two readings are the same only where every step of the canonical spelling provably keeps what LaTeX prints
# (latex_canon.py, 11-18; the regular expressions before it took out braces, fonts and the backslash of \max, and so
# read \frac{ab}{c} as \frac{a}{bc}, x as \mathbf{x} and max as \max)
from .latex_canon import canon


def _alnum(s):
    return collections.Counter(c for c in unicodedata.normalize("NFKC", s) if c.isalnum())


def printed(latex):
    """letters and digits a LaTeX formula prints: symbols as characters, command names dropped"""
    x = latex_plain(TAG.sub(r"(\1)", latex or ""))
    return _alnum(re.sub(r"\\[A-Za-z]+", " ", x))


def check(primary_dir, oxr_dir, pdf_path=None, layer_pages=()):
    A, B = MR.pages(primary_dir), OX.pages(oxr_dir)
    pdf = pymupdf.open(pdf_path) if pdf_path else None
    res = []
    for pg in sorted(A):
        me = [(bi, b) for bi, b in A[pg] if b["type"] == "equation"]
        oe = [b["content"] for b in B.get(pg, []) if b["type"] == "Formula"]
        oc = [canon(o) for o in oe]
        used = set()
        for bi, b in me:
            ca = canon(b.get("content"))
            ka = ca if ca is not None else (b.get("content") or "")   # pairing only; None never counts as same
            best, r = None, 0.0
            for j, o in enumerate(oe):
                q = difflib.SequenceMatcher(None, ka, oc[j] if oc[j] is not None else (o or ""), autojunk=False).ratio()
                if j not in used and q > r:
                    best, r = j, q
            item = {"page": pg, "block": bi, "bbox": b.get("bbox"), "mineru": b.get("content")}
            if ca == "":
                item.update(status="empty equation")             # a box read as an equation that prints nothing
            elif best is None or r < 0.5:
                item.update(status="no OXR reading")
            else:
                used.add(best)
                same = ca is not None and ca == oc[best]
                item.update(oxr=oe[best], status="same" if same else "differ")
                if ca is None or oc[best] is None:
                    item["latex_not_printable"] = [n for n, c in (("mineru", ca), ("oxr", oc[best])) if c is None]
            if item["status"] != "same" and pdf is not None and pg in layer_pages and b.get("bbox"):
                page = LY.page(pdf, pg - 1); W, H = page.rect.width, page.rect.height; x0, y0, x1, y1 = b["bbox"]
                clip = pymupdf.Rect(x0 * W - 2, y0 * H - 2, x1 * W + 2, y1 * H + 2) * page.derotation_matrix
                lay = _alnum("".join(w[4] for w in LY.words(page, clip)))
                item["layer"] = "".join(sorted(lay.elements()))
                # a hint for whoever looks, not a confirmation: the layer keeps no two-dimensional order, so the same
                # letters and digits are also those of x_2 for x^2 or b/a for a/b (11-18, rule 执-1)
                item["layer_letters_and_digits_equal"] = bool(lay) and lay == printed(b.get("content"))
            res.append(item)
    return res
