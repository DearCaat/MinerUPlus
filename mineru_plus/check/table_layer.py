"""Tables against the text layer, character by character (born-digital pages). MinerU reads tables from the page image
(it does not copy the layer there), so the layer words inside the table box are an independent reading with
positions. Each MinerU cell's characters are aligned to the layer's (whitespace ignored, so a word the layer splits is
no difference), with the layer words in content-stream order or in line order, whichever aligns more; from the aligned
characters each cell gets the layer boxes of its words.

- look-alike: MinerU writes a look-alike of the layer's character (× for ✘, - for –, . for ·): the layer's code
  point is the font's glyph, written in.
- glued: a cell's two lines (two layer words on successive lines) MinerU writes without a space: a space written in.
- differ: other characters. A small difference (a misread or glued word) is settled by OXR's table where it holds one
  of the two readings and not the other (two readings against one), else by jev on the cell marked in a crop, per
  reading 'does the red box show exactly X?'; the layer's reading is written where it is printed and MinerU's is not.
- geometry: a cell whose layer words share a line band only with cells of other grid rows (or an x band only with
  cells of other columns). Such a table is not written (the alignment or MinerU's grid is uncertain) and goes to the
  caller with the cells.
10-29, 87 tables in 31 documents: 83 equal the layer after the fixes (533 look-alikes, 206 spaces, 3 cells); planted
cell swaps (168, a cell with its right or lower neighbour) found by geometry or as differing characters 161."""
import base64, collections as C, difflib, hashlib, html, re, statistics as ST, unicodedata
from pathlib import Path
import pymupdf
from .. import layer as LY
from ..readers import mineru as MR
from . import tables as TB, jev, dropped as DR

LOOKALIKE = ["-–—−‐‑", "✓✔√", "×✗✘✕Xx", ".·•", "*∗", "~∼", "'’′"]
CLS = {ch: k for k, s in enumerate(LOOKALIKE) for ch in s}
TD = re.compile(r"<tr[^>]*>|<(td|th)([^>]*)>(.*?)</\1>", re.S)
PLAIN = re.compile(r"^[^$\\<>&]*$")          # a cell whose characters are its text (no LaTeX, tags, entities)


def lookalike(a, b):
    return a != b and a in CLS and CLS.get(a) == CLS.get(b)


def parse(content):
    """source cells [{r, c, rs, cs, text, span}]: grid position with spans, inner text and its span in content
    (an HTML table, or a markdown pipe table: MinerU writes both)"""
    if "<table" not in content and "<tr" not in content:
        return _parse_pipes(content)
    out, taken, r, c = [], set(), -1, 0
    for m in TD.finditer(content):
        if m.group(0).startswith("<tr"):
            r, c = r + 1, 0; continue
        r = max(r, 0)
        while (r, c) in taken:
            c += 1
        a = m.group(2) or ""
        rs = int((re.search(r'rowspan="?(\d+)', a) or [0, 1])[1]); cs = int((re.search(r'colspan="?(\d+)', a) or [0, 1])[1])
        taken |= {(r + i, c + j) for i in range(rs) for j in range(cs)}
        out.append({"r": r, "c": c, "rs": rs, "cs": cs, "text": m.group(3), "span": m.span(3)})
        c += cs
    return out


def _nf(s):
    return unicodedata.normalize("NFKC", s)


def _parse_pipes(content):
    out, r, at = [], -1, 0
    for line in content.splitlines(keepends=True):
        st = line.strip()
        if st.startswith("|") and not re.fullmatch(r"\|[\s:|-]+\|?", st):
            r += 1
            bars = [at + m.start() for m in re.finditer(r"(?<!\\)\|", line)]
            for c, (x, y) in enumerate(zip(bars, bars[1:])):
                s0, s1 = x + 1, y
                while s0 < s1 and content[s0].isspace():
                    s0 += 1
                while s1 > s0 and content[s1 - 1].isspace():
                    s1 -= 1
                out.append({"r": r, "c": c, "rs": 1, "cs": 1, "text": content[s0:s1], "span": (s0, s1)})
        at += len(line)
    return out


def cell_chars(cell):
    """[(char, position in the cell's text or None)] without whitespace; a cell with LaTeX or markup is reduced to
    its printed characters (positions None: reported, not edited)"""
    t = cell["text"]
    if PLAIN.match(t):
        return [(ch, i) for i, ch in enumerate(t) if not ch.isspace()]
    return [(ch, None) for ch in _nf("".join(TB.cell_toks(re.sub(r"<[^>]+>", " ", t))))]


