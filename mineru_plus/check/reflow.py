"""Sentences the markdown breaks: a paragraph that ends mid-sentence and the text that continues it.

MinerU writes blocks in reading order, but a figure, table or caption that sits between the two halves of a sentence
on the page (a page or column break) lands between them in full.md, and a paragraph that runs over a column or page
break becomes two paragraphs. 10-29, 9 papers checked on the page images (about 120 pages): the order of text blocks
was wrong at 2 places, both at a figure (a caption split over two columns; body text MinerU typed as a figure note),
while floats split a sentence at about 50 places in 31 documents. The second half of a sentence cut by such a break
is far from the first in full.md, and line pointers of the next layer cannot cover the sentence in one range.

For each text block that ends without closing punctuation, the next text block in reading order is the candidate
continuation when only floats (figures, tables, charts and their captions and notes) sit between them. jev is asked
on the two passages whether the second continues the sentence the first breaks off (both option orders). Continued:
the two are joined into one paragraph and the floats between them move after it (moved, not changed; a hyphen at the
join is kept or dropped by the document's own usage of the joined word). Not continued, or undecided: an open issue
with the page, since the sentence's continuation is elsewhere (a misplaced block) or the break is real."""
import collections, re
from ..readers import mineru as MR
from . import jev
from .dropped import locate

FLOATS = {"image", "image_caption", "image_footnote", "table", "table_caption", "table_footnote", "chart",
          "chart_caption", "chart_footnote"}
CLOSED = re.compile(r"[.?!:;)\]\"”’](\s*(<sup>[^<]*</sup>|\[[\d,–\- ]+\]))?\s*$")
INSTR = ("Two passages from a scientific paper. In the PDF, the first breaks off at the end of a column or page, or "
         "next to a figure. Decide whether the second passage is the direct continuation of the first passage's "
         "unfinished sentence (read the end of the first and the start of the second as one sentence).")


