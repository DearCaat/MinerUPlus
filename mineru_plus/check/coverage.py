"""Coverage of the text layer: on born-digital pages the text layer is the document's own text, so every layer word
should appear in the primary reading. Each layer word is assigned to the reader block whose box holds its centre;
per block, layer characters the block's text lacks are content the reader dropped. Layer words in no block are a
region the reader missed. Words inside figures and charts are out of scope (figure-internal text). Whitespace and the
split of words are ignored (letter-spaced fonts split words on the layer). Counts and findings only."""
import collections, html, re, unicodedata
import pymupdf
from ..readers import mineru as MR
from .tables import cell_toks
from . import two_readings as TR
from .. import layer as LY

FIGURE = {"image", "chart"}
HY = "-\u2010\u2011\u00ad"
INVISIBLE = re.compile("[\u00ad\ufeff\u200b\u200c\u200d\u2060]")   # soft hyphen, BOM, zero-width: never printed


def _norm_box(r, pg):
    W, H = pg.rect.width, pg.rect.height
    return (r.x0 / W, r.y0 / H, r.x1 / W, r.y1 / H)


def _inside(c, b, pad=0.003):
    return b[0] - pad <= c[0] <= b[2] + pad and b[1] - pad <= c[1] <= b[3] + pad


def _parts(b):
    """A block and its nested captions / footnotes, each with its own box and text."""
    out = [(b["type"], b.get("bbox"), b.get("content") or "")]
    for k in ("captions", "footnotes"):
        for c in b.get(k) or []:
            out.append((b["type"] + "_" + k[:-1], c.get("bbox"), c.get("content") or ""))
    return out


def chars(ts):
    return collections.Counter("".join(ts))


def text_chars(s):
    """characters of a text as printed: LaTeX as the symbols it prints, typographic variants unified, and NFKD, so a
    precomposed letter matches a layer that stores the base letter and its accent as separate glyphs"""
    s = " ".join(cell_toks(TR.latex_plain(html.unescape(s))))
    s = unicodedata.normalize("NFKD", s.translate(TR.VARIANT))
    s = LEADER.sub("", s)
    return collections.Counter(c for c in s if not c.isspace() and not "\ue000" <= c <= "\uf8ff")


# private-use code points (symbol-font bullets and glyphs, U+E000-U+F8FF) carry no standard meaning: not compared
# dot leaders of a table of contents ('Methods ........ 12'): filler whose length the reader does not keep
LEADER = re.compile(r"(?:[.…·]\s*){3,}")
# the primary writes these as their ASCII look-alikes (en dash as hyphen, middle dot as period): a code-point loss,
# counted per document, not content dropped
FLAT = {"–": "-", "—": "-", "−": "-", "‒": "-", "‐": "-", "‑": "-", "·": "."}


def check(pdf_path, primary_dir, edits=()):
    """edits: the repair's edits ({page, old, new}); each is applied to the block it explains before comparing, so a
    character the repair restored is not reported again"""
    by_page = collections.defaultdict(list)
    for e in edits:
        by_page[e["page"]].append(e)
    pdf = pymupdf.open(pdf_path)
    A = MR.pages(primary_dir)
    pages, total = [], collections.Counter()
    for pg_no in sorted(A):
        pg = LY.page(pdf, pg_no - 1)
        words = LY.words(pg)
        if not words:
            continue
        # a hyphen ending the last word of a line is the line break's, not content the reader must keep
        last = {}
        for k, w in enumerate(words):
            last[(w[5], w[6])] = k
        words = [w[:4] + (w[4][:-1] if k == last[(w[5], w[6])] and w[4][-1:] in HY and len(w[4]) > 1 else w[4],) + w[5:]
                 for k, w in enumerate(words)]
        words = [w[:4] + (INVISIBLE.sub("", w[4]),) + w[5:] for w in words]
        words = [w for w in words if w[4]]
        parts = [(bi, t, bb, txt) for bi, b in A[pg_no] for t, bb, txt in _parts(b) if bb]
        figs = [bb for _, t, bb, _ in parts if t in FIGURE]
        text_parts = [p for p in parts if p[1] not in FIGURE]
        got = collections.defaultdict(list); loose = []
        for w in words:
            r = pymupdf.Rect(w[:4]) * pg.rotation_matrix
            nb = _norm_box(r, pg); c = ((nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2)
            hits = [p for p in text_parts if _inside(c, p[2])]
            if hits:
                h = min(hits, key=lambda p: (p[2][2] - p[2][0]) * (p[2][3] - p[2][1]))
                got[(h[0], h[1])].append(w[4])
            elif not any(_inside(c, f) for f in figs):
                loose.append(w[4])
        findings = []
        cmp = {}
        for (bi, t), ws in got.items():
            if t == "equation":
                continue                       # LaTeX against math-font glyphs: not comparable as characters
            cmp[(bi, t)] = [text_chars(" ".join(ws)), " ".join(p[3] for p in text_parts if p[0] == bi and p[1] == t)]
        for e in by_page.get(pg_no, []):
            need = text_chars(e["new"]) - text_chars(e["old"])
            for k, (lay, txt) in cmp.items():
                if e["old"] in txt and need & (lay - text_chars(txt)):
                    cmp[k][1] = txt.replace(e["old"], e["new"], 1)
                    break
        for (bi, t), (lay, txt) in cmp.items():
            have = text_chars(txt)
            missing, extra = lay - have, have - lay
            for c in list(missing):
                if c in FLAT and extra[FLAT[c]]:
                    k = min(missing[c], extra[FLAT[c]])
                    missing[c] -= k; extra[FLAT[c]] -= k; total["written_as_ascii"] += k
                    total["ascii_" + c] += k
            missing = +missing
            n = sum(missing.values())
            if n:
                findings.append({"block": bi, "type": t, "missing_chars": n, "missing": "".join(sorted(missing.elements()))})
                total["missing_chars"] += n
        if loose:
            findings.append({"block": None, "type": "outside every block", "layer_words": loose[:60], "count": len(loose)})
            total["outside_words"] += len(loose)
        total["layer_words"] += len(words)
        if findings:
            pages.append({"page": pg_no, "findings": findings})
    # the same characters missing on many pages are one omission repeated (a running header or footer)
    seen = collections.defaultdict(list)
    for pg in pages:
        for f in pg["findings"]:
            if f.get("missing"):
                seen[f["missing"]].append(pg["page"])
    repeated = {m: ps for m, ps in seen.items() if len(set(ps)) >= 3}
    for pg in pages:
        pg["findings"] = [f for f in pg["findings"] if f.get("missing") not in repeated]
    pages = [pg for pg in pages if pg["findings"]]
    rep = [{"missing": m, "pages": sorted(set(ps)), "blocks": len(ps)} for m, ps in repeated.items()]
    return {"totals": dict(total), "pages": pages, "repeated": rep}
