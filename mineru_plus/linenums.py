"""Line numbers set in a page margin (manuscripts, supplements of journals that number the lines of a submission).

They are printed, and part of the margin, not of the running text. Whether the primary reader sees them depends on the
page: on PTA-564's supplement it read the column as side-note blocks, which margins.py writes to the closing section
(`- p1 side note: 1121 1122 ...`); on PTA-129's supplement MOESM1 (11-17) it put every number into the text block of its
line, after the line's last word ('NanoZoomer6 S360', 'pixel.8'). The text then held numbers the page prints in the
margin, and the dropped check reported those it lost as 'text layer not in the parse' (31 issues on one document, the
paper line's L1-3 split on where in the line they belong).

So the column is found from the text layer, not from the reader's block types, and the reading is brought to the form
the reader gives when it recognises the column: each number taken out of the running text, the text blocks narrowed to
the body, and the page's numbers one side-note block, which margins.py writes and checks against the layer as for any
side note.

A column is the text layer's own: integer words whose left or right edges line up, values rising by one down the page,
beside lines of text and outside every other word of the page (a row-number column of a table has the table's other
cells and the paragraphs around it at its side, never only on one side); three or more on a page, or fewer at the
place of a column found on another page of the document. Rotated pages are left as they are.

A number is taken out of a block's text only where it is found once next to its own line's text (after the line's last
characters or before its first): text such as '421 patients' or 'S360' is never touched. A number the text holds that
cannot be placed so is left and reported."""
import collections, json, re, shutil
from pathlib import Path
import pymupdf
from . import layer as LY
from .readers import mineru as MR
from .check.coverage import INVISIBLE
from .margins import MARGIN

NUM = re.compile(r"\d{1,4}")
ALIGN = 1.5          # points: the edges of a column's numbers
GAP = 2.0            # points: between a column and the text beside it


def _clean(t):
    return INVISIBLE.sub("", t)


def _same_line(a, b):
    return min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5 * min(a.height, b.height)


def _alnum(s):
    return "".join(c.lower() for c in s if c.isalnum())


def _runs(cands):
    """runs of rising-by-one values down the page among numbers whose left or right edges line up"""
    out = []
    for edge in (0, 2):
        cs = sorted(cands, key=lambda c: c[1][edge])
        groups, g = [], []
        for c in cs:
            if g and c[1][edge] - g[-1][1][edge] > ALIGN:
                groups.append(g); g = []
            g.append(c)
        if g:
            groups.append(g)
        for g in groups:
            g = sorted(g, key=lambda c: c[1].y0)
            run = [g[0]]
            for c in g[1:]:
                if c[0] == run[-1][0] + 1:
                    run.append(c)
                else:
                    out.append(run); run = [c]
            out.append(run)
    return out


def _side(run, others):
    """'left' or 'right' when the run stands apart from every other word of the page on that side and beside lines of
    text on the other, else None"""
    col = pymupdf.Rect(run[0][1])
    for _, r in run:
        col |= r
    if not others:
        return None, col
    beside = lambda r: [o for o in others if _same_line(o, r)]
    # by the centres of the numbers, and their edges within GAP of the text: a word's box takes in the zero-width
    # characters around it (PTA-129 MOESM1: '\u200b1\u200b' ends at 73.2, its line's text starts at 72.0)
    cx = [(r.x0 + r.x1) / 2 for _, r in run]
    lo, hi = min(o.x0 for o in others), max(o.x1 for o in others)
    if max(cx) + GAP <= lo and col.x1 <= lo + GAP:
        side = "left"
        lined = sum(1 for (_, r), c in zip(run, cx) if any(o.x0 >= c for o in beside(r)))
    elif min(cx) - GAP >= hi and col.x0 >= hi - GAP:
        side = "right"
        lined = sum(1 for (_, r), c in zip(run, cx) if any(o.x1 <= c for o in beside(r)))
    else:
        return None, col
    return (side if 2 * lined >= len(run) else None), col


def find(pdf):
    """{page: {"side", "column" (Rect), "numbers": [(value, Rect)]}} of the line-number columns of the document"""
    doc = pymupdf.open(pdf) if not isinstance(pdf, pymupdf.Document) else pdf
    per, places = {}, []
    words = {}
    for i in range(len(doc)):
        pg = LY.page(doc, i)
        if pg.rotation:
            continue
        ws = [(_clean(w[4]), pymupdf.Rect(w[:4])) for w in LY.words(pg)]
        ws = [(t, r) for t, r in ws if t]
        cands = [(int(t), r) for t, r in ws if NUM.fullmatch(t)]
        words[i + 1] = (ws, cands)
        best = None
        for run in _runs(cands):
            if len(run) < 3:
                continue
            ids = {id(r) for _, r in run}
            others = [r for _, r in ws if id(r) not in ids]
            side, col = _side(run, others)
            if side and (best is None or len(run) > len(best[1])):
                best = (side, run, col)
        if best:
            per[i + 1] = {"side": best[0], "column": best[2], "numbers": [(v, r) for v, r in best[1]]}
            places.append((best[0], best[2]))
    # pages with one or two numbers at the place of a column found elsewhere in the document
    for pg_no, (ws, cands) in words.items():
        if pg_no in per or not places:
            continue
        for side, col in places:
            edge = 0 if side == "right" else 2
            at = [c for c in cands if abs(c[1][edge] - col[edge]) <= ALIGN]
            if not at:
                continue
            for run in _runs(at):
                ids = {id(r) for _, r in run}
                others = [r for _, r in ws if id(r) not in ids]
                s, c = _side(run, others)
                if s == side and (pg_no not in per or len(run) > len(per[pg_no]["numbers"])):
                    per[pg_no] = {"side": s, "column": c, "numbers": [(v, r) for v, r in run]}
            if pg_no in per:
                break
    return per


