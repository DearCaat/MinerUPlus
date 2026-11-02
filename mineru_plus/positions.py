"""Where full.md is printed: the page and the boxes of each passage, so that a quote from full.md can be shown in the PDF.

positions.json, written next to full.md:
  {"version": 1, "pdf": PATH, "coordinates": ..., "counts": {...}, "spans": [[start, end, page, source, boxes], ...]}
  start, end  character offsets in full.md (end exclusive)
  page        1-based page number
  boxes       [[x0, y0, x1, y1], ...] in PDF points on the page as displayed (PyMuPDF page.rect, rotation applied),
              one box per printed line
  source      "layer": the characters equal the text layer's there; the boxes are those characters' lines
              "between": text without a counterpart in the layer (a formula the reader typed in LaTeX, a misread word)
                         between two stretches that align; the boxes are the layer characters between those stretches
              "block": text of a block that does not align (words read from a picture, a page without a text layer);
                       the box is the reader's box of the block
Text with no span: markup (#, *, tags, a link's target), text whose neighbours are printed next to each other (nothing
of it is printed), short blocks that match only inside a longer one (a panel letter), and what full.md holds beyond
the reader's blocks (the page headers and footers listed at its end).

How: the reader's blocks are found in full.md in reading order by their opening and closing words (the checks rewrote
parts of them, and moved floats after the paragraph they interrupt), and each block's characters are aligned once to
the text-layer characters inside its box. A quote is looked up with find() or from the command line:
  python -m mineru_plus.positions OUT_DIR "quoted text" [--crop crop.png]
"""
import argparse, bisect, difflib, json, re, sys, unicodedata
from pathlib import Path
import pymupdf
from .readers import mineru as MR
from . import layer as LY

DASHES = dict.fromkeys(map(ord, "‐‑‒–—−­"), "-")
MARKUP = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$|<[^<>\n]{1,200}>|!\[[^\]\n]*\]\([^)\n]*\)|\]\([^)\s]*\)", re.S)
WORD = re.compile(r"[^\W_]+")
GAP = 200          # most layer characters a "between" stretch may span
TAG = re.compile(r"</?[A-Za-z][^<>\n]{0,200}>")
SEP = r"(?:</?[A-Za-z][^<>\n]{0,200}>|[^\w<]|_)*"      # between two words: anything but letters and digits, or a tag
# a figure's own content is its transcription, moved out of full.md; page headers, footers and numbers are not in its
# body (margins.py lists the ones it writes at the end)
SKIP = {"image", "chart", "header", "footer", "page_number"}


def _norm(ch):
    return unicodedata.normalize("NFKC", ch).translate(DASHES)


def _layer_chars(pg):
    """the page's printed characters in the layer's order: [(char, display rect, line key)]"""
    out = []
    for b in pg.get_text("rawdict")["blocks"]:
        for ln, l in enumerate(b.get("lines", [])):
            for s in l["spans"]:
                for c in s["chars"]:
                    for ch in _norm(c["c"]):
                        if not ch.isspace():
                            out.append((ch, pymupdf.Rect(c["bbox"]) * pg.rotation_matrix, (b["number"], ln)))
    return out


def _anchor(md, toks, lo, hi):
    """offset span of the token sequence in md[lo:hi], tokens separated by anything but letters and digits,
    or by tags (the cells of a table)"""
    if not toks:
        return None
    m = re.compile(SEP.join(map(re.escape, toks))).search(md, lo, hi)
    return (m.start(), m.end()) if m else None


