"""Words the primary broke with spaces, joined by the text layer alone.

The two-reading spacing route (check/resolve.py) needs OXR's reading of the same passage. Where OXR read the passage
elsewhere (a table note it put inside its table) nothing compares the primary's spacing: 11-03, PTA-05 main and
supplement, the note of Table 3 read 'g rade 1 –2 occu rri ng i n ≥ 5 % of patients and al l events ... are l isted',
three runs of it reported, the rest not.

A run of two to four letter tokens one space apart is joined where the page's layer has the joined word and never
the tokens one after another, at least one token is no layer word of the page (a single letter, 'occu'), and OXR,
wherever it put the passage, has the joined word on the page and not the tokens one after another: the layer is the
document's own text, so 'in to' stays where the layer prints 'in' 'to', and 'g rade' becomes 'grade' where it
prints only 'grade'. OXR is asked because some layers run words together without spaces (11-03, PTA-07, PTA-09,
PTA-11: 'theirutilityforROR' a layer word, 'their utility for ROR' joined); without OXR nothing is joined.

A space inside a word is an error (文浩 11-03, 「算错」: it breaks search and quotation checks). Where the layer
points to one and OXR neither confirms the word nor reads the pieces apart (no OXR, or OXR left the passage out),
it is reported.

A space before a comma, full stop, semicolon or colon is dropped where the layer prints the mark against the word
and OXR reads it so: a layer can set a spacing accent and then a space glyph the page does not print ('Pare´' ','
0.1 pt apart, 11-03 PTA-05 and PTA-10 references, read 'Paré , L.'). The compare reads no spaces around marks, so
only the layer and OXR see it; with no OXR nothing is dropped and nothing reported, a space before a mark being no
space inside a word.

So is a space after a hyphen where the layer breaks the line at that hyphen and OXR reads the word joined with it
(11-03, PTA-08 supplement: 'T2- weighted' for the layer's 'T2-' | 'weighted', OXR 'T2-weighted'). Whether such a
hyphen belongs to the word is the line-break spelling question (check/linebreak.py); this is only where both
readers kept it."""
import collections, re, unicodedata
import pymupdf
from ..readers import mineru as MR
from .. import layer as LY
from . import dropped as DR, linebreak as LB
from .two_readings import PRIMARY_PROSE
from .resolve import _base

LETTERS = re.compile(r"[^\W\d_]+")
MARK = ",.;:"
# the mark ends there: before a number it may be a reading's superscript run into it ('response ,39–44'), and
# dropping the space would make one token of the two
BEFORE_MARK = re.compile(r"([^\W\d_]+) ([,.;:])(?=[\s,.;:)\]]|$)")
AFTER_HYPHEN = re.compile(r"([^\W_]+)- ([^\W_]+)")


def _marks(pg):
    """(against, apart): a word's last letters (accents aside) with the mark after it, where the layer prints the mark
    against the word (a gap under a tenth of the height either way: 'A˚' '.,' overlap by 0.02 pt) and where it
    leaves a gap"""
    against, apart = set(), set()
    ws = LY.words(pg)
    for w in ws:
        against |= {m.group(1) + m.group(2) for m in re.finditer(r"([^\W\d_]+)([,.;:])", _base(w[4]))}
    for p, w in zip(ws, ws[1:]):
        h = w[3] - w[1]
        if not w[4] or w[4][0] not in MARK or abs(p[3] - w[3]) >= 0.2 * h:
            continue
        m = re.search(r"[^\W\d_]+$", _base(p[4]))
        if m and w[0] - p[2] > -0.1 * h:
            (against if w[0] - p[2] < 0.1 * h else apart).add(m.group() + w[4][0])
    return against, apart


def _oxr_marks(blocks):
    t = _base_text(" ".join(re.sub(r"<[^<>]*>", " ", b.get("content") or "") for b in blocks))
    return ({m.group(1) + m.group(2) for m in re.finditer(r"([^\W\d_]+)([,.;:])", t)},
            {m.group(1) + m.group(2) for m in re.finditer(r"([^\W\d_]+) ([,.;:])", t)}, t)


def _breaks(pg):
    """(left, right) of the words the layer breaks at a line-end hyphen, accents aside: the segment before the
    hyphen, the letters and digits after the break"""
    return {(_base(LB.DASH.split(l)[-1]), _base(re.match(r"[^\W_]*", r).group())) for l, r in LB.breaks(pg)}


def _base_text(t):
    """_base word by word, the spaces kept"""
    return " ".join(_base(x) for x in t.split())


def _layer(pg):
    """the page's letter runs in layer order, their set, the runs of 2-4 that follow one another, and whether the
    layer runs words together (more than one run in twenty of over 15 letters: 'theirutilityforROR')"""
    seq = []
    for w in LY.words(pg):
        seq += LETTERS.findall(unicodedata.normalize("NFKC", w[4]))
    glued = len(seq) > 0 and sum(len(t) > 15 for t in seq) > 0.05 * len(seq)
    return (*_rows(seq), glued)


