"""Formulas full.md cannot render (11-19, 文浩: 「这个是我们确定一定不对的，不能想办法解决？」).

Every formula of full.md is rendered with KaTeX (bundled in katex/; MathJax was not tried). A formula KaTeX rejects, and
a '$' that opens no formula, print as broken TeX: they are errors for certain, whatever the page prints. Code (fenced
blocks and inline code) is not read, as viewers do not read it as math either. A currency sign is '\\$' in MinerU's
markdown (PTA-555: 8 of 8); an unescaped one prints wrong too and is reported like any stray '$'. On the 26 documents
of eval_1118, 4 of 1214 formulas were rejected (3 double superscripts, a run of 32 '\\begin{aligned}') and one
paragraph had a stray '$'.

One repair, written only where the result renders:
  scripts   'X ^ {A} ^ {T}' (KaTeX: double superscript) becomes 'X ^ {A} {}^ {T}': the primary's tokens in their
            order, with '{}' added so that the second script sits on an empty base (what MinerU's text does not say:
            what it attaches to). Whether that reading is the page's is the business of the other checks.
Any other failure is an open issue, one a sentence, with KaTeX's message and, where it is located, the second reader's
reading of the stretch around it ('oxr', and whether it renders) as a candidate for whoever closes the issue. The
stretch runs between the nearest three words before and after the failure (outside formulas, in the same paragraph)
that occur once each in the second reader's text, in that order; none is located at a paragraph's start or end (the
second reader's blocks are not the primary's paragraphs), in a paragraph or stretch with code, a paragraph with a '$'
before a number (a currency sign?), a stretch whose '$' pair across two of the second reader's blocks, or one with a
blank line. The second reader's reading is not written into full.md, not even where it differs only in where its '$'
stand (11-19: eleven review rounds found a way through every comparison of two readings tried, moving a '$' included,
and a clean wrong formula hides what a broken one shows)."""
import json, re, shutil, subprocess
from pathlib import Path

KATEX = Path(__file__).parent / "katex" / "katex.min.js"
CODE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$|`[^`\n]+`", re.S | re.M)
SPAN = re.compile(r"\$\$((?:\\\$|[^$])+?)\$\$|(?<![\\$])\$((?:\\\$|[^$])+?)\$", re.S)
PARA = re.compile(r"(?:(?!\n[ \t]*\n).)+", re.S)
TOK = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+")       # a number whole: an anchor never ends inside one
TAG = re.compile(r"</?(?:sup|sub|br|i|b|em|strong|span|div|p|u|s|small|table|thead|tbody|tr|td|th|img|a|mark|del|"
                 r"ins|hr|ul|ol|li|font|center)(?:\s+[A-Za-z_:][\w:.-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s<>\"'=`]+))*\s*"
                 r"/?>", re.I)
CMD = re.compile(r"\\[A-Za-z]+")
END = re.compile(r"[.!?](?=\s)")
SCRIPT_ERR = re.compile(r"Double (?:superscript|subscript)")
ANCHOR = 3
JS = r"""const k=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{
process.stdout.write(JSON.stringify(JSON.parse(s).map(([t,disp])=>{try{k.renderToString(t,{displayMode:disp,
throwOnError:true,strict:'ignore'});return null}catch(e){return [String(e.message),e.position===undefined?null:e.position]}})))});"""


class KatexError(RuntimeError):
    """KaTeX could not be run (node failed, timed out or answered nothing readable)"""


def available():
    return shutil.which("node") is not None and KATEX.exists()


def errors(items):
    """items: [(tex, display)] -> [None | (KaTeX's message, position in tex or None)]"""
    if not items:
        return []
    try:
        r = subprocess.run(["node", "-e", JS, str(KATEX)], input=json.dumps(items), capture_output=True, text=True,
                           timeout=600)
        if r.returncode:
            raise KatexError(f"node exited {r.returncode}: {r.stderr[-400:]}")
        out = json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        raise KatexError(str(e)[:400]) from e
    if not isinstance(out, list) or len(out) != len(items):
        raise KatexError("KaTeX answered for another number of formulas")
    return out


