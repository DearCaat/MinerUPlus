"""Words the primary reading dropped, restored where two other readings agree.

The text layer of a born-digital page is the document's own text; OXR reads the page image. Where the layer has a run
of tokens between two neighbouring tokens of one primary block and the primary has nothing there, and OXR has the
same run between the same neighbours (up to three tokens of the block on each side; its dash and middle-dot flattening allowed), two independent readings agree
against the primary. 10-28, 9 papers: 11 such runs (7 compound hyphens at line breaks, 'vs', an em dash, a period);
the citation superscripts the primary drops are not in OXR either and stay coverage issues.

Each run becomes a disagreement in the schema of two_readings.compare with the layer as the second reading, the two
neighbours as anchors. settle() sends a lone hyphen at a line break to the spelling question like any other
line-break item; the rest is written as the layer prints it (route 'omission')."""
import difflib, re
import pymupdf
from ..readers import mineru as MR, oxr as OX
from .two_readings import pos_in_block, toks, latex_plain, PRIMARY_PROSE, OXR_PROSE, FLAT, MARKUP
from .. import layer as LY

PURE_MARKUP = re.compile(r"[$^{}_\\]+")


def _flat(ts):
    return [t.translate(FLAT) for t in ts]


def _has(seq, sub):
    n = len(sub)
    return any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def find(pdf, primary_dir, oxr_dir):
    A, B = MR.pages(primary_dir), OX.pages(oxr_dir)
    doc = pymupdf.open(pdf)
    out = []
    for pg in sorted(set(A) & set(B)):
        a = []
        for bi, typ, b in MR.units(A[pg]):
            if typ in PRIMARY_PROSE:
                a += [(t, bi) for t in toks(latex_plain(b.get("content") or ""))]
        at = [t for t, _ in a]
        bt = _flat(toks(latex_plain(" ".join(x.get("content") or "" for x in B[pg] if x["type"] in OXR_PROSE))))
        lt, lw = [], []                     # layer tokens and the layer word each comes from
        words = LY.words(LY.page(doc, pg - 1))
        for k, w in enumerate(words):
            for t in toks(w[4]):
                lt.append(t); lw.append(k)
        # a word ending in a hyphen at the end of its line continues on the next line without a space
        joins = {k for k, (w, nx) in enumerate(zip(words, words[1:]))
                 if w[4][-1:] in "-\u2010\u2011" and (w[5], w[6]) != (nx[5], nx[6])}
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, at, lt, autojunk=False).get_opcodes():
            if op != "insert" or i1 == 0 or i1 >= len(at) or a[i1 - 1][1] != a[i1][1]:
                continue
            ins, anchors = lt[j1:j2], [at[i1 - 1], at[i1]]
            if any(PURE_MARKUP.fullmatch(t) or MARKUP.search(t) for t in ins + anchors):
                continue
            # the run must sit between the same neighbours in all three readings: up to three tokens of the block on
            # each side. Two anchors alone are not enough: on a page whose layer runs in another order the aligner
            # paired 'of | the' with a run from elsewhere on the page (10-28, a reporting-summary form)
            bi0 = a[i1][1]
            L = [t for t, u in a[max(0, i1 - 3):i1] if u == bi0]
            R = [t for t, u in a[i1:i1 + 3] if u == bi0]
            want = _flat(L + ins + R)
            if not (_has(bt, want) and _has(_flat(lt), want)):
                continue
            # the run as printed: tokens of one layer word are joined, a new layer word starts after a space
            sep = lambda prev, k: "" if k == prev or prev in joins else " "
            text, prev = "", lw[j1 - 1] if j1 else None
            for t, k in zip(ins, lw[j1:j2]):
                text += sep(prev, k) + t; prev = k
            text += sep(prev, lw[j2]) if j2 < len(lw) else " "
            bi = a[i1][1]; typ, blk = MR.unit(A[pg], bi)
            out.append({"kind": "content", "source": "text layer and OXR", "page": pg, "blocks": [bi],
                        "bbox": blk.get("bbox"), "block_type": typ, "pos_in_block": pos_in_block(a, i1),
                        "primary": " ".join(anchors), "oxr": " ".join([anchors[0]] + ins + [anchors[1]]),
                        "primary_toks": anchors, "oxr_toks": [anchors[0]] + ins + [anchors[1]], "insert": text,
                        "left": at[max(0, i1 - 9):i1 - 1], "right": at[i1 + 1:i1 + 9],
                        "context": " ".join(at[max(0, i1 - 9):i1]) + " [+" + " ".join(ins) + "+] " + " ".join(at[i1:i1 + 8])})
    return out


def overlaps(o, s):
    """a two-reading disagreement at the same place as omission o (OXR's own reading of the same gap)"""
    if s["page"] != o["page"] or o["blocks"][0] not in s.get("blocks", []):
        return False
    return _has(s["left"][-1:] + s["primary_toks"] + s["right"][:1], o["primary_toks"])
