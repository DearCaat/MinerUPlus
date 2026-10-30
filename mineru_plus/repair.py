"""Write the settled disagreements into full.md, then accept the result independently.

An edit is made only where the place is found without ambiguity: the disagreement lies in one block of the primary
reading and that block's text occurs once in full.md. Character edits are written at the raw span the comparison
recorded (char_edits; a formula they touch is written out as linear text); line-break spellings and omissions at the
passage, found once in the block (with up to three words of left context if needed). Anything else becomes an open
issue for the calling agent.

Acceptance (accept): the token multiset of the repaired markdown must differ from the original by exactly the tokens
the edits removed and added; nothing else may change.
"""
import collections, difflib, re
from .check import two_readings as TR
from .check.two_readings import toks, MARKUP, LINK
from .readers import mineru as MR

# Character edits were off while the judge was jev (it "corrected" printed typos: knowedge, radiopathomic, 0·05).
# On 10-28 Gemini passed the printed-typo test (0 wrong among decided, check/gemini.py); edits are on, undecided items
# go to the calling agent with their crop.
CHARACTER_EDITS = True
HY = "-‐‑­"
HYC = re.escape(HY)             # for use inside a character class


def _pattern(ts):
    return r"\s*".join(re.escape(t) for t in ts)


def _locate(text, s):
    for k in (0, 1, 2, 3):
        left = s["left"][-k:] if k else []
        m = list(re.finditer(_pattern(left + s["primary_toks"]) if left else _pattern(s["primary_toks"]), text))
        if len(m) == 1:
            if not left:
                return m[0].span()
            inner = re.search(_pattern(s["primary_toks"]) + r"$", m[0].group(0))
            return m[0].start() + inner.start(), m[0].end()
        if not m:
            return None
    return None


def _new_span(span_text, s):
    if s["route"] == "omission":         # the dropped run goes between the two anchor tokens, as the layer prints it
        m1 = re.compile(re.escape(s["primary_toks"][0])).search(span_text)
        m2 = re.compile(re.escape(s["primary_toks"][1])).search(span_text, m1.end())
        gap = span_text[m1.end():m2.start()]      # the primary's own separator (a space, or a newline between items)
        if s["insert"].endswith(" "):
            return span_text[:m1.end()] + s["insert"].rstrip() + (gap or " ") + span_text[m2.start():]
        return span_text[:m1.end()] + s["insert"] + span_text[m2.start():]
    if s["route"] == "line-break hyphen":
        left, right = s["split"].split("-|")
        if s["verdict"] == "hyphen":
            return re.sub(rf"({re.escape(left)})\s*({re.escape(right)})", r"\1-\2", span_text, count=1)
        return re.sub(rf"({re.escape(left)})\s*[{HYC}]\s*({re.escape(right)})", r"\1\2", span_text, count=1)
    if len(s["primary_toks"]) != len(s["oxr_toks"]):   # same letters, hyphens differ: the printed form, no spaces at hyphens
        return re.sub(rf"\s*([{HYC}])\s*", r"\1", " ".join(s["oxr_toks"]))
    out, pos = [], 0                      # characters: token by token, separators kept
    for t, o in zip(s["primary_toks"], s["oxr_toks"]):
        m = re.compile(re.escape(t)).search(span_text, pos)
        out.append(span_text[pos:m.start()] + o)
        pos = m.end()
    return "".join(out) + span_text[pos:]


def plan(s):
    """what to do with one settled disagreement: 'edit', 'keep' or an open-issue reason"""
    v = s.get("verdict")
    if s["route"] == "form only":
        return "keep"
    if s["route"] == "omission":
        return "edit"
    if s["route"] == "line-break hyphen":
        if v not in ("hyphen", "joined"):
            return f"open: spelling not settled ({v})"
        has = any(c in s["primary"] for c in HY)
        return "keep" if (v == "hyphen") == has else "edit"
    if v == "primary":
        return "keep"
    if v == "oxr" and not CHARACTER_EDITS:
        return "open: the judge reads the OXR side; not written (character edits are off)"
    if v != "oxr":
        return f"open: page reading not settled ({v})"
    if s.get("raw_span") is None:
        return "open: spans two blocks"
    return "edit"


