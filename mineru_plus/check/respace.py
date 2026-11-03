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
it is reported."""
import collections, re, unicodedata
import pymupdf
from ..readers import mineru as MR
from .. import layer as LY
from . import dropped as DR
from .two_readings import PRIMARY_PROSE

LETTERS = re.compile(r"[^\W\d_]+")


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
        lay = None
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