def _uncode(text):
    """text with code blanked out (same length, line breaks kept)"""
    return CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)


def _mask(text):
    """(text with code, formulas and '\\$' blanked out, same length; formulas [(start, end, tex, display)])"""
    text = _uncode(text)
    spans = [(m.start(), m.end(), m.group(1) if m.group(1) is not None else m.group(2), m.group(1) is not None)
             for m in SPAN.finditer(text)]
    out = list(text)
    for a, b, _, _ in spans:
        out[a:b] = " " * (b - a)
    return "".join(out).replace("\\$", "  "), spans


def find(md):
    """[{start, end, tex, display}] for every formula, and [position] of each '$' that opens no formula"""
    formulas, stray = [], []
    for p in PARA.finditer(_uncode(md)):
        masked, spans = _mask(p.group())
        for a, b, _, d in spans:                  # the formula as written (code inside it was blanked for the scan)
            a, b = p.start() + a, p.start() + b
            formulas.append({"start": a, "end": b, "tex": md[a + 2:b - 2] if d else md[a + 1:b - 1], "display": d})
        stray += [p.start() + i for i, c in enumerate(masked) if c == "$"]
    return formulas, stray


def unscript(tex, pos):
    """'{}' before the second of two scripts KaTeX points at; None where it does not point at a script"""
    for i in (pos, pos - 1) if isinstance(pos, int) else ():
        if 0 <= i < len(tex) and tex[i] in "^_":
            return tex[:i] + "{}" + tex[i:]
    return None


def _tokens(text):
    masked, _ = _mask(text)
    # markup such as <sup>, and command names a stray '$' left outside formulas ('\mathrm'), are no words
    masked = CMD.sub(lambda m: " " * len(m.group()), TAG.sub(lambda m: " " * len(m.group()), masked))
    return [(m.group().lower(), m.start(), m.end()) for m in TOK.finditer(masked)]


def _sentence(md, a, b):
    """the bounds of the sentences of md's paragraph that hold [a, b)"""
    p = next(p for p in PARA.finditer(md) if p.start() <= a < p.end())
    masked, _ = _mask(p.group())
    ends = [m.end() + p.start() for m in END.finditer(masked)]
    s = max([e for e in ends if e <= a], default=p.start())
    e = min([e for e in ends if e >= b], default=p.end())
    while s < e and md[s].isspace():
        s += 1
    return s, e


def _oxr_text(oxp):
    """(the second reader's blocks joined by spaces, the (start, end) of each block in it)"""
    parts = [str(b.get("content") or "") for pg in sorted(oxp, key=str) if isinstance(oxp[pg], list)
             for b in oxp[pg] if isinstance(b, dict)]
    bounds, at = [], 0
    for p in parts:
        bounds.append((at, at + len(p)))
        at += len(p) + 1
    return " ".join(parts), bounds


def _oxr_tokens(text, bounds):
    """the tokens of the second reader's text, block by block: a '$' never pairs with one in another block"""
    return [(w, s + x, s + y) for s, e in bounds for w, x, y in _tokens(text[s:e])]


def _dollars(t):
    return len(re.findall(r"(?<!\\)\$", _uncode(t)))


def _anchor(toks, idx, words, step):
    """the ANCHOR consecutive tokens nearest idx (going back for step -1, forward for 1) that occur once in words:
    (first token index in toks, index in words) or None"""
    n = len(toks)
    starts = range(idx - ANCHOR, -1, -1) if step < 0 else range(idx, n - ANCHOR + 1)
    for k in starts:
        seq = [w for w, _, _ in toks[k:k + ANCHOR]]
        at = [i for i in range(len(words) - ANCHOR + 1) if words[i:i + ANCHOR] == seq]
        if len(at) == 1:
            return k, at[0]
    return None