def _letters(x):
    return re.sub(rf"[\s{HYC}]", "", x)


def _in_md(md, block):
    """the block's text as it stands once in full.md; a block ending in a line-break hyphen MinerU joined with the
    next block's first word (10-29: 'align-' + 'ment' written 'alignment') is found without the hyphen"""
    if md.count(block) == 1:
        return block
    if block[-1:] in HY and md.count(block[:-1]) == 1:
        return block[:-1]
    return None


def apply(md, pages, subs):
    """pages: mineru.pages(); returns (repaired md, edits, open issues)"""
    cur = {}
    edits, issues = [], []
    for s in subs:
        s["plan"] = plan(s)
    # character edits first, per block, at their recorded raw spans (the block as MinerU wrote it)
    byblk = collections.defaultdict(list)
    for s in subs:
        if s["plan"] == "edit" and s["route"] == "characters":
            byblk[(s["page"], s["blocks"][0])].append(s)
    for key, items in byblk.items():
        block = _in_md(md, MR.unit(pages[key[0]], key[1])[1].get("content") or "")
        if block is None:
            for s in items:
                s["plan"] = "open: block text not found once in full.md"
            continue
        nb, done, bad = char_edits(block, items)
        for s, why in bad:
            s["plan"] = "open: " + why
        for ss, old, new in done:
            for s in ss:
                s["written"] = True
            edits.append({"id": ",".join(s["id"] for s in ss), "page": key[0], "route": "characters",
                          "by": ss[0].get("by"), "old": old, "new": new})
        if done:
            md = md.replace(block, nb, 1)
            cur[key] = nb
    for s in subs:
        if s["plan"].startswith("keep") or s.get("written"):
            continue
        if s["plan"].startswith("open"):
            issues.append({"id": s["id"], "page": s["page"], "why": s["plan"][6:], "primary": s["primary"], "oxr": s["oxr"],
                           "context": s["context"], "crop": s.get("crop"), "crop_placed_by": s.get("crop_placed_by")})
            continue
        if len(s["blocks"]) != 1:
            issues.append({"id": s["id"], "page": s["page"], "why": "spans two blocks", "primary": s["primary"],
                           "oxr": s["oxr"], "context": s["context"]}); continue
        key = (s["page"], s["blocks"][0])
        block = cur.get(key) or _in_md(md, MR.unit(pages[s["page"]], s["blocks"][0])[1].get("content") or "")
        if block is None or md.count(block) != 1:
            issues.append({"id": s["id"], "page": s["page"], "why": "block text not found once in full.md",
                           "primary": s["primary"], "oxr": s["oxr"], "context": s["context"]}); continue
        span = _locate(block, s)
        if not span:
            issues.append({"id": s["id"], "page": s["page"], "why": "passage not found once in its block",
                           "primary": s["primary"], "oxr": s["oxr"], "context": s["context"]}); continue
        old = block[span[0]:span[1]]
        new = _new_span(old, s)
        nb = block[:span[0]] + new + block[span[1]:]
        md = md.replace(block, nb, 1)
        cur[key] = nb
        edits.append({"id": s["id"], "page": s["page"], "route": s["route"], "by": s.get("by"), "old": old, "new": new})
    return md, edits, issues


# ---- character edits by position (0.5.1) -------------------------------------------------------------------------
# two_readings.compare gives each disagreement the raw span of the primary's markdown its printed characters come
# from, so the place is known without searching (10-29: five '0:05' in one mako block could not be told apart by
# context). Where the span touches an inline formula, the formula is written out as linear text with <sup>/<sub>
# (the form check/dropped.py uses for retyped formulas) and the judged characters put in; formulas that are not
# linear (fractions, roots, sums, arrays, stacked scripts) are not rewritten.
NONLINEAR = re.compile(r"\\(?:frac|dfrac|tfrac|over|sqrt|sum|prod|int|begin|array|matrix|binom|stackrel|overset|underset)\b"
                       r"|[_^]\s*(?:\{[^{}]*\}|[^\s{}])\s*[_^]")


REV = {v: k for k, v in sorted(TR.LATEX.items(), key=lambda kv: -len(kv[0])) if len(v) == 1 and not v.isascii()}


