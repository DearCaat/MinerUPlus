"""Words full.md spells otherwise than the page prints them, outside formulas: a reader that corrects what it reads
('biopies' printed, 'biopsies' written; 'READout' as 'READOut'; 'eosinophillic' as 'eosinophilic'), misreads a letter
('Mr-TalhaIlyas' as 'Mr-Talhalyas'), or drops a ligature ('ﬁndings' as 'ndings'). Both readers can do it alike, so the
comparison of the two readings does not see it; the text layer prints the page's letters (11-20, 36 parses: 15 such
places, among them 6 ligatures and 9 words both readers changed).

Each prose paragraph of full.md and each cell of its tables, reduced to letters and digits, is placed on the text
layer: units the layer holds as they are take their stretch first, the rest go where most of their shingles are. A
difference counts where both sides are runs of at most six Latin letters, the letters on each side agree in the layer
and the parse for CTX letters (a cell CTX_CELL; fewer only at a unit's end, never under EDGE), and no letter of it or
its context comes from a formula (a math font's layer spells symbols as Latin letters). A symbol the parse prints that
the layer's font spells as a letter of its own (a bullet as 'B', '∏' as 'Q') is no difference.

With a source document, the source passage aligned with the unit says which spelling it writes (a source can differ from
the print too: 11-20, PTA-607 the XML writes 'biopsies' where the page prints 'biopies'). Every difference is an issue
with the page's letters, the parse's, and the source's word; none is written (11-20 文浩: an autocorrection is either
edited back with its evidence or reported, never kept silently). Where the layer and the aligned source agree against
the parse and the unit is the only one of its letters, the issue carries the edit back to the page's spelling as a
suggestion: writing it waits for a held-out set without a wrong edit (解-9)."""
import html, re, difflib, collections, unicodedata
import pymupdf
from .. import layer as LY
from . import two_readings as TR

CTX, CTX_CELL, EDGE = 12, 6, 3
FORMULA = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.S)
TAGS = re.compile(r"</?(?:sup|sub|table|tr|td|th|thead|tbody|br|a|img|span|div|i|b|em|strong|details|summary|u|ins|"
                  r"del|s|mark|small|font|center|p|code)\b[^>]*>")
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
KIND = "spelling differs from the text layer"


def key(text):
    """(letters and digits, NFKC with ligatures split; index of each in text)"""
    out, idx = [], []
    for i, c in enumerate(text):
        for d in unicodedata.normalize("NFKC", c):
            if d.isalnum():
                out.append(d)
                idx.append(i)
    return "".join(out), idx


def printed(seg):
    """a markdown stretch as printed: images out, links to their text, real tags off, then entities ('&lt;/a&gt;' is
    printed text, PTA-123 MOESM3 prints HTML source)"""
    seg = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", seg)
    seg = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", seg)
    return html.unescape(TAGS.sub("", seg))


def unit_key(text):
    """(key, index of each key letter into the printed text, from-formula flags, printed text)"""
    out, idx, fm, pt, n, pos = [], [], [], [], 0, 0
    for m in list(FORMULA.finditer(text)) + [None]:
        parts = [(printed(text[pos:m.start() if m else len(text)]), False)]
        if m:
            parts.append((" " + TR.latex_plain(m.group(0).strip("$")) + " ", True))
            pos = m.end()
        for seg, f in parts:
            k, ix = key(seg)
            out.append(k); idx += [n + i for i in ix]; fm += [f] * len(k); pt.append(seg); n += len(seg)
    return "".join(out), idx, fm, "".join(pt)


def units(md):
    """(raw text, offset in md, is a cell) of each paragraph, a table's cells one by one"""
    for m in re.finditer(r"(?:[^\n]|\n(?!\s*\n))+", md):
        p = m.group(0)
        if not p.strip():
            continue
        if "<table" in p:
            for c in CELL.finditer(p):
                yield c.group(1), m.start() + c.start(1), True
        else:
            yield p, m.start(), False


def shingles(k, n):
    return {k[i:i + n] for i in range(max(1, len(k) - n + 1))}


def _layer(doc):
    """per page: (key, owner word of each key letter, words)"""
    pages = []
    for i in range(len(doc)):
        ws = LY.words(LY.page(doc, i))
        k, owner = [], []
        for wi, w in enumerate(ws):
            kk, _ = key(w[4])
            k.append(kk); owner += [wi] * len(kk)
        pages.append(("".join(k), owner, ws))
    return pages


def _gap(text, idx, a, b):
    """text between key letters a-1 and b (exclusive), by their indices"""
    return text[idx[a - 1] + 1:idx[b]] if 0 < a and b < len(idx) else None