def frame(page, clip):
    """a function mapping a box (unrotated page coordinates) to (x0, y0, x1, y1) in the reading frame of the text
    inside clip: x along its lines, y down the lines"""
    dirs = C.Counter()
    for b in page.get_text("dict", clip=clip)["blocks"]:
        for l in b.get("lines", []):
            dirs[(round(l["dir"][0]), round(l["dir"][1]))] += len(l.get("spans", []))
    d = dirs.most_common(1)[0][0] if dirs else (1, 0)
    if d == (0, -1):      # text running up: next line to the right
        return lambda b: (-b[3], b[0], -b[1], b[2])
    if d == (0, 1):       # running down: next line to the left
        return lambda b: (b[1], -b[2], b[3], -b[0])
    if d == (-1, 0):
        return lambda b: (-b[2], -b[3], -b[0], -b[1])
    return lambda b: tuple(b[:4])


def layer_words(page, bbox, order, pad=0.005):
    """layer words in the table box, in reading order of the table's text: [(text, box in reading frame)]"""
    W, H = page.rect.width, page.rect.height
    x0, y0, x1, y1 = bbox
    r = pymupdf.Rect((x0 - pad) * W, (y0 - pad) * H, (x1 + pad) * W, (y1 + pad) * H) * page.derotation_matrix
    ws = [w for w in LY.words(page, r) if w[4].replace("﻿", "").strip()]
    if not ws:
        return []
    f = frame(page, r)
    ws = [(_nf(w[4]).replace("﻿", ""), f(w), tuple(w[:4])) for w in ws]
    if order == "stream":
        return ws        # content-stream order: generators write a row's cells one after another, a wrapped cell whole
    h = ST.median(b[3] - b[1] for _, b, _u in ws)
    ws.sort(key=lambda w: (w[1][1] + w[1][3]) / 2)
    lines, cur = [], []
    for w in ws:
        y = (w[1][1] + w[1][3]) / 2
        if cur and y - ST.mean((v[1][1] + v[1][3]) / 2 for v in cur) > 0.5 * h:
            lines.append(cur); cur = []
        cur.append(w)
    lines.append(cur)
    return [w for ln in lines for w in sorted(ln, key=lambda w: w[1][0])]


def align(M, L):
    """M, L: character strings; -> {i: j} for equal characters, two passes (a wrapped cell's second line comes after
    the other cells' first lines in the layer's line order)"""
    m = {}
    for a, b, n in difflib.SequenceMatcher(None, M, L, autojunk=False).get_matching_blocks():
        m.update({a + k: b + k for k in range(n)})
    li = [i for i in range(len(M)) if i not in m]; lj = sorted(set(range(len(L))) - set(m.values()))
    if li and lj:
        M2, L2 = "".join(M[i] for i in li), "".join(L[j] for j in lj)
        for a, b, n in difflib.SequenceMatcher(None, M2, L2, autojunk=False).get_matching_blocks():
            if n >= 3:            # a short common run of leftovers is chance
                m.update({li[a + k]: lj[b + k] for k in range(n)})
    return m


def check_table(page, b):
    """the table checked with the layer words in content-stream order (generators write a row's cells one after
    another, a wrapped cell whole: 10-29, 100 tables, 99.4% of characters aligned) or in line order, whichever aligns
    more characters"""
    best = None
    for order in ("stream", "lines"):
        r = _check(page, b, order)
        if r and (best is None or r["matched"] > best["matched"]):
            best = r
    return best