ELEMENT = re.compile(r"<(sup|sub|b|i|em|strong|u)>.*?</\1>", re.S)


def _md_escape(t):
    return re.sub(r"([*_$\\`])", r"\\\1", t)


def _seq(s, i, keep=False):
    """render LaTeX math s from i to the closing brace (or the end) as linear text: (text, next i)"""
    out = []
    while i < len(s):
        c = s[i]
        if c == "}":
            return "".join(out), i + 1
        if c == "{":
            t, i = _seq(s, i + 1, keep); out.append(t); continue
        if c in "^_":
            j = i + 1
            while j < len(s) and s[j].isspace():
                j += 1
            if j < len(s) and s[j] == "{":
                t, j = _seq(s, j + 1, keep)
            elif j < len(s) and s[j] == "\\":
                m = re.match(r"\\[A-Za-z]+|\\.", s[j:])
                t, _ = _seq(m.group(0), 0, keep); j += len(m.group(0))
            else:
                t, j = (_md_escape(s[j]) if j < len(s) else ""), j + 1
            tag = "sup" if c == "^" else "sub"
            out.append(f"<{tag}>{t}</{tag}>" if t else ""); i = j; continue
        if c == "\\" and i + 1 < len(s):
            m = re.match(r"\\([A-Za-z]+)", s[i:])
            if m:
                name = m.group(1); i += len(m.group(0))
                if "\\" + name in TR.LATEX:
                    out.append(_md_escape(TR.LATEX["\\" + name]))
                elif name in TR.FUNCS:
                    out.append(name)
                elif name in TR.TEXT_MODE:
                    while i < len(s) and s[i].isspace():
                        i += 1
                    if i < len(s) and s[i] == "{":
                        t, i = _seq(s, i + 1, True); out.append(t)
                continue
            nx = s[i + 1]
            out.append(_md_escape(nx) if nx in "{}%#&_$|" else " " if nx == "\\" else "")
            i += 2; continue
        if c in "~&" or (c.isspace() and not keep):
            i += 1; continue
        out.append(_md_escape(c)); i += 1
    return "".join(out), i


def _render(block, x, y, spans):
    """block[x:y] with every formula part in it written as linear text (dollars dropped); the rest as it is"""
    out, i = [], x
    for a, b in spans:
        if b <= x or a >= y:
            continue
        if i < a:
            out.append(block[i:a])
        lo, hi = max(a, x), min(b, y)
        inner = block[lo:hi]
        inner = re.sub(r"^\$+", "", inner) if lo == a else inner
        inner = re.sub(r"\$+$", "", inner) if hi == b else inner
        k, parts = 0, []
        while k < len(inner):                 # a fragment may close groups it did not open
            t, k = _seq(inner, k); parts.append(t)
        out.append("".join(parts)); i = hi
    if i < y:
        out.append(block[i:y])
    return "".join(out)


def _groups(block, spans):
    """raw ranges of the script groups (^{..}, _x) inside formulas: a change is not split inside one"""
    g = []
    for a, b in spans:
        s = block[a:b]
        for m in re.finditer(r"[_^]\s*(\{)?", s):
            st = a + m.start()
            if m.group(1):
                d, k = 1, m.end()
                while k < len(s) and d:
                    d += {"{": 1, "}": -1}.get(s[k], 0); k += 1
                g.append((st, a + k))
            else:
                g.append((st, a + m.end() + 1))
    return g