def _occurrences(text, v):
    s = str(v)
    for m in re.finditer(r"(?<!\d)" + s + r"(?!\d)", text):
        a, b = m.start(), m.end()
        # a decimal or a grouped number ('0.23', '1,250'): the digits continue across the mark
        if a >= 2 and text[a - 1] in ".," and text[a - 2].isdigit():
            continue
        if b + 1 < len(text) and text[b] in ".," and text[b + 1].isdigit():
            continue
        yield a, b


def _placed(text, v, line):
    """(start, end) of the number v in the text where it is found once next to its line's text, else None (and the
    count of its occurrences)"""
    lt = _alnum(" ".join(line))
    tail, head = lt[-4:], lt[:4]
    hits = []
    occ = list(_occurrences(text, v))
    for a, b in occ:
        if tail and _alnum(text[:a]).endswith(tail) or head and _alnum(text[b:]).startswith(head):
            hits.append((a, b))
    return (hits[0] if len(hits) == 1 else None), len(occ)


def _cut(text, spans):
    for a, b in sorted(spans, reverse=True):
        l = text[a - 1] if a > 0 else ""
        r = text[b] if b < len(text) else ""
        if l in (" ", "\n", "") and r == " ":
            b += 1
        elif l == " " and r in ("\n", ""):
            a -= 1
        text = text[:a] + text[b:]
    return text