def _plain(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


MARGIN = {"header", "footer", "page_number", "aside_text", "page_footnote"}     # not in the running text
AFFIL = re.compile(r"^\d{1,2}[A-Z]")          # a numbered affiliation or footnote entry


def find(mdir, md):
    """candidate continuations of each broken sentence: [{id, page_a, uid_a, cands: [{page_b, uid_b, b, k}], a,
    floats}]; cands are the next text blocks in reading order (up to 3), the
    first one the plain candidate, later ones for a sentence a footnote or affiliation block interrupts"""
    seq = []
    for pg, bl in sorted(MR.pages(mdir).items()):
        for uid, t, p in MR.units(bl):
            if t not in MARGIN:
                seq.append((pg, uid, t, p.get("content") or ""))
    out = []
    for i, (pa, ua, ta, ra) in enumerate(seq):
        pr = _plain(ra)
        if ta != "text" or len(pr) < 30 or CLOSED.search(pr) or AFFIL.match(pr):
            continue
        a = locate(md, ra)
        if not a:
            continue
        cands, between, j = [], collections.Counter(), i + 1
        while j < len(seq) and len(cands) < 3:
            pb, ub, tb, rb = seq[j]
            j += 1
            if tb in FLOATS:
                between[tb] += 1; continue
            if tb != "text":
                break                         # a heading, list or equation: the sentence does not run past it
            b, pl = locate(md, rb), _plain(rb)
            ok = bool(b) and len(pl) >= 3 and not AFFIL.match(pl) and not (len(pr) < 120 and len(pl) < 120)
            cands.append({"page_b": pb, "uid_b": ub, "b": b, "k": len(cands), "floats": dict(between), "ok": ok})
            between[tb] += 1
        cands = [c for c in cands if c["ok"]]
        if cands:
            out.append({"id": f"j{pa}.{ua}", "page_a": pa, "uid_a": ua, "a": a, "cands": cands})
    return out


def judge(found, work):
    qs = []
    for f in found:
        for c in f["cands"]:
            body = f"First ends: «…{_plain(f['a'])[-300:]}» Second begins: «{_plain(c['b'])[:300]}…»"
            qs.append({"id": f"{f['id']}|{c['k']}", "state": "Two passages of a scientific paper.", "instructions": INSTR,
                       "options": {"continues": "The second passage continues the first passage's sentence. " + body,
                                   "new": "The second passage does not continue the first passage's sentence. " + body}})
    v = jev.ask(qs, work, "reflow")
    for f in found:
        for c in f["cands"]:
            c["verdict"] = v.get(f"{f['id']}|{c['k']}", "not judged")
        # the next text block continues it; or it does not and a later one (lower-case start, so not a new sentence)
        # does: the blocks between (a page footnote, affiliations typed as text) move with the floats
        first = f["cands"][0]
        later = [c for c in f["cands"] if c["k"] > 0 and c["verdict"] == "continues" and _plain(c["b"])[:1].islower()]
        if first["k"] == 0 and first["verdict"] == "continues":
            f["verdict"], f["chosen"] = "continues", first
        elif (first["k"] > 0 or first["verdict"] == "new") and later and len(_plain(f["a"])) >= 100:
            # only a paragraph's broken sentence skips blocks (10-29: a heading typed as text took the next
            # column's lower-case continuation of another sentence)
            f["verdict"], f["chosen"] = "continues", later[0]
        else:
            f["verdict"], f["chosen"] = (first["verdict"] if first["k"] == 0 else "undecided"), first
        f["b"], f["page_b"], f["floats"] = f["chosen"]["b"], f["chosen"]["page_b"], f["chosen"]["floats"]
    return found


def _joiner(md, a, b):
    """(new end of a, joiner): a line-end hyphen is dropped when the document writes the joined word and not the
    hyphenated one, kept when only the hyphenated form occurs; otherwise kept and reported"""
    m = re.search(r"([A-Za-z]+)-$", a.rstrip())
    n = re.match(r"([A-Za-z]+)", b)
    if not m or not n:
        return a.rstrip(), " ", None
    joined, hyph = m.group(1) + n.group(1), m.group(1) + "-" + n.group(1)
    cj = len(re.findall(r"\b" + re.escape(joined) + r"\b", md, re.I))
    ch = len(re.findall(r"\b" + re.escape(hyph) + r"\b", md, re.I))
    if cj and not ch:
        return a.rstrip()[:-1], "", None
    return a.rstrip(), "", (None if ch and not cj else "hyphen kept at the join, the document's usage does not decide")


def apply(md, found):
    """returns (md, edits, issues, counts)"""
    edits, issues, n = [], [], collections.Counter()
    for f in found:
        n[f["verdict"]] += 1
        if f["verdict"] != "continues":
            if not re.match(r"[a-z(,;]", _plain(f["b"])):
                n["next block starts a new sentence"] += 1     # a heading or author line typed as text: no defect
                continue
            issues.append({"kind": "sentence breaks off", "why": f"jev {f['verdict']}: the next text block does not "
                           "continue it; its continuation may be a block placed elsewhere", "page": f["page_a"],
                           "end": _plain(f["a"])[-120:], "next": _plain(f["b"])[:120], "next_page": f["page_b"]})
            continue
        ia = md.find(f["a"])
        ib = md.find(f["b"], ia + len(f["a"])) if ia != -1 else -1
        if ia == -1 or ib == -1 or md.count(f["a"]) != 1:
            n["not placed"] += 1
            issues.append({"kind": "sentence breaks off", "why": "continued (jev); not found once in full.md",
                           "page": f["page_a"], "end": _plain(f["a"])[-120:], "next": _plain(f["b"])[:120]})
            continue
        a_end, b_end = ia + len(f["a"]), ib + len(f["b"])
        chunk = md[a_end:ib]
        if re.search(r"^#", chunk, re.M) or (f["chosen"]["k"] == 0 and f["floats"].get("text")):
            n["heading between"] += 1
            continue
        head, joiner, note = _joiner(md, f["a"], f["b"])
        if note:
            issues.append({"kind": "join hyphen", "why": note, "page": f["page_a"], "end": head[-60:], "next": f["b"][:60]})
        new = head + joiner + f["b"] + ("\n\n" + chunk.strip() if chunk.strip() else "")
        md = md[:ia] + new + md[b_end:]
        wa, wb = f["a"].rstrip().split()[-1], f["b"].split()[0]
        edits.append({"id": f["id"], "page": f["page_a"], "route": "reflow", "by": "jev",
                      "old": f"{wa} {wb}", "new": (head.split()[-1] if head.split() else "") + joiner + wb,
                      "moved": dict(f["floats"]), "skipped_blocks": f["chosen"]["k"]})
        n["joined"] += 1
        n["floats moved"] += 1 if chunk.strip() else 0
    return md, edits, issues, dict(n)