def reread(md, a, b, oxr):
    """(start, end, the second reader's reading) of the stretch of md around [a, b); or why none is located. The
    reading is a candidate for whoever closes the issue: nothing here says it is the page's"""
    p = next(p for p in PARA.finditer(md) if p.start() <= a < p.end())
    s, e = p.start(), p.end()
    if "`" in md[s:e] or "~~~" in md[s:e]:
        return "the paragraph holds code"
    if re.search(r"\$\d", _mask(md[s:e])[0]):
        return "the paragraph has a '$' before a number (a currency sign not escaped?)"
    toks = _tokens(md[s:e])
    oxr_text, bounds = oxr
    ot = _oxr_tokens(oxr_text, bounds)
    words = [w for w, _, _ in ot]
    before = sum(1 for t in toks if s + t[2] <= a)
    after = next((k for k, t in enumerate(toks) if s + t[1] >= b), len(toks))
    L, R = _anchor(toks, before, words, -1), _anchor(toks, after, words, 1)
    # both anchors, also at a paragraph's start or end: the second reader's blocks are not the primary's paragraphs,
    # so a block's edge does not tell where its reading of the failure ends
    if not L or not R:
        return "no three words next to the failure on both sides occur once in the second reader's text"
    if not L[1] + ANCHOR <= R[1] <= L[1] + ANCHOR + 3 * (R[0] - L[0]) + 20:
        return "the words around the failure are in another place or order in the second reader's text"
    ms, me = s + toks[L[0] + ANCHOR - 1][2], s + toks[R[0]][1]
    os_, oe = ot[L[1] + ANCHOR - 1][2], ot[R[1]][1]
    new = oxr_text[os_:oe]
    if "`" in new or "~~~" in new:
        return "the second reader's stretch holds code"
    if any(_dollars(oxr_text[max(x, os_):min(y, oe)]) % 2 for x, y in bounds if x < oe and y > os_):
        return "the second reader's stretch has a '$' paired across two of its blocks"
    if re.search(r"\n[ \t]*\n", new):
        return "the second reader's stretch breaks the paragraph"
    return ms, me, new


def _key(f):
    """what a failure is, block or md alike: a formula's TeX without spaces and braces (MinerU's text spaces a
    formula as it likes: 'c e l l', '\\mathrm { cell }'), or a stray '$'"""
    return ("$",) if f is None else ("tex", re.sub(r"[\s{}]", "", f["tex"]))


def _block_failures(pages):
    """[(page, block, key)] of each formula the primary's blocks hold that KaTeX rejects, and of each stray '$' in
    them; an equation block's content is its display formula (MinerU writes it without '$$')"""
    order = lambda k: (0, k, "") if isinstance(k, int) else (1, 0, str(k))
    items, at, out = [], [], []
    for pg in sorted(pages, key=order):
        for item in pages[pg] if isinstance(pages[pg], list) else []:
            if not (isinstance(item, (tuple, list)) and len(item) == 2 and isinstance(item[1], dict)):
                continue
            bi, c = item[0], str(item[1].get("content") or "")
            if item[1].get("type") == "equation" and "$" not in c:
                fs, stray = [{"tex": c, "display": True}], []
            else:
                fs, stray = find(c)
            for f in fs:
                items.append((f["tex"], f["display"]))
                at.append((pg, bi, _key(f)))
            out += [(pg, bi, _key(None))] * len(stray)
    return out + [w for w, e in zip(at, errors(items)) if e]


def _where(failures, md_count, key):
    """(page, block) of an md failure: the one block that holds every failure of its kind, as many as md has --
    where md has failures of a kind the blocks have more or fewer of, or several blocks have them, (None, None):
    no place beats a wrong one. (11-19, rounds 12-20: matching md's text around a failure against the blocks' named
    a wrong block somewhere every time -- md and a block cut their text apart differently, and md is edited; here
    the failure itself is read in MinerU's blocks, as the other checks read their findings there). A wrong place
    remains possible only where a block's failure is not in md (edited away, or a '$' md pairs across blocks) and md
    has as many of that kind from outside the blocks (a caption); on eval_1118 with a '$' put into 4972 paragraphs:
    4741 placed right, 231 not placed (a stray '$' is a kind without content: two blocks with one place none), 0
    wrong (review round 21)"""
    held = [(pg, bi) for pg, bi, k in failures if k == key]
    return held[0] if held and len(held) == md_count.get(key, 0) and len(set(held)) == 1 else (None, None)