def _locate(md, content, cursor):
    """(start, end) of a block of the reader in full.md: its opening words near the cursor (ahead first, then a stretch
    back, since the checks move floats after the paragraph they interrupt), else anywhere when they are long enough to
    occur once; its closing words where the block's length puts them. None when not found"""
    content = TAG.sub(" ", content)
    toks = WORD.findall(content)
    if not toks:
        return None
    n = min(4, len(toks))
    tries = range(0, max(1, min(3, len(toks) - n + 1)))     # an edit may have hit the first or last words
    wins = [(cursor, min(len(md), cursor + 4 * len(content) + 4000)), (max(0, cursor - 20000), cursor)]
    if sum(map(len, toks[:n])) >= 16:
        wins.append((0, len(md)))
    for w, (lo, hi) in enumerate(wins):
        for k in tries:
            head = toks[k:k + n]
            h = _anchor(md, head, lo, hi)
            if h and w == 2 and _anchor(md, head, h[1], len(md)):
                h = None                                      # anywhere: only an opening that occurs once
            if not h:
                continue
            want = h[0] + len(content)
            reach = min(len(md), h[0] + 2 * len(content) + 400)
            for j in tries:
                tail = toks[len(toks) - n - j:len(toks) - j]
                ends, t = [], _anchor(md, tail, h[0], reach)
                while t:
                    ends.append(t[1])
                    t = _anchor(md, tail, t[1], reach)
                if ends:
                    end = min(ends, key=lambda e: abs(e - want))
                    # what the block holds after those words (its last words, when an edit hit them; a full stop)
                    c = _anchor(content, tail, 0, len(content))
                    rest = len(content) - c[1] if c else 0
                    stop = md.find("\n\n", end)
                    stop = stop if stop >= 0 else len(md)
                    e = min(end + rest, stop)
                    while e < stop and not md[e].isspace():     # an edit may have made the last word longer
                        e += 1
                    return h[0], e
            return h[0], min(len(md), want)
    return None


def _md_chars(seg, off):
    """(char, offset) of the printed characters of a stretch of full.md, and the formula spans in it"""
    chars, formulas, keep = [], [], [True] * len(seg)
    for m in MARKUP.finditer(seg):
        for i in range(m.start(), m.end()):
            keep[i] = False
        if m.group().startswith("$"):
            formulas.append((off + m.start(), off + m.end()))
    for i, ch in enumerate(seg):
        if keep[i] and not ch.isspace() and ch not in "#*":
            for c in _norm(ch):
                chars.append((c, off + i))
    return chars, formulas


def _boxes(items):
    """one box per printed line: [[x0, y0, x1, y1]] from (rect, line key) pairs"""
    lines = {}
    for r, ln in items:
        lines[ln] = lines[ln] | r if ln in lines else pymupdf.Rect(r)
    return [[round(v, 2) for v in r] for r in sorted(lines.values(), key=lambda r: (r.y0, r.x0))]