def _check(page, b, order):
    cells = parse(b["content"])
    lw = layer_words(page, b["bbox"], order)
    if not lw or not cells:
        return None
    Mc = [(ch, k, pos) for k, cl in enumerate(cells) for ch, pos in cell_chars(cl)]
    Lc = [(ch, w) for w, (t, *_) in enumerate(lw) for ch in t if not ch.isspace() and ch != "\xad"]
    M, L = "".join(x[0] for x in Mc), "".join(x[0] for x in Lc)
    m = align(M, L)
    # look-alike substitutions: an unmatched M char between matched neighbours whose layer counterpart is a look-alike
    variants, rev = [], {j: i for i, j in m.items()}
    for i, (ch, k, pos) in enumerate(Mc):
        if i in m:
            continue
        p, n = m.get(i - 1), m.get(i + 1)
        j = p + 1 if p is not None else (n - 1 if n is not None else None)
        if j is not None and 0 <= j < len(Lc) and j not in rev and lookalike(ch, Lc[j][0]):
            m[i] = j; rev[j] = i
            variants.append({"cell": k, "pos": pos, "mineru": ch, "layer": Lc[j][0], "word": lw[Lc[j][1]][0]})
    # leftover look-alikes in the same order on both sides (a check mark the line order puts before its row)
    li = [i for i in range(len(Mc)) if i not in m and Mc[i][0] in CLS]
    lj = [j for j in range(len(Lc)) if j not in rev and Lc[j][0] in CLS]
    if li and lj:
        ca, cb = [CLS[Mc[i][0]] for i in li], [CLS[Lc[j][0]] for j in lj]
        for a, b2, n in difflib.SequenceMatcher(None, ca, cb, autojunk=False).get_matching_blocks():
            for q in range(n):
                i, j = li[a + q], lj[b2 + q]
                m[i] = j; rev[j] = i
                if Mc[i][0] != Lc[j][0]:
                    variants.append({"cell": Mc[i][1], "pos": Mc[i][2], "mineru": Mc[i][0], "layer": Lc[j][0],
                                     "word": lw[Lc[j][1]][0]})
    # glued: consecutive M chars of one cell, mapped to two different layer words, with no whitespace between in the
    # cell's text
    glued = []
    for i in range(len(Mc) - 1):
        (c1, k1, p1), (c2, k2, p2) = Mc[i], Mc[i + 1]
        if k1 != k2 or p1 is None or i not in m or i + 1 not in m:
            continue
        w1, w2 = Lc[m[i]][1], Lc[m[i + 1]][1]
        b1, b2 = lw[w1][1], lw[w2][1]
        h = min(b1[3] - b1[1], b2[3] - b2[1])
        # a cell's next line (10-29: gaps on a line are no evidence, glyph widths in some layers are wrong: 'T umor')
        apart = b2[1] > b1[3] - 0.3 * h
        if w1 != w2 and apart and p2 == p1 + 1 and lw[w1][0][-1:] not in "-–—−‐‑/":     # a line broken after a dash or slash
            glued.append({"cell": k1, "pos": p2, "left": lw[w1][0], "right": lw[w2][0]})
    # unmatched characters on either side, in runs
    used = set(m.values())
    um = [i for i in range(len(Mc)) if i not in m]; ul = [j for j in range(len(Lc)) if j not in used]
    def runs(ix, s):
        out, cur = [], []
        for i in ix:
            if cur and i != cur[-1] + 1:
                out.append("".join(s[x] for x in cur)); cur = []
            cur.append(i)
        if cur: out.append("".join(s[x] for x in cur))
        return out
    # cell boxes (reading frame) from the layer words their characters map to
    wof = C.defaultdict(C.Counter)
    for i, j in m.items():
        wof[Mc[i][1]][Lc[j][1]] += 1
    box = {}
    for k, cnt in wof.items():
        bs = [lw[w][1] for w in cnt]
        box[k] = (min(x[0] for x in bs), min(x[1] for x in bs), max(x[2] for x in bs), max(x[3] for x in bs))
    # a cell's layer box must share its line band with some cell of its own grid row (and its x band with some cell of
    # its own column), not only with cells of other rows (columns): spanned cells count for every row (column) they cover
    geometry = []
    ov = lambda x0, x1, y0, y1: min(x1, y1) - max(x0, y0) > 0.3 * min(x1 - x0, y1 - y0)
    for what, lo, hi, a0, a1 in (("row", "r", "rs", 1, 3), ("column", "c", "cs", 0, 2)):
        for k, bx in box.items():
            cl = cells[k]
            mine = set(range(cl[lo], cl[lo] + cl[hi]))
            own = other = 0; where = C.Counter()
            for k2, bx2 in box.items():
                if k2 == k or not ov(bx[a0], bx[a1], bx2[a0], bx2[a1]):
                    continue
                c2 = cells[k2]; theirs = set(range(c2[lo], c2[lo] + c2[hi]))
                if mine & theirs: own += 1
                else: other += 1; where[min(theirs)] += 1
            if own == 0 and other > 0:
                geometry.append({"cell": k, "r": cl["r"], "c": cl["c"], "text": cl["text"][:60], "what": "on another " + what,
                                 "other": where.most_common(1)[0][0]})
    ubox = {k: [lw[w][2] for w in cnt] for k, cnt in wof.items()}
    owner = C.defaultdict(set)
    for i, j in m.items():
        owner[Lc[j][1]].add(Mc[i][1])
    # a cell differs when MinerU has characters the layer lacks there, or a layer word inside the cell (in stream
    # order between the cell's words and inside its box) has characters MinerU lacks; a hyphen ending a line of the
    # cell is the line break's, not a difference (MinerU joins the word)
    last = {}
    for j, (_, w) in enumerate(Lc):
        last[w] = j

    def line_end_hyphen(j):
        w = Lc[j][1]
        if Lc[j][0] != "-" or last[w] != j or w + 1 >= len(lw):
            return False
        bx, nx = lw[w][1], lw[w + 1][1]
        return nx[1] > bx[3] - 0.3 * (bx[3] - bx[1])
    unl = C.Counter(Lc[j][1] for j in ul if not line_end_hyphen(j))
    umc = C.Counter(Mc[i][1] for i in um)
    cells_differ = []
    for k, cnt in wof.items():
        ws = sorted(cnt); bx = box[k]; hh = 0.3 * (bx[3] - bx[1])
        inside = lambda w: bx[0] - hh <= (lw[w][1][0] + lw[w][1][2]) / 2 <= bx[2] + hh and bx[1] - hh <= (lw[w][1][1] + lw[w][1][3]) / 2 <= bx[3] + hh
        run = [w for w in range(ws[0], ws[-1] + 1) if w in cnt or (not owner.get(w) and inside(w))]
        if not umc.get(k) and not any(unl.get(w) for w in run):
            continue
        lay = " ".join(lw[w][0] for w in run)
        mine = re.sub(r"\s+", " ", cells[k]["text"]).strip()
        same = lambda x: "".join(LOOKALIKE[CLS[c]][0] if c in CLS else c for c in x)
        if same("".join(lay.split())) == same("".join(ch for ch, _ in cell_chars(cells[k]))):
            continue
        cells_differ.append({"cell": k, "r": cells[k]["r"], "c": cells[k]["c"], "mineru": mine, "layer": lay,
                             "plain": bool(PLAIN.match(cells[k]["text"])), "boxes": [lw[w][2] for w in run]})
    return {"order": order, "cells_differ": cells_differ, "ubox": {str(k): v for k, v in ubox.items()}, "grid": [(c["r"], c["c"], c["rs"], c["cs"]) for c in cells],
            "cells": len(cells), "chars": len(M), "layer_chars": len(L), "matched": len(m), "variants": variants,
            "glued": glued, "mineru_only": runs(um, M), "layer_only": runs(ul, L), "geometry": geometry}