def _renders(text):
    fs, stray = find(text)
    return not stray and not any(errors([(f["tex"], f["display"]) for f in fs]))


def _braced(f):
    tex = f["tex"]
    for _ in range(8):
        err = errors([(tex, f["display"])])[0]
        if not err:
            return tex
        if not SCRIPT_ERR.search(err[0]):
            return None
        tex = unscript(tex, err[1])
        if tex is None:
            return None
    return None


def repair(md, pages, oxp):
    """md with the formulas KaTeX rejects mended where a repair renders: (md, counts, issues, repairs).
    Raises KatexError where KaTeX cannot be run."""
    pages, oxp = (pages if isinstance(pages, dict) else {}), (oxp if isinstance(oxp, dict) else None)
    fs, stray = find(md)
    errs = errors([(f["tex"], f["display"]) for f in fs])
    bad = [(f["start"], f["end"], f, err) for f, err in zip(fs, errs) if err]
    bad += [(p, p + 1, None, ("a '$' that opens no formula", None)) for p in stray]
    oxr = _oxr_text(oxp) if oxp else None
    md_count, failures = {}, None   # failures: the blocks', read once an issue needs a place
    for _, _, f, _ in bad:
        md_count[_key(f)] = md_count.get(_key(f), 0) + 1
    edits, still = [], []           # edits: (start, end, new text, repair); still: (position, issue, its sentence)
    for a, b, f, (msg, _) in sorted(bad, key=lambda x: x[0]):
        if f is not None and SCRIPT_ERR.search(msg):
            tex = _braced(f)
            if tex is not None and md[a:b].replace(f["tex"], tex, 1) != md[a:b]:
                edits.append((a, b, md[a:b].replace(f["tex"], tex, 1), {"how": "scripts braced", "was": f["tex"],
                                                                        "now": tex}))
                continue
        s, e = _sentence(md, a, b)
        same = [i for _, i, k in still if k == (s, e)]
        if same:                                      # one issue a sentence, naming each of its failures
            same[0]["found"] += f" Also in this sentence: {md[a:b] if f is not None else repr('$')} ({msg})."
            continue
        if failures is None:
            failures = _block_failures(pages)
        pg, bi = _where(failures, md_count, _key(f))
        issue = {"kind": "formula that does not render", "page": pg, "block": bi,
                 "parse": md[a:b] if f is not None else md[max(0, a - 80):a + 80], "error": msg,
                 "found": f"KaTeX cannot render it ({msg}). "}
        r = reread(md, a, b, oxr) if oxr and oxr[0].strip() else "no second reading"
        if isinstance(r, tuple):
            issue.update(stretch=md[r[0]:r[1]], oxr=r[2], oxr_renders=_renders(r[2]))
            issue["found"] += ("The second reader reads the stretch around it as 'oxr'; not taken, as nothing here "
                               "decides whether a reading of a formula is the page's.")
        else:
            issue["found"] += f"No second reading of it located: {r}."
        still.append((a, issue, (s, e)))
    for s, e, new, _ in sorted(edits, key=lambda x: -x[0]):
        md = md[:s] + new + md[e:]
    done = [r for _, _, _, r in edits]
    issues = [i for _, i, _ in still]
    count = {"formulas": len(fs), "rejected by KaTeX": sum(1 for x in errs if x), "stray dollars": len(stray),
             "scripts braced": sum(1 for r in done if r["how"] == "scripts braced"), "left open": len(still)}
    return md, count, issues, done