def _spans(page, mc, formulas, lay, bbox_pts, md_seg):
    """spans of one block: aligned stretches as "layer", what lies between them as "between", the rest as "block" """
    sm = difflib.SequenceMatcher(None, [c for c, _ in mc], [c for c, _, _ in lay], autojunk=False)
    hit = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            hit[a + k] = b + k
    runs, cur = [], None                    # stretches where the layer goes on in order: [start, end, i, j, [j...]]
    for i in range(len(mc)):
        j = hit.get(i)
        if j is not None and cur and cur[2] == i - 1 and 0 < j - cur[3] <= 3:
            cur[1], cur[2], cur[3] = mc[i][1] + 1, i, j
            cur[4].append(j)
        elif j is not None:
            cur = [mc[i][1], mc[i][1] + 1, i, j, [j]]
            runs.append(cur)
        else:
            cur = None
    # each word of an aligned stretch is a span of its own, so that a quote gets the boxes of its own words
    out = []
    for r in runs:
        word, prev = [], None
        for i, j in zip(range(r[2] - len(r[4]) + 1, r[2] + 1), r[4]):
            o = mc[i][1]
            if word and (o > prev + 1 and any(ch.isspace() for ch in md_seg(prev + 1, o))):
                out.append([mc[word[0][0]][1], prev + 1, page, "layer", _boxes([(lay[q][1], lay[q][2]) for _, q in word])])
                word = []
            word.append((i, j))
            prev = o
        if word:
            out.append([mc[word[0][0]][1], prev + 1, page, "layer", _boxes([(lay[q][1], lay[q][2]) for _, q in word])])
    # the stretches between aligned runs (formulas included) are printed where the layer goes between those runs
    first = mc[0][1] if mc else None
    last = mc[-1][1] + 1 if mc else None
    if formulas:
        first = min([first] + [f[0] for f in formulas]) if first is not None else formulas[0][0]
        last = max([last] + [f[1] for f in formulas]) if last is not None else formulas[-1][1]
    if first is None:
        return out
    bounds = [(first, first, None)] + [(r[0], r[1], r) for r in runs] + [(last, last, None)]
    for (_, lo, ra), (hi, _, rb) in zip(bounds, bounds[1:]):
        while lo < hi and md_seg(lo, lo + 1).isspace():
            lo += 1
        while hi > lo and md_seg(hi - 1, hi).isspace():
            hi -= 1
        if hi <= lo:
            continue
        if not any(lo <= o < hi for _, o in mc) and not any(lo <= f[0] < hi for f in formulas):
            continue
        a, b = (ra[4][-1] if ra else None), (rb[4][0] if rb else None)
        if a is not None and b is not None and b - a <= 1:
            continue                        # nothing is printed between its neighbours: markup, or a repeat
        if a is not None and b is not None and b - a <= GAP:
            out.append([lo, hi, page, "between", _boxes([(lay[j][1], lay[j][2]) for j in range(a + 1, b)])])
        else:
            out.append([lo, hi, page, "block", [bbox_pts]])
    return out


def build(pdf_path, mdir, md):
    doc = pymupdf.open(pdf_path)
    P = MR.pages(mdir)
    found, cursor, missing = [], 0, 0
    for pg_no in sorted(P):
        if pg_no > doc.page_count:
            continue
        for uid, typ, part in MR.units(P[pg_no]):
            content, bb = part.get("content"), part.get("bbox")
            if not isinstance(content, str) or not content.strip() or not bb or typ in SKIP:
                continue
            at = _locate(md, content, cursor)
            if not at:
                missing += 1
                continue
            if len(content) >= 40:          # a short block (a panel letter, a label) may match ahead of its place
                cursor = max(cursor, at[0])
            found.append((at, pg_no, bb, len(content) >= 40))
    # a short block whose match falls inside a longer block's stretch matched a word of that block ('F' in
    # '(E and F) Gene-wise ...'): it is left without a span, as is a short block another short one already took
    long_at = sorted(f[0] for f in found if f[3])
    taken, kept = [], []
    for f in found:
        if not f[3]:
            k = bisect.bisect_right(long_at, (f[0][0], len(md))) - 1
            if (k >= 0 and long_at[k][1] > f[0][0]) or any(t[0] < f[0][1] and f[0][0] < t[1] for t in taken):
                missing += 1
                continue
            taken.append(f[0])
        kept.append(f)
    spans, layers = [], {}
    for (lo, hi), pg_no, bb, _ in kept:
        pg = LY.page(doc, pg_no - 1)
        if pg_no not in layers:
            layers[pg_no] = _layer_chars(pg)
        W, H = pg.rect.width, pg.rect.height
        box = pymupdf.Rect(bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H)
        pad = box + (-2, -2, 2, 2)
        lay = [x for x in layers[pg_no] if pad.contains(pymupdf.Point((x[1].x0 + x[1].x1) / 2, (x[1].y0 + x[1].y1) / 2))]
        mc, formulas = _md_chars(md[lo:hi], lo)
        spans += _spans(pg_no, mc, formulas, lay, [round(v, 2) for v in box], lambda a, b: md[a:b])
    spans.sort(key=lambda s: (s[0], s[1]))
    printed = sorted({o for _, o in _md_chars(md, 0)[0]})       # characters of the text, markup left out
    cover = {}
    for s in spans:
        cover[s[3]] = cover.get(s[3], 0) + bisect.bisect_left(printed, s[1]) - bisect.bisect_left(printed, s[0])
    counts = {"spans": len(spans), "blocks not found in full.md": missing, "text characters": len(printed),
              **{f"characters in {k} spans": v for k, v in sorted(cover.items())},
              **{f"{k} spans": sum(x[3] == k for x in spans) for k in ("layer", "between", "block")}}
    return {"version": 1, "pdf": str(pdf_path),
            "coordinates": "PDF points on the page as displayed (PyMuPDF page.rect, origin top-left, rotation applied); "
                           "one box per printed line",
            "counts": counts, "spans": spans}


