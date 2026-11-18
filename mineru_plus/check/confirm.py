"""Confirmation of the open issues before they go to the calling agent: an issue whose place the parse already prints
as the page does is closed here, not handed on.

11-18 文浩: the paper line's L1-3 found "no change needed" for 283 of 372 issues it had settled, each by an agent
session reading the page; mineru_plus is to close what it can itself, by script, then jev, then a model reading the
page, and hand on only the rest.

Each issue is turned into one question: a crop of its place on the page (the place marked in red where the issue is
about a few words) and the stretch of full.md printed there (from positions.json), with what the check suspected.
The question is the L1-3 one: does the parse print exactly what the page prints there?

  jev     the question with the crop, in both option orders; 'match' in both closes the issue, 'differ' in both keeps
          it, anything else goes on.
  model   the page_judge backend (mineru_plus/backends), crops stacked on numbered sheets, two sessions with the two
          answers listed in opposite order; 'match' in both closes the issue.

Script rules are not here: what a script can settle is settled in the check that raises the issue (the zero-width
characters, overprinted words, line numbers and table asterisks of 11-18 were all fixed there).

Which kinds are confirmed at all is the caller's choice (KINDS): a kind goes in only after its wrongful closings were
measured on the paper line's settled issues."""
import base64, collections, json, re
from pathlib import Path
import pymupdf
from .. import backends
from .. import layer as LY
from ..readers import mineru as MR
from . import jev, gemini as G, judge_cache as JC

ALL_KINDS = ("text layer not in the parse", "disagreement", "text only the primary read", "table", "display equation",
             "margin text differs from the text layer")
CONTEXT = 120          # characters of full.md on each side of the stretch printed in the place
LIMIT = 1500           # characters of the stretch itself (a long formula is given whole up to this)
TABLE_LIMIT = 8000     # a table is given whole up to this
SHORT = 300            # a marked place (a few words) whose stretch runs longer is narrowed to the issue's words
PER_SHEET = 6
# the kinds closed and how sure jev must be (confirm(): measured 11-18; tools/confirm_eval.py measures again)
KINDS = ("text layer not in the parse", "table", "text only the primary read")
MIN_P = 0.98

INSTR = ("The image is cut from a printed page of a scientific paper. Below it is the text a parser wrote for this "
         "part of the page: Markdown, with formulas in LaTeX and tables in HTML. The stretch between ⟦ and ⟧ is "
         "what the parser wrote for the place the issue is about (marked with a red box in the image when there is "
         "one). Decide whether that stretch prints exactly what the page prints there: every letter, digit, "
         "punctuation mark, symbol, subscript and superscript, in the same order, nothing missing and nothing extra; "
         "a space inside a word or a missing space between words is a difference, and so is another kind of dash "
         "(hyphen -, en dash –, em dash —) or of dots (. against · or ⋯ against …). "
         "Two notations that print the same symbol are the same (LaTeX \\cdots and ⋯, \\| and ‖, <sub>i</sub> and "
         "_{i}); line breaks and a hyphen that only breaks a word at a line end do not count. Judge what is printed, "
         "not what would be correct.")
MATCH = "The stretch prints exactly what the page prints at that place"
DIFFER = "The stretch differs from what the page prints at that place (or the image does not show enough to tell)"


def _rect_norm(pg, nb):
    """a box normalised to the displayed page as an unrotated rectangle"""
    W, H = pg.rect.width, pg.rect.height
    return pymupdf.Rect(nb[0] * W, nb[1] * H, nb[2] * W, nb[3] * H) * pg.derotation_matrix


def _load(out):
    out = Path(out)
    j = lambda p: json.loads((out / p).read_text()) if (out / p).exists() else []
    pos = j("positions.json") or {}
    spans = collections.defaultdict(list)
    for s, e, page, how, boxes in pos.get("spans", []):
        spans[page].append((s, e, [pymupdf.Rect(b) for b in boxes]))
    return {"md": (out / "full.md").read_text(errors="ignore"), "spans": spans,
            "dropped": {d["id"]: d for d in j("checks/dropped.json")},
            "dis": {d["id"]: d for d in j("checks/disagreements.json") if d.get("id")},
            "unread": j("checks/unread.json"),
            "pages": MR.pages(out / "readers" / "mineru") if (out / "readers" / "mineru").exists() else {}}


