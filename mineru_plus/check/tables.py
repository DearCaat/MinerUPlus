"""Table check by three readings. MinerU and OXR both recognise tables from the page image (neither copies the text
layer here), so on born-digital pages the text layer inside the table box is a third, independent reading.

- characters: tokens of the MinerU table against the text-layer words inside its box (multiset difference). A token
  MinerU writes that the layer does not have, or the reverse, is a disagreement; OXR's cells say which side it takes.
- structure: MinerU and OXR grids (spans expanded) aligned row by row; rows or cells that differ are disagreements.
Counts and disagreements only; nothing here decides which reading is right.
"""
import collections, difflib, html, re, unicodedata
from html.parser import HTMLParser
import pymupdf
from ..readers import mineru as MR, oxr as OX
from .two_readings import toks
from .. import layer as LY

LATEX = {r"\pm": "±", r"\times": "×", r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\%": "%",
         r"\cdot": "·", r"\sim": "~", r"\approx": "≈", r"\mu": "μ", r"\alpha": "α", r"\beta": "β", r"\chi": "χ",
         r"\kappa": "κ", r"\dagger": "†", r"\ddagger": "‡", r"\to": "→", r"\rightarrow": "→", r"\infty": "∞",
         r"\lt": "<", r"\gt": ">", r"\ast": "*", r"\circ": "°", r"\%": "%"}
CMD = re.compile(r"\\(?:mathrm|text|textbf|mathbf|operatorname|left|right|mathit|textit|boldsymbol)\b")
PURE_MARKUP = re.compile(r"[$^{}_\\*]+")


def cell_toks(s):
    s = html.unescape(s)
    for k in sorted(LATEX, key=len, reverse=True):
        s = s.replace(k, " " + LATEX[k] + " ")
    s = CMD.sub(" ", s)
    return [t for t in toks(s) if not PURE_MARKUP.fullmatch(t)]