def apply(pdf, mdir):
    """Bring the reading in mdir to the form with the line numbers in the margin. The reader's own files are kept
    (structured_content.reader.json, <markdown>.reader.md) and the result is rebuilt from them each run. Returns
    (stats, issues)."""
    mdir = Path(mdir)
    sc_path = mdir / "structured_content.json"
    md_path = next((mdir / n for n in ("full.md", "markdown.md") if (mdir / n).exists()), None)
    sc_orig, md_orig = mdir / "structured_content.reader.json", (md_path.with_suffix(".reader.md") if md_path else None)
    if sc_orig.exists():
        shutil.copyfile(sc_orig, sc_path)
        if md_orig and md_orig.exists():
            shutil.copyfile(md_orig, md_path)
    cols = find(pdf)
    stats = collections.Counter()
    if not cols or md_path is None:
        return dict(stats), []
    if not sc_orig.exists():
        shutil.copyfile(sc_path, sc_orig)
        shutil.copyfile(md_path, md_orig)
    doc = pymupdf.open(pdf)
    sc = json.loads(sc_path.read_text())
    md = md_path.read_text(errors="ignore")
    issues, cursor = [], 0
    by_page = {p["page_idx"] + 1: p for p in sc["pages"]}
    for pg_no in sorted(by_page):
        page = by_page[pg_no]
        blocks = page.get("blocks") or []
        col = cols.get(pg_no)
        pg = LY.page(doc, pg_no - 1)
        W, H = pg.rect.width, pg.rect.height
        nums = col["numbers"] if col else []
        ws = [(_clean(w[4]), pymupdf.Rect(w[:4])) for w in LY.words(pg)] if col else []
        # the column's words among the page's words (find() read them into rectangles of its own)
        rk = lambda r: (round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2))
        ids = {rk(r) for _, r in nums}
        centre = lambda r: pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        nbox = lambda bb: pymupdf.Rect(bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H)
        # numbers the reader already gave as margin blocks (PTA-564's supplement) stay there. A page number, header or
        # footer block that holds only the column's numbers inside its box is read line numbers: they go to the side note
        # below and the block goes (11-18, PTA-129 MOESM1 p5: '8' was written as the page number '- p5 page number: 8')
        line_blocks = set()
        for bi, b in enumerate(blocks):
            if b.get("type") in MARGIN and b.get("type") != "aside_text" and b.get("bbox") and nums \
                    and isinstance(b.get("content"), str):
                inside = [v for v, r in nums if nbox(b["bbox"]).contains(centre(r))]
                if inside and collections.Counter(b["content"].split()) == collections.Counter(str(v) for v in inside):
                    line_blocks.add(bi)
        margin = [nbox(b["bbox"]) for bi, b in enumerate(blocks)
                  if b.get("type") in MARGIN and b.get("bbox") and bi not in line_blocks]
        column = nums
        nums = [(v, r) for v, r in nums if not any(m.contains(centre(r)) for m in margin)]
        drop, left = [], []
        for bi, b in enumerate(blocks):
            parts = [(None, b)] + [((k, j), c) for k in ("captions", "footnotes") for j, c in enumerate(b.get(k) or [])]
            if bi in line_blocks:
                # dropped from the page's blocks (the reader's markdown leaves margin blocks out: margins.py writes them
                # to the closing section from these blocks, so the markdown is not touched)
                drop.append(bi)
                stats["margin blocks of line numbers only, removed"] += 1
                continue
            if b.get("type") in MARGIN:
                continue
            for key, part in parts:
                t = part.get("content")
                bb = part.get("bbox")
                if not column or not bb:
                    continue
                box = nbox(bb)
                wide = box + (-GAP, -GAP, GAP, GAP)
                if not any(wide.contains(centre(r)) for _, r in column):
                    continue
                # the block reaches over the column: narrowed to the body, so that no check counts the column's
                # words for it (also those the reader gave a margin block of their own: PTA-129 MOESM1 p5, '8' as a
                # page number, was otherwise counted to the text block beside it and reported missing there)
                if col["side"] == "left":
                    part["bbox"] = [max(bb[0], col["column"].x1 / W), *bb[1:]]
                else:
                    part["bbox"] = [bb[0], bb[1], min(bb[2], col["column"].x0 / W), bb[3]]
                mine = [(v, r) for v, r in nums if wide.contains(centre(r))]
                if not isinstance(t, str) or not t or not mine:
                    continue
                spans, unplaced, held = [], [], [v for v, _ in mine]
                if t.split() == [str(v) for v, _ in mine]:
                    # a block of the column's numbers alone (PTA-129 MOESM1 p2: '12')
                    mine, spans = [], [(m.start(), m.end()) for m in re.finditer(r"\d+", t)]
                for v, r in mine:
                    line = [w for w, q in sorted(((w, q) for w, q in ws if rk(q) not in ids and _same_line(q, r)
                                                  and box.intersects(q)), key=lambda x: x[1].x0)]
                    at, n = _placed(t, v, line)
                    if at:
                        spans.append(at)
                    elif n:
                        unplaced.append(v)
                new = _cut(t, spans)
                stats["numbers taken out of the text"] += len(spans)
                if unplaced:
                    left.extend(unplaced)
                if new == t:
                    continue
                # the block in the markdown, in reading order
                gone = not new.strip()
                if gone:
                    # a paragraph of its own, with the line break that ends it
                    m = re.compile(r"(?m)^" + re.escape(t.strip()) + r"[ \t]*(\n|$)").search(md, cursor)
                    pos, old = (m.start(), m.group(0)) if m else (-1, "")
                else:
                    pos, old = md.find(t, cursor), t
                    if pos < 0 and md.count(t) == 1:
                        pos = md.find(t)
                if pos < 0:
                    left.extend(held)
                    stats["numbers taken out of the text"] -= len(spans)
                    continue
                md = md[:pos] + ("" if gone else new) + md[pos + len(old):]
                cursor = pos
                if gone and key is None:
                    drop.append(bi)
                    stats["blocks of line numbers only, removed"] += 1
                else:
                    part["content"] = new
        if nums:
            # the box of the numbers it holds: those in a margin block of the reader are checked there
            c = pymupdf.Rect(nums[0][1])
            for _, r in nums:
                c |= r
            # short of the text beside it: a number's box takes in the zero-width characters around it and reaches
            # into the line (PTA-129 MOESM1 p8: the side note's layer took the line's first word 'is')
            body = [q for _, q in ws if rk(q) not in ids]
            if body and col["side"] == "left":
                c.x1 = max(c.x0 + 1, min(c.x1, min(q.x0 for q in body) - 2 * GAP))
            elif body:
                c.x0 = min(c.x1 - 1, max(c.x0, max(q.x1 for q in body) + 2 * GAP))
            blocks = [b for i, b in enumerate(blocks) if i not in drop]
            blocks.append({"type": "aside_text", "bbox": [c.x0 / W, c.y0 / H, c.x1 / W, c.y1 / H],
                           "content": " ".join(str(v) for v, _ in nums), "line_numbers": True})
            page["blocks"] = blocks
            stats["pages with line numbers"] += 1
            stats["line numbers"] += len(nums)
        if left:
            issues.append({"kind": "line number left in the running text", "page": pg_no, "numbers": left,
                           "why": "the text holds the number but not once next to its line's text"})
    sc_path.write_text(json.dumps(sc, ensure_ascii=False))
    md_path.write_text(md)
    return dict(stats), issues