def _stretch(D, page, disp):
    """(start, end) of full.md printed in the displayed rectangle, widened to whole formulas and tables"""
    hit = [(s, e) for s, e, boxes in D["spans"].get(page, ()) if any(b.intersects(disp) and
           (b & disp).get_area() > 0.2 * min(b.get_area(), disp.get_area()) for b in boxes)]
    if not hit:
        return None
    a, b = min(s for s, _ in hit), max(e for _, e in hit)
    md = D["md"]
    for m in re.finditer(r"<table.*?</table>|\$\$.*?\$\$|(?<!\\)\$[^$\n]+\$", md[max(0, a - 3000):b + 3000], re.S):
        s, e = m.start() + max(0, a - 3000), m.end() + max(0, a - 3000)
        if s < b and e > a:
            a, b = min(a, s), max(b, e)
    while a > 0 and md[a - 1].isalnum():
        a -= 1
    while b < len(md) and md[b].isalnum():
        b += 1
    return a, b


def _in_block(D, page, block, span):
    """(start, end) in full.md of a span of a block's text, the block found once in full.md"""
    bl = dict(D["pages"].get(page, ())).get(block)
    raw = (bl or {}).get("content") or ""
    if not span or not raw or D["md"].count(raw) != 1:
        return None
    at = D["md"].find(raw)
    return at + span[0], at + span[1]


def _alnum(s):
    """letters and digits, without HTML tags and LaTeX command names"""
    return "".join(c.lower() for c in re.sub(r"<[^>]+>|\\[A-Za-z]+", "", s) if c.isalnum())


def _by_context(md, issue, at_md):
    ctx = issue.get("context") or ""
    m = re.search(r"\[\.\.\.\]|\[\[(.*?)\]\]", ctx, re.S)
    if not m:
        return None
    left, right = _alnum(ctx[:m.start()])[-10:], _alnum(ctx[m.end():])[:10]
    hint = issue.get("primary") if issue["kind"] == "disagreement" else issue.get("text")
    cands = {at_md} if at_md else set()
    if hint and hint.strip():
        cands |= {(x.start(), x.end()) for x in re.finditer(re.escape(hint), md)}
    ok = [(a, b) for a, b in cands if (not left or left in _alnum(md[max(0, a - 200):a])) and
          (not right or right in _alnum(md[b:b + 200]))]
    return ok[0] if len(ok) == 1 else None


def _places(D, doc, issue):
    """[(page, unrotated rectangle, mark, (start, end) in full.md or None)] of the issue, or None when its place is
    not known"""
    k = issue["kind"]
    if k == "text layer not in the parse":
        f = D["dropped"].get(Path(issue.get("crop") or "").stem)
        return [(f["page"], pymupdf.Rect(f["bbox"]), True, None)] if f else None
    if k == "disagreement":
        d = D["dis"].get(issue.get("id"))
        if not d or not d.get("bbox"):
            return None
        at = _in_block(D, d["page"], (d.get("blocks") or [None])[0], d.get("raw_span"))
        return [(d["page"], _rect_norm(LY.page(doc, d["page"] - 1), d["bbox"]), True, at)]
    if k == "text only the primary read":
        u = next((u for u in D["unread"] if u["page"] == issue["page"] and str(u.get("block")) == str(issue.get("block"))
                  and u.get("text") == issue.get("text") and u.get("bbox")), None)
        if u is None:
            return None
        at = _in_block(D, u["page"], u.get("block"), u.get("raw_span"))
        return [(u["page"], _rect_norm(LY.page(doc, u["page"] - 1), u["bbox"]), True, at)]
    if k in ("table", "display equation"):
        b = issue.get("bbox")
        if b is None:
            bl = dict(D["pages"].get(issue["page"], ())).get(issue.get("block"))
            b = bl.get("bbox") if bl else None
        return [(issue["page"], _rect_norm(LY.page(doc, issue["page"] - 1), b), False, None)] if b else None
    if k == "margin text differs from the text layer":
        out = []
        for pg in issue.get("pages") or []:
            bl = next((b for _, b in D["pages"].get(pg, ()) if b.get("type") == issue.get("type")
                       and (b.get("content") or "").strip() == issue.get("text") and b.get("bbox")), None)
            if bl is None:
                return None
            out.append((pg, _rect_norm(LY.page(doc, pg - 1), bl["bbox"]), True, None))
        return out or None
    return None