def _by_chars(block, s, text, idx, ks, once, spans):
    """the differing characters only, replaced in the markdown at the raw characters that print them (a formula keeps
    its LaTeX and its scripts: 't_{TULMOR}' becomes 't_{TUMOR}', 'M \\times E D' becomes 'M IX E D'): [(r0, r1,
    text)], or None when a difference falls on something that is not one character of the markdown"""
    ptext, o = text[ks[0]:ks[-1] + 1], s["oxr_text"]
    if any(c in TR.ACCENTS for c in block[s["raw_span"][0]:s["raw_span"][1]]):
        return None
    inmath = lambda r: any(a < r < b for a, b in spans)
    # in a formula that is not linear only a character for a character: the printed order of a fraction or a root is
    # not the order of its LaTeX ('\\frac{a}{b}' prints 'ab' in the comparison)
    nonlinear = lambda r: any(a < r < b and NONLINEAR.search(block[a:b]) for a, b in spans)

    def extent(r):
        m = re.match(r"\\[A-Za-z]+\s?|\\.", block[r:]) if block[r] == "\\" else None
        return r + (len(m.group(0)) if m else 1)

    def conv(t, r):
        if not inmath(r):
            return _md_escape(t)
        if any(c.isspace() for c in t):
            return None
        return "".join((REV[c] + " ") if c in REV else ("\\" + c if c in "_^{}%#&$" else c) for c in t)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ptext, o, autojunk=False).get_opcodes():
        if op == "equal" or all(c.isspace() for c in ptext[i1:i2] + o[j1:j2]):
            continue                            # spacing differences: the primary's spacing stays
        x, y = ptext[i1:i2], o[j1:j2]
        if (x.translate(TR.FLAT) == y or x.translate(TR.VARIANT) == y.translate(TR.VARIANT) or
                TR.skeleton(x) == TR.skeleton(y)) and not s.get("by", "").startswith("text layer"):
            continue                            # OXR's ASCII look-alike, characters drawn alike: the image judges are
                                                # no evidence, the primary's stays (the text layer may decide them)
        if nonlinear(idx[ks[0] + max(0, i1 - (i1 == i2))]) and not (op == "replace" and i2 - i1 == j2 - j1):
            return None
        if i1 == i2:                            # an insertion, after the printed character before it
            if i1 == 0:
                return None
            if re.fullmatch(r"[\d,–-]*\d[\d,–-]*", o[j1:j2]) and not ptext[i1 - 1].isspace():
                continue                        # citation numbers OXR glued on: superscripts, written from the
                                                # layer by check/dropped.py (10-29: 'resistance.4')
            r = extent(idx[ks[0] + i1 - 1])
            # punctuation after the last printed character of a formula ends the sentence, not the formula: it goes
            # after the closing $ (10-30: 'mR2 ,' against '$R ^ { 2 }$' was written '$R ^ { 2, }$')
            sp = next(((a, b) for a, b in spans if a < r < b), None)
            if sp and re.fullmatch(r"[.,;:]+", o[j1:j2]) and not any(r <= q < sp[1] for q in idx):
                out.append((sp[1], sp[1], o[j1:j2])); continue
            t = conv(o[j1:j2], r - 1)
            if t is None:
                return None
            out.append((r, r, t)); continue
        if any(ptext[i].isspace() and not block[idx[ks[0] + i]].isspace() for i in range(i1, i2)):
            return None                         # a space the markup prints (an HTML tag): not a character to edit
        R = sorted({idx[ks[0] + i] for i in range(i1, i2) if not ptext[i].isspace()})
        if not R:                               # a space of the markdown where OXR has characters: they take it
            r = idx[ks[0] + i1]
            t = conv(o[j1:j2], r)
            if t is None:
                return None
            out.append((r, r + 1, t)); continue
        if any(once[r] != sum(1 for i in range(i1, i2) if idx[ks[0] + i] == r) for r in R):
            return None                         # a raw character that prints more than these characters
        t = conv(o[j1:j2], R[0])
        if t is None:
            return None
        out.append((R[0], extent(R[0]), t))
        out += [(r, extent(r), "") for r in R[1:]]
    return out


def _chunk(block, a, b):
    """[a, b) widened to whole whitespace-separated words: the unit an edit is recorded in, so that the tokens the
    record declares are the tokens the document changes (accept)"""
    while a > 0 and not block[a - 1].isspace():
        a -= 1
    while b < len(block) and not block[b].isspace():
        b += 1
    return a, b