def find(pdf_path, mdir, layer_pages):
    """tables on pages with a text layer whose box holds layer words: [{page, block, content, ...check_table}]"""
    pdf = pymupdf.open(pdf_path); out = []
    for pg, bl in sorted(MR.pages(mdir).items()):
        if pg not in layer_pages:
            continue
        page = LY.page(pdf, pg - 1)
        for bi, b in bl:
            if b["type"] == "table" and parse(b.get("content") or "") and b.get("bbox"):
                r = check_table(page, b)
                if r:
                    out.append({"page": pg, "block": bi, "content": b["content"], **r})
    return out


EXACT = ("The image is cut from a printed table. Compare the quoted text with the text inside the red box character by "
         "character: every letter, its order, digits, punctuation, symbols, spaces between words. The table may contain "
         "typing errors; judge what is printed, do not correct it.")


def _similar(a, b):
    """a small difference (a misread or glued word), not another cell's text: lengths within a quarter, 80% alike"""
    a, b = "".join(a.split()), "".join(b.split())
    return a and b and 0.8 <= len(a) / len(b) <= 1.25 and difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.8


def _upright(page, clip):
    """degrees to turn a rendering of the page so the text inside clip (unrotated coordinates) reads left to right"""
    d = C.Counter()
    for b in page.get_text("dict", clip=clip)["blocks"]:
        for l in b.get("lines", []):
            v = pymupdf.Point(l["dir"]) * pymupdf.Matrix(page.rotation_matrix.a, page.rotation_matrix.b,
                                                         page.rotation_matrix.c, page.rotation_matrix.d, 0, 0)
            d[(round(v.x), round(v.y))] += 1
    top = d.most_common(1)[0][0] if d else (1, 0)
    return {(0, -1): -90, (0, 1): 90, (-1, 0): 180}.get(top, 0)