def _suspect(issue):
    k = issue["kind"]
    if k == "text layer not in the parse":
        return f"The PDF text layer has «{issue.get('layer')}» in the red box; the parser has «{issue.get('parse')}» there."
    if k == "disagreement":
        return f"Two readers of the page differ in the red box: «{issue.get('primary')}» and «{issue.get('oxr')}»."
    if k == "text only the primary read":
        return f"Only one reader has «{issue.get('text')}» in the red box; the other reader and the text layer do not."
    if k == "table":
        return "The table's cells could not all be checked against the page: compare every cell."
    if k == "display equation":
        return "Two readers wrote this formula differently: compare every symbol."
    if k == "margin text differs from the text layer":
        return f"The PDF text layer has «{issue.get('layer')}» in the red box; the parser wrote «{issue.get('text')}»."
    return ""


def _crop(doc, page, r, mark, path):
    pg = LY.page(doc, page - 1)
    pad = (-70, -30, 70, 30) if mark else (-12, -12, 12, 12)
    clip = (r + pad) & (pg.rect * pg.derotation_matrix)
    if mark:
        d2 = pymupdf.open(); d2.insert_pdf(doc, from_page=pg.number, to_page=pg.number); p2 = d2[0]
        p2.draw_rect(r + (-1.5, -1.5, 1.5, 1.5), color=(1, 0, 0), width=0.8)
        im = G._image(p2, clip, 220)
    else:
        im = G._image(pg, clip, 220)
    im.save(str(path))
    return str(path)


def items(out, pdf, issues, work, kinds=ALL_KINDS):
    """the questions: [{n (index in issues), id, kind, parts: [{page, crop, text}], suspect}] and the issues left out
    with the reason"""
    D, doc = _load(out), pymupdf.open(pdf)
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    res, skipped = [], {}
    for n, issue in enumerate(issues):
        if issue.get("kind") not in kinds:
            continue
        places = _places(D, doc, issue)
        if not places:
            skipped[n] = "place not found"; continue
        parts = []
        for j, (page, r, mark, at_md) in enumerate(places):
            pg = LY.page(doc, page - 1)
            if issue["kind"] in ("disagreement", "text only the primary read"):
                # a passage the check found by its words: the place in full.md whose surroundings are the issue's
                # context, found once (a block's offsets go stale when a later route edits it: PTA-123 main d0135
                # pointed into another 'y i')
                st = _by_context(D["md"], issue, at_md)
                if st is None:
                    # not found once by its context (11-18, 26 parses: 41 of 46 such 'text only' issues had their
                    # words, 'd' or 'nature portfolio |', in several places; 23 disagreements a respelled formula's
                    # words): what positions.json says is printed in the box, narrowed below when long
                    st = _stretch(D, page, r * pg.rotation_matrix)
            else:
                # what positions.json says is printed there
                st = _stretch(D, page, r * pg.rotation_matrix)
            if st is None:
                break
            a, b = st
            md = D["md"]
            if b - a > (TABLE_LIMIT if issue["kind"] == "table" else LIMIT if mark is False else SHORT):
                # a place inside a block positions.json boxes only as a whole (a page without a text layer): the
                # issue's own words, found once in the block
                hint = issue.get("text") or issue.get("primary") or issue.get("parse") or ""
                at = [m.start() for m in re.finditer(re.escape(hint), md[a:b])] if len(hint) >= 2 else []
                if len(at) != 1:
                    break
                a, b = a + at[0], a + at[0] + len(hint)
            text = md[max(0, a - CONTEXT):a] + "⟦" + md[a:b] + "⟧" + md[b:b + CONTEXT]
            parts.append({"page": page, "crop": _crop(doc, page, r, mark, work / "crops" / f"c{n}.{j}.png"),
                          "text": text})
        if len(parts) != len(places):
            skipped[n] = "text of the place not found in full.md"; continue
        res.append({"n": n, "id": f"c{n}", "kind": issue["kind"], "parts": parts, "suspect": _suspect(issue)})
    return res, skipped