def find(doc, md, source=None):
    pages = _layer(doc)
    us = []
    for raw, off, cell in units(md):
        mk, midx, mfm, pt = unit_key(raw)
        if len(mk) >= (8 if cell else 30):
            us.append((raw, off, cell, mk, midx, mfm, pt))
    many = collections.Counter(u[3] for u in us)     # a unit md has more than once: its place is ambiguous
    stats = collections.Counter()
    # units the layer holds as they are take their stretch first (PTA-607: three cells 'biopsies', the layer one
    # 'biopsies' and two 'biopies'); the rest are placed on what is left
    used = [[] for _ in pages]
    rest = []
    for u in us:
        mk = u[3]
        for pi, (k, _, _) in enumerate(pages):
            at = next((m.start() for m in re.finditer(re.escape(mk), k)
                       if not any(a < m.end() and m.start() < b for a, b in used[pi])), None)
            if at is not None:
                used[pi].append((at, at + len(mk)))
                stats["units as the layer has them"] += 1
                break
        else:
            rest.append(u)
    masked = []
    for pi, (k, _, _) in enumerate(pages):
        s = list(k)
        for a, b in used[pi]:
            s[a:b] = "\x00" * (b - a)
        masked.append("".join(s))
    sh = {n: [shingles(k, n) for k in masked] for n in (6, 8)}
    found = []
    for raw, off, cell, mk, midx, mfm, pt in rest:
        n = 6 if cell else 8
        us_ = shingles(mk, n)
        best = max(range(len(pages)), key=lambda i: len(us_ & sh[n][i]), default=None)
        if best is None or len(us_ & sh[n][best]) / len(us_) < 0.5:
            stats["units not placed"] += 1
            continue
        stats["units placed"] += 1
        lk, (_, owner, ws) = masked[best], pages[best]
        sm = difflib.SequenceMatcher(None, lk, mk, autojunk=False)
        bl = [b for b in sm.get_matching_blocks() if b.size >= 4]
        if not bl:
            continue
        lo = max(0, bl[0].a - bl[0].b - 10)
        hi = min(len(lk), bl[-1].a + bl[-1].size + (len(mk) - bl[-1].b - bl[-1].size) + 10)
        C = CTX_CELL if cell else CTX
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, lk[lo:hi], mk, autojunk=False).get_opcodes():
            if op == "equal":
                continue
            i1, i2 = i1 + lo, i2 + lo
            ls, ps = lk[i1:i2], mk[j1:j2]
            L, R = mk[max(0, j1 - C):j1], mk[j2:j2 + C]
            if (len(L) < C and j1 - len(L) > 0) or (len(R) < C and j2 + len(R) < len(mk)) or len(L) + len(R) < C \
                    or len(L) < EDGE or len(R) < EDGE \
                    or lk[max(0, i1 - len(L)):i1] != L or lk[i2:i2 + len(R)] != R:
                continue
            if not (re.fullmatch(r"[A-Za-z]{0,6}", ls) and re.fullmatch(r"[A-Za-z]{0,6}", ps)) or ls == ps:
                continue
            if any(mfm[max(0, j1 - C):j2 + C]):
                stats["in or next to a formula, left out"] += 1
                continue
            gap = _gap(pt, midx, j1, j2) or ""
            # a symbol the parse prints that the layer's font spells as one letter, a word of its own
            if not ps and len(ls) == 1 and words_of(owner, i1, i2) == [owner[i1]] and ws[owner[i1]][4].strip() == ls \
                    and any(ord(c) > 127 and unicodedata.category(c) in ("So", "Sm", "Po") for c in gap):
                stats["layer letter for a printed symbol, left out"] += 1
                continue
            wi = words_of(owner, max(0, i1 - 1), min(len(owner), i2 + 1))
            f = {"page": best + 1, "cell": cell, "layer_letters": ls, "parse_letters": ps, "left": L, "right": R,
                 "layer": " ".join(ws[w][4] for w in wi), "parse": _words_around(pt, midx, j1, j2),
                 "repeated": many[mk] > 1, "boxes": [ws[w][:4] for w in wi]}
            f["source"] = source_says(source, mk, L, ls, ps, R) if source else None
            f["edit"] = _edit(raw, off, L, ps, R, ws, owner, i1, i2) \
                if f["source"] == "layer" and not f["repeated"] else None
            stats["differences"] += 1
            found.append(f)
    return found, stats


def words_of(owner, a, b):
    return sorted({owner[t] for t in range(a, b)})


def _words_around(pt, idx, j1, j2):
    a = idx[max(0, j1 - 1)]
    b = idx[min(len(idx) - 1, j2)]
    s = pt.rfind(" ", 0, a) + 1
    e = pt.find(" ", b)
    return pt[s:e if e >= 0 else len(pt)]