def _oxr(blocks):
    seq = []
    for b in blocks:
        seq += LETTERS.findall(re.sub(r"<[^<>]*>", " ", unicodedata.normalize("NFKC", b.get("content") or "")))
    return _rows(seq)


def _rows(seq):
    return set(seq), {" ".join(seq[i:i + n]) for n in (2, 3, 4) for i in range(len(seq) - n + 1)}


def apply(pdf_path, mdir, md, layer_pages, second, reported=()):
    """(md, edits, issues, joined, counts): joined maps (page, block) to the tokens joined there; second: OXR pages
    or None; reported: (page, primary text) of spacing questions the two readings raised already"""
    pdf = pymupdf.open(pdf_path)
    edits, issues, joined, n = [], [], collections.defaultdict(list), collections.Counter()
    for pg_no, blocks in sorted(MR.pages(mdir).items()):
        if pg_no not in layer_pages:
            continue
        ows, orows = _oxr(second[pg_no]) if second and pg_no in second else (set(), set())
        omarks = _oxr_marks(second[pg_no]) if second and pg_no in second else None
        lay = marks = brk = None
        for uid, typ, part in MR.units(blocks):
            if typ not in PRIMARY_PROSE:
                continue
            raw = part.get("content") or ""
            cur = DR.locate(md, raw)
            if not cur:
                continue
            if lay is None:
                lay = _layer(LY.page(pdf, pg_no - 1))
            ws, rows, glued = lay
            toks = [(m.start(), m.end(), m.group(0)) for m in LETTERS.finditer(cur)]
            new, i, out, last = cur, 0, [], 0
            while i < len(toks):
                for k in (4, 3, 2):
                    run = toks[i:i + k]
                    if len(run) < k or any(cur[a[1]:b[0]] != " " for a, b in zip(run, run[1:])):
                        continue
                    if DR._in_math(cur, run[0][0]) or "\\" in cur[max(0, run[0][0] - 1):run[0][0]]:
                        continue
                    pieces = [t for _, _, t in run]
                    word = "".join(pieces)
                    spaced = " ".join(pieces)
                    if not (word in ws and spaced not in rows and any(p not in ws for p in pieces)) or spaced in orows:
                        continue
                    if word not in ows:
                        if not glued and not any(pg == pg_no and spaced in prim for pg, prim in reported):
                            n["spaces inside a word reported"] += 1
                            issues.append({"kind": "a space inside a word", "page": pg_no, "block": uid,
                                           "text": spaced, "layer": word,
                                           "why": "the text layer has the word whole; OXR does not confirm it"})
                        i += k
                        break
                    out.append(cur[last:run[0][0]] + word)
                    last = run[-1][1]
                    joined[(pg_no, uid)] += pieces
                    edits.append({"page": pg_no, "route": "spacing (text layer)", "by": "text layer",
                                  "old": " ".join(pieces), "new": word})
                    n["words joined"] += 1
                    i += k
                    break
                else:
                    i += 1
            if out:
                new = "".join(out) + cur[last:]
            if omarks:
                if marks is None:
                    marks, brk = _marks(LY.page(pdf, pg_no - 1)), _breaks(LY.page(pdf, pg_no - 1))
                cut = []
                for m in AFTER_HYPHEN.finditer(new):
                    l, r = _base(m.group(1)), _base(m.group(2))
                    if (l, r) in brk and not DR._in_math(new, m.start()) and f"{l}-{r}" in omarks[2] \
                            and f"{l}- {r}" not in omarks[2]:
                        cut.append(m.end(1) + 1)
                        edits.append({"page": pg_no, "route": "spacing after a line-break hyphen (text layer)",
                                      "by": "text layer", "old": m.group(0), "new": f"{m.group(1)}-{m.group(2)}"})
                        n["spaces after a line-break hyphen dropped"] += 1
                for m in BEFORE_MARK.finditer(new):
                    key = _base(m.group(1)) + m.group(2)
                    if DR._in_math(new, m.start()) or not (key in marks[0] and key not in marks[1]):
                        continue
                    if key in omarks[0] and key not in omarks[1]:
                        cut.append(m.end(1))
                        edits.append({"page": pg_no, "route": "spacing before a mark (text layer)", "by": "text layer",
                                      "old": m.group(0), "new": m.group(1) + m.group(2)})
                        n["spaces before a mark dropped"] += 1
                for at in sorted(cut, reverse=True):
                    new = new[:at] + new[at + 1:]
            if new != cur:
                md = md.replace(cur, new, 1)
    return md, edits, issues, joined, dict(n)


def covers(run, joined):
    """an unread run whose letter tokens were all joined into words in its block"""
    got = joined.get((run["page"], run["block"]))
    if not got:
        return False
    left = collections.Counter(got)
    toks = LETTERS.findall(run["text"])
    return bool(toks) and all(left[t] > 0 for t in toks) and not (collections.Counter(toks) - left)