def ask_jev(qs, work, min_p=None):
    """{id: 'match' | 'differ' | 'undecided' | ...} per part, the issue's answer the parts' agreement"""
    flat = []
    for q in qs:
        for j, p in enumerate(q["parts"]):
            img = "data:image/png;base64," + base64.b64encode(Path(p["crop"]).read_bytes()).decode()
            flat.append({"id": f"{q['id']}.{j}", "state": f"{q['suspect']}\n\nParser's text:\n{p['text']}",
                         "instructions": INSTR, "images": [img], "options": {"match": MATCH, "differ": DIFFER}})
    v = jev.ask(flat, work, "confirm", min_p) if flat else {}
    return {q["id"]: _all([v.get(f"{q['id']}.{j}", "not judged") for j in range(len(q["parts"]))]) for q in qs}


def _all(answers):
    if all(a == "match" for a in answers):
        return "match"
    if any(a == "differ" for a in answers):
        return "differ"
    return "undecided"


def ask_model(qs, work):
    """{id: 'match' | 'differ' | 'undecided' | 'not judged: ...'} from two page_judge sessions per sheet set"""
    work = Path(work); (work / "sheets").mkdir(parents=True, exist_ok=True)
    flat = [(q["id"], j, p) for q in qs for j, p in enumerate(q["parts"])]
    if not flat:
        return {}
    page = backends.get("page_judge")
    cache = JC.directory("page_judge")
    per = {}
    for s0 in range(0, len(flat), PER_SHEET * 4):
        chunk = flat[s0:s0 + PER_SHEET * 4]
        sheets = G._sheets([p["crop"] for _, _, p in chunk], work / "sheets")
        for order in ("a", "b"):
            opts = [("M", MATCH), ("D", DIFFER)] if order == "a" else [("D", DIFFER), ("M", MATCH)]
            lines = []
            for k, (qid, j, p) in enumerate(chunk, 1):
                q = next(x for x in qs if x["id"] == qid)
                lines.append(f"#{k}: {q['suspect']}\nParser's text:\n{G._shown(p['text'])}")
            body = (INSTR + "\n\nThe strips are numbered on the sheets in the order of the items.\nAnswers: " +
                    "; ".join(f'"{c}" = {t}' for c, t in opts) + "\n\nItems:\n" + "\n\n".join(lines) +
                    '\n\nAnswer with JSON only, one key per item: {"1": "' + opts[0][0] + '" | "' + opts[1][0] +
                    '", ...}')
            k = JC.key(page.info(), body, [JC.file_hash(x) for x in sheets])
            hit = JC.get(cache, k)
            if hit is not None:
                ans = hit["answer"]
            else:
                ans, use, err = page.session(body, sheets, work)
                if ans is not None:
                    JC.put(cache, k, {"answer": ans, "usage": use})
            for k2, (qid, j, _) in enumerate(chunk, 1):
                x = str((ans or {}).get(str(k2), "")).strip().upper()
                per.setdefault((qid, j), {})[order] = ("match" if x == "M" else "differ" if x == "D" else
                                                       ("not judged" if ans is None else "no answer"))
    out = {}
    for q in qs:
        parts = []
        for j in range(len(q["parts"])):
            v = per.get((q["id"], j), {})
            parts.append(v.get("a") if v.get("a") == v.get("b") and v.get("a") in ("match", "differ") else "undecided")
        out[q["id"]] = _all(parts)
    return out


def confirm(out, pdf, issues, work, kinds=KINDS):
    """(issues left open, issues closed, stats). An issue is closed where jev answers 'match' in both option orders,
    each with probability at least MIN_P, and the page judge answers 'match' in both sessions; every other issue is
    left open. Measured 11-18 on the paper line's 433 settled issues of 26 documents: of the kinds in KINDS, 52 of the
    252 'no change' closed and none of the 46 'edit'; the two judges each closed edits on their own (jev 'match' alone
    14, among them the text layer's '⊮' the page prints where the parse has '\\mathbb{1}'; both at a lower
    probability 3), and in disagreements and display equations both closed edits at any probability."""
    qs, skipped = items(out, pdf, issues, work, kinds)
    vj = ask_jev(qs, Path(work) / "jev", MIN_P)
    sure = [q for q in qs if vj.get(q["id"]) == "match"]
    vm = ask_model(sure, Path(work) / "model") if sure else {}
    by = {q["n"] for q in sure if vm.get(q["id"]) == "match"}
    left = [i for n, i in enumerate(issues) if n not in by]
    closed = [{**issues[n], "closed_by": "jev and the page judge"} for n in sorted(by)]
    stats = {"asked": len(qs), "not asked": len(skipped), "jev sure of a match": len(sure), "closed": len(closed),
             "left open": len(left)}
    return left, closed, stats