class _Grid(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows, self.cell, self.span = [], None, (1, 1)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            if not self.rows:
                self.rows.append([])
            self.cell, self.span = [], (int(a.get("rowspan") or 1), int(a.get("colspan") or 1))

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.rows[-1].append(("".join(self.cell), self.span)); self.cell = None

    def handle_data(self, d):
        if self.cell is not None:
            self.cell.append(d)


def cells(content):
    """Each source cell once (for token counts; grid() repeats spanned cells)."""
    content = content or ""
    if "<table" in content:
        p = _Grid(); p.feed(content)
        return [t for r in p.rows for t, _ in r]
    return [c for r in grid(content) for c in r]


def grid(content):
    """Rows of cell strings with row/col spans expanded (a spanned cell repeats its text)."""
    content = content or ""
    if "<table" in content:
        p = _Grid(); p.feed(content)
        out, carry = [], {}
        for r, row in enumerate(p.rows):
            line, c, it = [], 0, iter(row)
            while True:
                if (r, c) in carry:
                    line.append(carry.pop((r, c))); c += 1; continue
                nxt = next(it, None)
                if nxt is None:
                    break
                text, (rs, cs) = nxt
                for dc in range(cs):
                    line.append(text)
                    for dr in range(1, rs):
                        carry[(r + dr, c + dc)] = text
                c += cs
            while (r, c) in carry:
                line.append(carry.pop((r, c))); c += 1
            out.append(line)
        return out
    rows = []
    for l in content.splitlines():
        l = l.strip()
        if not l.startswith("|") or re.fullmatch(r"\|[\s:|-]+\|?", l):
            continue
        rows.append([c.strip() for c in re.split(r"(?<!\\)\|", l.strip("|"))])
    return rows


def norm_rows(g):
    return [[" ".join(cell_toks(c)) for c in r] for r in g if any(cell_toks(c) for c in r)]


def compare_structure(ga, gb):
    A, B = norm_rows(ga), norm_rows(gb)
    out = {"rows": [len(A), len(B)], "cols": [max(map(len, A), default=0), max(map(len, B), default=0)], "diffs": []}
    head = A[0] if A else []
    sm = difflib.SequenceMatcher(None, ["|".join(r) for r in A], ["|".join(r) for r in B], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            for ra, rb, i in zip(A[i1:i2], B[j1:j2], range(i1, i2)):
                if len(ra) != len(rb):
                    out["diffs"].append({"what": "row shape", "row": i, "mineru": ra, "oxr": rb})
                    continue
                for c, (x, y) in enumerate(zip(ra, rb)):
                    if x != y:
                        out["diffs"].append({"what": "cell", "row": i, "col": c, "row_label": ra[0] if ra else "",
                                             "col_label": head[c] if c < len(head) else "", "mineru": x, "oxr": y})
        else:
            for i in range(i1, i2):
                out["diffs"].append({"what": "row only in MinerU", "row": i, "mineru": A[i]})
            for j in range(j1, j2):
                out["diffs"].append({"what": "row only in OXR", "row_oxr": j, "oxr": B[j]})
    return out


def layer_tokens(pdf, page, bbox, pad=0.005):
    pg = LY.page(pdf, page - 1); W, H = pg.rect.width, pg.rect.height
    x0, y0, x1, y1 = bbox
    r = pymupdf.Rect((x0 - pad) * W, (y0 - pad) * H, (x1 + pad) * W, (y1 + pad) * H)
    r = r * pg.derotation_matrix            # reader boxes are on the displayed page; words are unrotated
    return toks(" ".join(w[4] for w in LY.words(pg, r)))


def check(pdf_path, primary_dir, oxr_dir):
    pdf = pymupdf.open(pdf_path)
    A, B = MR.pages(primary_dir), OX.pages(oxr_dir)
    res = []
    for pg in sorted(A):
        otabs = [b for b in B.get(pg, []) if b["type"] == "Table"]
        for bi, b in A[pg]:
            if b["type"] != "table":
                continue
            ga = grid(b.get("content"))
            ta = [t for c in cells(b.get("content")) for t in cell_toks(c)]
            item = {"page": pg, "block": bi, "bbox": b.get("bbox"), "rows": len(ga), "tokens": len(ta)}
            # characters against the text layer
            lt = layer_tokens(pdf, pg, b["bbox"]) if b.get("bbox") else []
            if lt:
                ca, cl = collections.Counter(ta), collections.Counter(lt)
                ma, ml = sorted((ca - cl).elements()), sorted((cl - ca).elements())
                # characters, whitespace ignored: a word the layer splits (letter-spaced fonts) is not a difference
                ch = lambda ts: collections.Counter("".join(ts))
                item["layer"] = {"tokens": len(lt), "mineru_not_on_layer": ma, "layer_not_in_mineru": ml,
                                 "chars_mineru_not_on_layer": dict(ch(ma) - ch(ml)),
                                 "chars_layer_not_in_mineru": dict(ch(ml) - ch(ma))}
            else:
                item["layer"] = None
            # structure against OXR (the OXR table on this page sharing most tokens)
            best, bj = None, 0.0
            for ob in otabs:
                to = collections.Counter(t for c in cells(ob["content"]) for t in cell_toks(c))
                j = sum((collections.Counter(ta) & to).values()) / max(1, sum((collections.Counter(ta) | to).values()))
                if j > bj:
                    best, bj = ob, j
            if best is not None and bj >= 0.3:
                gb = grid(best["content"])
                tb = collections.Counter(t for c in cells(best["content"]) for t in cell_toks(c))
                item["oxr"] = {"token_overlap": round(bj, 3), **compare_structure(ga, gb)}
                if item["layer"]:
                    cl = collections.Counter(lt)
                    item["layer"]["oxr_not_on_layer"] = sorted((tb - cl).elements())
            else:
                item["oxr"] = None
            res.append(item)
    return res