def crop(page, boxes, path, rot, mark=True, pad=30, dpi=200):
    """crop around unrotated layer boxes, the boxes' union marked red, turned upright; returns the path"""
    from PIL import Image, ImageDraw
    U = pymupdf.Rect(boxes[0])
    for b in boxes[1:]:
        U |= pymupdf.Rect(b)
    D = U * page.rotation_matrix
    clip = (D + (-pad, -pad, pad, pad)) & page.rect
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if mark:
        z = dpi / 72
        ImageDraw.Draw(im).rectangle([(D.x0 - clip.x0 - 2) * z, (D.y0 - clip.y0 - 2) * z, (D.x1 - clip.x0 + 2) * z,
                                      (D.y1 - clip.y0 + 2) * z], outline=(255, 0, 0), width=3)
    if rot:
        im = im.rotate(rot, expand=True)
    im.save(path)
    return path


def _oxr_text(oxr_pages, page, mine):
    """the OXR table on the page sharing most characters with MinerU's, as one string without whitespace"""
    best, bj = "", 0.0
    for ob in oxr_pages.get(page, []):
        if ob["type"] != "Table":
            continue
        t = _nf(html.unescape(re.sub(r"<[^>]+>", " ", ob.get("content") or "")))
        t = "".join(t.split())
        j = difflib.SequenceMatcher(None, mine[:3000], t[:3000], autojunk=False).ratio()
        if j > bj:
            best, bj = t, j
    return best if bj >= 0.3 else ""


def judge(pdf_path, found, work, oxr_pages=None):
    """cells that differ a little from the layer (a misread or glued word): jev on a crop with the cell marked, per
    reading, 'does the red box show exactly X?' in both orders. layer: the layer's reading is printed and MinerU's is
    not; mineru: the reverse (the layer is wrong there); else undecided"""
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    pdf = pymupdf.open(pdf_path); qs = []
    for t in found:
        page = LY.page(pdf, t["page"] - 1)
        allb = [b for bs in t["ubox"].values() for b in bs]
        U = pymupdf.Rect(allb[0])
        for b in allb[1:]:
            U |= pymupdf.Rect(b)
        rot = _upright(page, U)
        if t["cells_differ"] or t["geometry"]:
            t["crop"] = crop(page, allb, str(work / "crops" / f"table_p{t['page']}_b{t['block']}.png"), rot, mark=False)
        for x in t["cells_differ"]:
            mine = html.unescape(x["mineru"])
            if not (x["plain"] and _similar(mine, x["layer"])):
                x["verdict"] = "not judged (LaTeX or markup in the cell)" if not x["plain"] else "not judged (not a small difference)"
                continue
            x["id"] = f"t{t['page']}.{t['block']}.{x['cell']}"
            # OXR (a second reading of the image) holds the layer's characters and not MinerU's, or the reverse: two
            # readings against one, no judge (as for omissions)
            if oxr_pages is not None:
                if "oxr" not in t:
                    t["oxr"] = _oxr_text(oxr_pages, t["page"], "".join(ch for c in parse(t["content"]) for ch, _ in cell_chars(c)))
                dl, dm = "".join(x["layer"].split()), "".join(mine.split())
                if t["oxr"] and (dl in t["oxr"]) != (dm in t["oxr"]):
                    x["verdict"] = "layer" if dl in t["oxr"] else "mineru"
                    x["by"] = "text layer and OXR" if dl in t["oxr"] else "MinerU and OXR"
                    continue
            x["crop"] = crop(page, x["boxes"], str(work / "crops" / f"{x['id']}.png"), rot)
            img = "data:image/png;base64," + base64.b64encode(open(x["crop"], "rb").read()).decode()
            for side, txt in (("mineru", mine), ("layer", x["layer"])):
                h = hashlib.md5(txt.encode()).hexdigest()[:8]     # jev-call resumes by id: the id carries the words
                qs.append({"id": f"{x['id']}|{side}~{h}", "state": f"Quoted text: «{txt}»", "instructions": EXACT,
                           "images": [img], "options": {"yes": f"The red box shows exactly «{txt}»",
                                                        "no": f"The red box shows something different from «{txt}»"}})
    v = jev.ask(qs, work, "cells") if qs else {}
    got = {q["id"].split("~")[0]: v.get(q["id"]) for q in qs}
    for t in found:
        for x in t["cells_differ"]:
            if "id" in x and "by" not in x:
                x["by"] = "jev (exactly printed)"
                a, b = got.get(x["id"] + "|mineru"), got.get(x["id"] + "|layer")
                x["verdict"] = "layer" if (b, a) == ("yes", "no") else "mineru" if (a, b) == ("yes", "no") else "undecided"
    return found


