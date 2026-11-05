"""A punctuation mark the parse has twice where the page prints it once. The reader puts the mark that ends a formula
inside the formula, and writes the same mark again after it ('(N = 156) ,$ , and TCGA', '0.05 ,$ , Kang'), or doubles
it in prose ('0.001;;'). No other check sees it: the two readings are compared outside formulas, and the text layer
is searched for what the parse lacks, not for what it has in excess (11-04: 14 such places in 26 documents of the
paper line, one of them found by hand by L1-3). The text layer settles each: where every place it has the words
after the marks has the mark once, the copy inside the formula (in prose, the second) is deleted; where the layer has
it twice, as printed ('reasons: : 1)'), it stays; where the layer does not have the words, it is an open issue."""
import re
import pymupdf
from .. import layer as LY

# the same mark twice, with only spaces, closing braces, an environment's end or the formula's closing '$' between
DOUBLED = re.compile(r"([,;:])((?:\s|\}|\\end\{[a-z]+\*?\}|\\right\s*[.)\]]|\$)*)\1")
WORD = re.compile(r"[A-Za-z]+|\d+")


def _after(md, i, n=2):
    """the first words after position i, up to the next formula"""
    rest = md[i:i + 120].split("$")[0]
    return WORD.findall(rest)[:n]


def find(md):
    return [{"start": m.start(), "end": m.end(), "mark": m.group(1), "between": m.group(2),
             "after": _after(md, m.end()), "context": md[max(0, m.start() - 60):m.end() + 40]}
            for m in DOUBLED.finditer(md)]


def judge(pdf, found):
    """for each place: 'once' (every place the layer has the following words has the mark once before them),
    'twice' (the layer has the mark twice there) or 'not in the layer'"""
    if not found:
        return found
    doc = pymupdf.open(pdf)
    pages = [(i + 1, LY.text(LY.page(doc, i))) for i in range(len(doc))]
    for f in found:
        f["verdict"], f["page"] = "not in the layer", None
        if not f["after"]:
            continue
        # two words after the marks; where the layer lacks them together (the second in a formula's font,
        # 11-04, PTA-11 MOESM1: 'with count being' layered 'with being'), the first alone
        for words in (f["after"], f["after"][:1]):
            rx = re.compile(r"(" + re.escape(f["mark"]) + r"\s*)?" + re.escape(f["mark"]) + r"[^A-Za-z0-9,;:]*"
                            + r"[^A-Za-z0-9]*".join(map(re.escape, words)) + r"(?![A-Za-z])")
            hits = [(p, m) for p, t in pages for m in rx.finditer(t)]
            if hits:
                break
        if hits:
            f["page"] = hits[0][0]
            f["verdict"] = "twice" if any(m.group(1) for _, m in hits) else "once"
    return found


def apply(md, found):
    edits, issues, count = [], [], {"once": 0, "twice": 0, "not in the layer": 0}
    for f in sorted(found, key=lambda f: -f["start"]):
        count[f["verdict"]] += 1
        if f["verdict"] == "twice":
            continue
        if f["verdict"] == "not in the layer":
            issues.append({"kind": "punctuation doubled", "why": "the parse has the mark twice; the text layer does "
                           "not have the words after it, check by hand", "page": f["page"], "parse": f["context"]})
            continue
        s, e = f["start"], f["end"]
        old = md[s:e]
        # a formula between: the copy inside it goes, with the space before it; in prose the second copy goes
        new = old[1:] if f["between"].strip() else old[:-1]
        if f["between"].strip() and s > 0 and md[s - 1] == " ":
            s, old = s - 1, " " + old
        edits.append({"id": f"p{f['start']}", "page": f["page"], "route": "punctuation", "by": "text layer",
                      "old": old, "new": new})
        md = md[:s] + new + md[e:]
    return md, edits[::-1], issues, count