def write(pdf_path, mdir, md, out):
    pos = build(pdf_path, mdir, md)
    (Path(out) / "positions.json").write_text(json.dumps(pos, ensure_ascii=False, separators=(",", ":")))
    return pos["counts"]


def lookup(pos, start, end):
    """the spans that print full.md[start:end]: [{"start", "end", "page", "source", "boxes"}]"""
    return [{"start": s[0], "end": s[1], "page": s[2], "source": s[3], "boxes": s[4]}
            for s in pos["spans"] if s[0] < end and s[1] > start]


def lines(spans):
    """the boxes of spans merged into one box per printed line: {page: [[x0, y0, x1, y1]]}"""
    out = {}
    for s in spans:
        for b in s["boxes"]:
            ls = out.setdefault(s["page"], [])
            for L in ls:
                if abs((L[1] + L[3]) - (b[1] + b[3])) / 2 < 0.5 * min(L[3] - L[1], b[3] - b[1]) + 0.5 and \
                        b[0] <= L[2] + 20 and L[0] <= b[2] + 20:
                    L[:] = [min(L[0], b[0]), min(L[1], b[1]), max(L[2], b[2]), max(L[3], b[3])]
                    break
            else:
                ls.append(list(b))
    return out


def find(out_dir, quote):
    """where a quote from full.md is printed: {"start", "end", "spans"}, or None when full.md does not hold it
    (spaces and line breaks are not compared)"""
    out_dir = Path(out_dir)
    md = (out_dir / "full.md").read_text()
    pos = json.loads((out_dir / "positions.json").read_text())
    idx = [i for i, ch in enumerate(md) if not ch.isspace()]
    flat = "".join(md[i] for i in idx)
    q = "".join(quote.split())
    k = flat.find(q) if q else -1
    if k < 0:
        return None
    start, end = idx[k], idx[k + len(q) - 1] + 1
    sp = lookup(pos, start, end)
    return {"start": start, "end": end, "pages": lines(sp), "sources": sorted({s["source"] for s in sp}), "spans": sp}


def crop(out_dir, hit, path, dpi=150):
    """the first page of a hit with its boxes in red, saved to path"""
    pos = json.loads((Path(out_dir) / "positions.json").read_text())
    page = hit["spans"][0]["page"]
    pg = pymupdf.open(pos["pdf"])[page - 1]
    rects = [pymupdf.Rect(b) for b in hit["pages"][page]]
    u = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        u |= r
    for r in rects:
        pg.draw_rect((r + (-1, -1, 1, 1)) * pg.derotation_matrix, color=(1, 0, 0), width=0.8)
    pg.get_pixmap(dpi=dpi, clip=(u + (-30, -20, 30, 20)) & pg.rect).save(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m mineru_plus.positions",
                                 description="Where a quote from full.md is printed in the PDF (page and boxes).")
    ap.add_argument("out_dir", help="a mineru_plus output directory (full.md and positions.json)")
    ap.add_argument("quote", help="text copied from full.md; spaces and line breaks are not compared")
    ap.add_argument("--crop", metavar="PNG", help="save the page region with the boxes in red")
    a = ap.parse_args(argv)
    hit = find(a.out_dir, a.quote)
    if not hit:
        sys.exit("not in full.md")
    if a.crop and hit["spans"]:
        crop(a.out_dir, hit, a.crop)
    print(json.dumps({k: hit[k] for k in ("start", "end", "pages", "sources")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