def apply(md, mdir, found):
    """writes look-alike characters and spaces from the layer and the cells jev settled for the layer; returns
    (md, edits, issues, counts)"""
    pages = MR.pages(mdir)
    edits, issues, n = [], [], C.Counter()
    pdf_pages = {}
    for t in found:
        n["tables"] += 1
        content = dict(pages[t["page"]])[t["block"]]["content"]
        cells = parse(content)
        rewrite = {x["cell"]: x for x in t["cells_differ"] if x.get("verdict") == "layer"}
        ch = C.defaultdict(list)                  # cell -> [(pos, old length, new text)]
        for v in t["variants"]:
            if v["pos"] is not None and v["cell"] not in rewrite:
                ch[v["cell"]].append((v["pos"], 1, v["layer"])); n["look-alike characters"] += 1
        for g in t["glued"]:
            if g["cell"] not in rewrite:
                ch[g["cell"]].append((g["pos"], 0, " ")); n["spaces between glued words"] += 1
        new_cells = {}
        for k, ops in ch.items():
            s = cells[k]["text"]
            for pos, ln, new in sorted(ops, reverse=True):
                s = s[:pos] + new + s[pos + ln:]
            new_cells[k] = s
        for k, x in rewrite.items():
            new_cells[k] = html.escape(x["layer"], quote=False); n["cells rewritten: " + x["by"]] += 1
        n["cells kept (layer wrong)"] += sum(x.get("verdict") == "mineru" for x in t["cells_differ"])
        left = [x for x in t["cells_differ"] if x.get("verdict") not in ("layer", "mineru")]
        if t["geometry"]:
            new_cells = {}            # cells off their row or column: the alignment, or MinerU's grid, is not certain
            n["tables not written (cells off their row or column)"] += 1
        # full.md joins a table continued on the next page into one (the first part loses </table>, the next its
        # <table>), and earlier repairs may have changed a cell: the rows are located without the wrapping tags, and a
        # cell is written only where full.md still has MinerU's text
        core = re.sub(r"^<table>|</table>$", "", content)
        if new_cells:
            # a continued table whose repeated header row full.md drops: located without its first row
            first = re.match(r"\s*<tr[^>]*>.*?</tr>", core, re.S)
            here, skip = DR.locate(md, core), 0
            if not here and first:
                here, skip = DR.locate(md, core[first.end():]), sum(c["r"] == 0 for c in cells)
            mcells = [None] * skip + (parse(here) if here else [])
            if len(mcells) != len(cells):
                # full.md writes some tables otherwise than the page's block (10-29: a page's pipe table as part of
                # a joined HTML table); look-alikes and spaces are counted, a settled cell goes to the caller
                n["table written otherwise in full.md (fixes not written)"] += 1
                if rewrite:
                    issues.append({"kind": "table", "page": t["page"], "block": t["block"], "crop": t.get("crop"),
                                   "why": "cells settled for the layer's reading but not written: the table is not "
                                          "found in full.md as on its page",
                                   "cells": [{k: x[k] for k in ("r", "c", "mineru", "layer", "by")} for x in rewrite.values()]})
            else:
                new = here
                for k in sorted(new_cells, key=lambda k: -(mcells[k]["span"][0] if mcells[k] else -1)):
                    if mcells[k] is None:
                        n["header of a continued table (not in full.md)"] += 1
                        continue
                    if mcells[k]["text"] != cells[k]["text"]:
                        n["cells changed by an earlier repair (not written)"] += 1
                        continue
                    a, b = mcells[k]["span"]
                    new = new[:a] + new_cells[k] + new[b:]
                    edits.append({"id": f"t{t['page']}.{t['block']}.{k}", "page": t["page"], "route": "table",
                                  "by": rewrite[k]["by"] if k in rewrite else "text layer",
                                  "cell": [cells[k]["r"], cells[k]["c"]], "old": cells[k]["text"], "new": new_cells[k]})
                md = md.replace(here, new, 1)
        if left or t["geometry"]:
            n["tables with open cells"] += 1
            issues.append({"kind": "table", "page": t["page"], "block": t["block"], "crop": t.get("crop"),
                           "cells_differ_from_layer": [{k: x[k] for k in ("r", "c", "mineru", "layer", "verdict")} for x in left],
                           "cells_off_their_row_or_column": [{k: g[k] for k in ("r", "c", "text", "what", "other")} for g in t["geometry"]]})
        else:
            n["tables equal the layer (after fixes)"] += 1
    return md, edits, issues, dict(n)