def char_edits(block, items):
    """items: settled character disagreements of one block with raw_span, oxr_text. Returns (new block,
    [(items, old, new)], [(item, why)]). Where the differing characters fall on single characters of the markdown,
    only they are replaced (_by_chars); otherwise the span takes OXR's text and a formula it touches is written out
    as linear text with <sup>/<sub>."""
    spans = TR.math_spans(block)
    groups = _groups(block, spans)
    text, idx = TR.printed_map(block)
    once = collections.Counter(idx)
    regs, bad = [], []
    for s in items:
        r0, r1 = s["raw_span"]
        ks = [k for k, r in enumerate(idx) if r0 <= r < r1]
        # citation numbers OXR glued to the end of a word are superscripts check/dropped.py writes from the layer
        # (10-29: 'PanopTILs32'); they are not written here as plain digits
        if ks and not re.search(r"\d\W*$", text[ks[0]:ks[-1] + 1]):
            s["oxr_text"] = re.sub(r"(?<=[^\W\d_]|[.,;:)])\d+(?:[,–-]\d+)*$", "", s["oxr_text"])
        ops = _by_chars(block, s, text, idx, ks, once, spans) if ks else None
        if ops:
            regs += [[a, b, [(a, b, s, t)], False] for a, b, t in ops]
            continue
        if ops == []:
            s["plan"] = "keep: only citation numbers differ (check/dropped.py writes them from the layer)"
            continue
        # a change touching part of a script group or of an HTML element (<sup>..</sup>) takes all of it
        for a, b in groups + [m.span() for m in ELEMENT.finditer(block)]:
            if a < r1 and b > r0:
                r0, r1 = min(r0, a), max(r1, b)
        R0, R1 = r0, r1
        for a, b in spans:
            if a < R1 and b > R0:
                R0, R1 = min(R0, a), max(R1, b)
        if any(NONLINEAR.search(block[a:b]) for a, b in spans if a < R1 and b > R0):
            bad.append((s, "inside a formula that is not linear (fraction, root, sum, array or stacked scripts)"))
            continue
        if any(m.start() < R1 and m.end() > R0 and not (m.start(1) <= r0 and r1 <= m.end(1))
               for m in TR.LINK.finditer(block)):
            bad.append((s, "across a link")); continue
        regs.append([R0, R1, [(r0, r1, s, None)], True])
    regs.sort(key=lambda r: (r[0], r[1]))
    merged = []
    for r in regs:
        if merged and r[0] < merged[-1][1]:
            m = merged[-1]
            m[1] = max(m[1], r[1]); m[2] += r[2]; m[3] = m[3] or r[3]
        else:
            merged.append(r)
    chunks = []                                # regions recorded together when their words touch
    for r in merged:
        a, b = _chunk(block, r[0], r[1])
        if chunks and a <= chunks[-1][1]:
            chunks[-1][1] = max(chunks[-1][1], b); chunks[-1][2].append(r)
        else:
            chunks.append([a, b, [r]])
    done = []
    for A, B, rs in reversed(chunks):
        clash = [r for r in rs if any(x[0] < y[1] for x, y in zip(sorted(r[2], key=lambda t: t[0])[1:],
                                                                 sorted(r[2], key=lambda t: t[0])))]
        if clash:
            bad += [(s, "overlaps another disagreement") for r in rs for _, _, s, _ in r[2]]; continue
        pieces, pos = [], A
        for R0, R1, its, render in rs:
            pieces.append(block[pos:R0]); p = R0
            for r0, r1, s, t in sorted(its, key=lambda t: (t[0], t[1])):
                pieces += [_render(block, p, r0, spans) if render else block[p:r0],
                           _md_escape(s["oxr_text"]) if t is None else t]
                p = r1
            pieces.append(_render(block, p, R1, spans) if render else block[p:R1]); pos = R1
        pieces.append(block[pos:B])
        new, old = "".join(pieces), block[A:B]
        block = block[:A] + new + block[B:]
        done.append((list({id(s): s for r in rs for _, _, s, _ in r[2]}.values()), old, new))
    return block, done, bad


def accept(md_before, md_after, edits):
    """independent of apply(): the signed token change of the whole document must equal the sum the edits declare"""
    before, after = collections.Counter(toks(md_before)), collections.Counter(toks(md_after))
    want = collections.Counter()
    for e in edits:
        want.update(collections.Counter(toks(e["new"])))
        want.subtract(collections.Counter(toks(e["old"])))
    got = collections.Counter(after); got.subtract(before)
    diff = {t: got[t] - want[t] for t in set(got) | set(want) if got[t] != want[t]}
    return {"passed": not diff, "edits": len(edits), "tokens_removed": sum((before - after).values()),
            "tokens_added": sum((after - before).values()), "unexplained_change": diff}