def source_says(source, mk, L, ls, ps, R):
    """which spelling the source passage aligned with the unit writes: 'layer', 'parse', 'both', 'neither', or
    'no aligned passage'"""
    sk = source.passage(mk)
    if not sk:
        return "no aligned passage"
    a, b = (L + ls + R) in sk, (L + ps + R) in sk
    return "both" if a and b else "layer" if a else "parse" if b else "neither"


def _edit(raw, off, L, ps, R, ws, owner, i1, i2):
    """the edit back to the page's spelling: the raw text between the last letter of L and the first of R, found once
    in the unit with only marks between the letters, replaced by the layer's text there (ligatures split). None where
    the place is not found once, or the layer's text there runs over a line"""
    sep = r"[^A-Za-z0-9<>\[\]$]*?"
    rx = re.compile(sep.join(map(re.escape, L)) + "(" + sep + sep.join(map(re.escape, ps)) + sep + ")"
                    + sep.join(map(re.escape, R)))
    hits = list(rx.finditer(raw))
    if len(hits) != 1:
        return None
    s, e = hits[0].span(1)
    a, b = owner[i1 - 1], owner[i2] if i2 < len(owner) else None
    if b is None or (ws[a][5], ws[a][6]) != (ws[b][5], ws[b][6]):
        return None
    # the layer's text from after L's last letter to before R's first (the words between them, marks included)
    text = " ".join(ws[w][4] for w in range(a, b + 1))
    _, ix = key(text)
    first = owner.index(a)                        # the key letter word a starts at
    la, rb = (i1 - 1) - first, i2 - first
    if not (0 <= la < len(ix) and 0 <= rb < len(ix)):
        return None
    new = unicodedata.normalize("NFKC", text[ix[la] + 1:ix[rb]])
    old = raw[s:e]
    if re.sub(r"[\x00-\x1f\x7f-\x9f]", "", old) == new:
        return None
    return {"start": off + s, "end": off + e, "old": old, "new": new}


def check(doc, md, source=None):
    """(issues, stats): one issue per difference, the edit back to the page's spelling attached where it is known"""
    found, stats = find(doc, md, source)
    issues = []
    for f in found:
        pg = LY.page(doc, f["page"] - 1)
        boxes = [_norm(pg, b) for b in f["boxes"]]
        i = {"kind": KIND, "page": f["page"], "parse": f["parse"], "layer": f["layer"],
             "layer_letters": f["layer_letters"], "parse_letters": f["parse_letters"], "layer_boxes": boxes,
             "why": f"the text layer prints '{f['layer_letters']}' where the parse writes '{f['parse_letters']}' "
                    f"(letters around: '{f['left']}|{f['right']}')"}
        if f["source"]:
            i["source"] = f["source"]
        if f["repeated"]:
            i["unit_repeated"] = True
        if f["edit"]:
            i["suggested_edit"] = f["edit"]
        stats["with a suggested edit"] += bool(f["edit"])
        if f["source"]:
            stats["source: " + f["source"]] += 1
        issues.append(i)
    return issues, dict(stats)


def _norm(pg, r):
    d = pymupdf.Rect(r) * pg.rotation_matrix
    W, H = pg.rect.width, pg.rect.height
    return [round(d.x0 / W, 4), round(d.y0 / H, 4), round(d.x1 / W, 4), round(d.y1 / H, 4)]


# an edit back to the page's spelling is written only after a held-out set of new papers shows none wrong (解-9);
# until then it is a suggestion on the issue
WRITE = False


def apply(doc, md, source=None, write=WRITE):
    """(md, edits, issues, stats): with write, the suggested edits are made and recorded with their evidence (the
    layer's and the source's spelling) instead of being reported"""
    issues, stats = check(doc, md, source)
    edits, out = [], []
    for i in sorted(issues, key=lambda i: -(i.get("suggested_edit") or {}).get("start", -1)):
        e = i.get("suggested_edit")
        if write and e and md[e["start"]:e["end"]] == e["old"]:
            md = md[:e["start"]] + e["new"] + md[e["end"]:]
            edits.append({"id": f"s{e['start']}", "page": i["page"], "route": "spelling",
                          "by": "text layer and source document", "old": e["old"], "new": e["new"],
                          "evidence": {"layer": i["layer"], "parse": i["parse"], "source": i.get("source")}})
            continue
        if e:
            i["suggested_edit"] = {"old": e["old"], "new": e["new"]}
        out.append(i)
    stats["written"] = len(edits)
    return md, edits[::-1], sorted(out, key=lambda i: i["page"]), stats
