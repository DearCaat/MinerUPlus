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

WRAP = re.compile(r"\\(?:mathrm|text|textrm|textit|mathit|operatorname|mathbf|boldsymbol|textbf|left|right|displaystyle)\b")
SPACE = re.compile(r"\\[,;:! ]|\\quad|\\qquad|~|\s+")
FUNC = re.compile(r"\\(log|ln|exp|min|max|sin|cos|tan|arg|det|lim|sup|inf|Pr)\b")
TAG = re.compile(r"\\tag\s*\{([^}]*)\}")


def canon(s):
    s = TAG.sub(r"(\1)", s or "")
    s = WRAP.sub("", s)
    s = FUNC.sub(r"\1", s)
    s = SPACE.sub("", s)
    return s.replace("{", "").replace("}", "")


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
        used = set()
        for bi, b in me:
            ca = canon(b.get("content"))
            best, r = None, 0.0
            for j, o in enumerate(oe):
                q = difflib.SequenceMatcher(None, ca, canon(o), autojunk=False).ratio()
                if j not in used and q > r:
                    best, r = j, q
            item = {"page": pg, "block": bi, "bbox": b.get("bbox"), "mineru": b.get("content")}
            if best is None or r < 0.5:
                item.update(status="no OXR reading")
            else:
                used.add(best)
                item.update(oxr=oe[best], status="same" if ca == canon(oe[best]) else "differ")
            if item["status"] != "same" and pdf is not None and pg in layer_pages and b.get("bbox"):
                page = LY.page(pdf, pg - 1); W, H = page.rect.width, page.rect.height; x0, y0, x1, y1 = b["bbox"]
                clip = pymupdf.Rect(x0 * W - 2, y0 * H - 2, x1 * W + 2, y1 * H + 2) * page.derotation_matrix
                lay = _alnum("".join(w[4] for w in LY.words(page, clip)))
                item["layer"] = "".join(sorted(lay.elements()))
                if lay and lay == printed(b.get("content")):
                    item["status"] = "characters equal the text layer"
            res.append(item)
    return res
