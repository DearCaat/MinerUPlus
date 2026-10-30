"""Text-layer content the primary reading dropped or changed, settled by jev and written back.

Coverage (check/coverage.py) finds, per block, layer characters the primary's text lacks. Here each finding is
localised to the layer words that carry it (a character alignment of the block's layer words against the block's
text), cropped from the page with a thin red box around those words, and jev is asked whether the box prints exactly
the layer's form, in both option orders. 10-29, 101 findings on 9 papers labelled on the page image: jev decided 95,
3 wrong; asked instead to choose between the layer's and the primary's form it got 10 of 91 wrong.

  printed      the layer is right: the primary dropped or changed it (superscript citation numbers, ')' ',' after
               inline math, '**', '≤'). Written into the block where the primary's own characters around it are found.
               Inside an inline formula the primary read from the image, the formula is retyped from the layer
               (sub- and superscripts as <sub>/<sup>) where every difference in it is a printed finding.
  not printed  the layer is wrong there (a font that maps '.' to ':' or '=' to '1⁄4', radical glyphs): nothing to do.
  undecided    an open issue with its crop.
"""
import base64, collections, difflib, hashlib, html, re, unicodedata
from pathlib import Path
import pymupdf
from ..readers import mineru as MR
from .. import layer as LY
from . import coverage as CV, two_readings as TR, jev
from .tables import cell_toks

DASH = str.maketrans({"−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-"})
CMD = re.compile(r"\\([A-Za-z]+|.)")
INSTR = ("The image is a crop of a printed page; a thin red box marks some text. Compare the text inside the red box "
         "with the quoted text character by character: every letter, digit, punctuation mark, symbol and superscript. "
         "Do not correct or normalise either side.")


def _norm_char(c):
    s = unicodedata.normalize("NFKD", c.translate(TR.VARIANT)).translate(DASH)
    return [x for x in s if not x.isspace() and not "" <= x <= "" and not unicodedata.combining(x)]


# accents over a letter print, in a text layer, as a spacing accent before it ('ˆak' for \hat{a}_k); read as nothing,
# the layer's accent looked dropped and was written in front of the formula (10-30: 'the ˆ $\hat { y }$')
ACCENT_CMDS = {"\\hat": "ˆ", "\\widehat": "ˆ", "\\tilde": "˜", "\\widetilde": "˜", "\\bar": "¯", "\\dot": "˙",
               "\\ddot": "¨", "\\check": "ˇ", "\\breve": "˘", "\\acute": "´", "\\grave": "`"}


def plain_map(raw):
    """the characters a block's markdown prints, each with the index of the raw character it comes from. Inside
    $...$: LaTeX commands as their symbols (or nothing), ^ _ { } ~ and spacing commands dropped. Outside: markdown
    escapes (\\* \\$ \\~ \\{) print their character, unescaped * and _ are emphasis, HTML tags are markup."""
    out, i, math = [], 0, False
    while i < len(raw):
        c = raw[i]
        if c == "$":
            math = not math; i += 1; continue
        if c == "<" and not math:
            j = raw.find(">", i)
            if j != -1 and re.match(r"</?[A-Za-z][^<>]*>", raw[i:j + 1]):
                i = j + 1; continue
        if c == "\\" and i + 1 < len(raw):
            nx = raw[i + 1]
            if nx.isalpha():
                m = re.match(r"\\[A-Za-z]+", raw[i:])
                sym = TR.LATEX.get(m.group(0)) or (ACCENT_CMDS.get(m.group(0)) if math else None)
                if sym:
                    out += [(x, i) for x in _norm_char(sym)]
                i += len(m.group(0)); continue
            if math and nx in ",;:! ":
                i += 2; continue
            out += [(x, i + 1) for x in _norm_char(nx)]
            i += 2; continue
        if math and c in "^_{}~":
            i += 1; continue
        if not math and c in "*_":
            i += 1; continue
        if c == "&" and not math:
            m = re.match(r"&(#?\w+);", raw[i:])
            if m:
                out += [(x, i) for x in _norm_char(html.unescape(m.group(0)))]
                i += len(m.group(0)); continue
        out += [(x, i) for x in _norm_char(c)]
        i += 1
    return out


def _in_math(raw, at):
    """whether position at lies inside a $...$ span (unescaped dollars before it are odd)"""
    return len(re.findall(r"(?<!\\)\$", raw[:at])) % 2 == 1


def _lay_chars(words):
    """layer characters of a run of words, each with (word index, character)"""
    out = []
    for k, w in enumerate(words):
        for c in w:
            out += [(x, k) for x in _norm_char(c)]
    return out


def _lay_src(words):
    """for each character of _lay_chars, the printed character it comes from, given once (at its first normalised
    character): inserted text keeps the layer's own characters ('−' stays '−')"""
    out = []
    for w in words:
        for c in w:
            n = len(_norm_char(c))
            out += [c] + [""] * (n - 1) if n else []
    return out


def _superscript(pg, box):
    """characters of the layer inside box that sit raised in a smaller size (citation numbers)"""
    sup = []
    for b in pg.get_text("rawdict", clip=box)["blocks"]:
        for ln in b.get("lines", []):
            sizes = [s["size"] for s in ln["spans"]]
            big = max(sizes) if sizes else 0
            for s in ln["spans"]:
                if s["flags"] & 1 or (big and s["size"] < 0.8 * big and s["bbox"][3] < ln["bbox"][3] - 0.15 * (ln["bbox"][3] - ln["bbox"][1])):
                    sup += [ch["c"] for ch in s["chars"]]
    return "".join(sup)


# formulas whose layer text has no linear order (numerator and denominator, roots, sums, arrays): not retyped
NONLINEAR = re.compile(r"\\(?:frac|dfrac|tfrac|over|sqrt|sum|prod|int|begin|array|matrix|binom|stackrel|overset|underset)\b"
                       r"|[_^]\s*(?:\{[^{}]*\}|[^\s{}])\s*[_^]")    # or a sub- and superscript stacked on one base


def _math_span(raw, at):
    """(start, end) of the $...$ span holding position at, dollars included; None outside a formula"""
    if not _in_math(raw, at):
        return None
    ds = [m.start() for m in re.finditer(r"(?<!\\)\$", raw)]
    s = max(d for d in ds if d < at)
    nxt = [d for d in ds if d >= at]
    return (s, nxt[0] + 1) if nxt else None


def _scripts(pg, box, chars):
    """for each of the layer characters chars (normalised, in order) found in box: '', 'sup' or 'sub' by where the
    glyph sits on its line (raised or lowered and smaller than the line's text); all '' when not found in order"""
    lines = []
    for b in pg.get_text("rawdict", clip=box)["blocks"]:
        for ln in b.get("lines", []):
            big = max((x["size"] for x in ln["spans"]), default=0)
            base = next((x["origin"][1] for x in ln["spans"] if x["size"] == big), ln["bbox"][3])
            lines.append((ln, big, base))
    top = max((big for _, big, _ in lines), default=0)
    seq = []
    for ln, big, base in lines:
        if big < 0.85 * top:        # a raised or lowered glyph the layer keeps as a line of its own: the nearest
            near = [(abs(b2 - base), big2, b2) for _, big2, b2 in lines if big2 >= 0.85 * top]    # full-size line
            if near:
                _, big, base = min(near)
        for x in ln["spans"]:
            small = x["size"] < 0.85 * big
            for ch in x["chars"]:
                y = ch["origin"][1]
                f = "sup" if small and y < base - 0.15 * big else "sub" if small and y > base + 0.08 * big else ""
                seq += [(c, f) for c in _norm_char(ch["c"])]
    flat = "".join(c for c, _ in seq)
    k = flat.find("".join(chars))
    return [seq[k + i][1] for i in range(len(chars))] if k != -1 else [""] * len(chars)


def _retype(pg, raw, pm, L, Lsrc, lw, ops, at):
    """a formula the primary reads from the image on a page whose text layer holds it (10-29: inline formulas held
    misreadings such as 'pm' for 'µm', 'ANN' for 'ANC', 'M×ED' for 'MIXED', 'I56' for '156'): the $...$ span around
    position at, retyped from the layer characters between the primary characters that bound it, with raised and
    lowered glyphs as <sup>/<sub>. None when the span is not linear or its bounds are not matched."""
    sp = _math_span(raw, at)
    if sp is None or NONLINEAR.search(raw[sp[0]:sp[1]]):
        return None
    p2l = {}
    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            p2l.update({j1 + k: i1 + k for k in range(i2 - i1)})
    js = [j for j, (_, r) in enumerate(pm) if sp[0] < r < sp[1]]
    if not js:
        return None
    jlo, jhi = js[0], js[-1]
    # the layer characters strictly between the matched characters just outside the span
    lo = p2l.get(jlo - 1, -1) + 1 if jlo > 0 else 0
    hi = p2l.get(jhi + 1, len(L) + 1) - 1 if jhi + 1 < len(pm) else len(L) - 1
    if (jlo > 0 and jlo - 1 not in p2l) or (jhi + 1 < len(pm) and jhi + 1 not in p2l) or hi < lo:
        return None
    ks = sorted({L[i][1] for i in range(lo, hi + 1)})
    box = lw[ks[0]][1]
    for k in ks:
        box |= lw[k][1]
    flags = _scripts(pg, box + (-1, -2, 1, 2), [L[i][0] for i in range(lo, hi + 1)])
    gap = lambda i: L[i - 1][1] != L[i][1] and not lw[L[i - 1][1]][2]
    out, cur = [], None
    for n, i in enumerate(range(lo, hi + 1)):
        f = flags[n]
        if f != cur:
            if cur:
                out.append(f"</{cur}>")
            if f:
                out.append(f"<{f}>")
            cur = f
        if i > lo and gap(i) and not f:
            out.append(" ")
        out.append(re.sub(r"([*_$])", r"\\\1", Lsrc[i]))
    if cur:
        out.append(f"</{cur}>")
    text = "".join(out).replace(" </", "</")
    # the primary's spacing around the span stays; a space the layer has before or after it is kept
    if lo > 0 and gap(lo) and sp[0] > 0 and not raw[sp[0] - 1].isspace():
        text = " " + text
    # the differences inside: each a finding of its own (op number n) or characters only the primary has
    inside = [[n, op, any(pm[j][0].isalnum() for j in range(j1, j2))] for n, (op, i1, i2, j1, j2) in enumerate(ops)
              if op != "equal" and (max(i1, lo) < min(i2, hi + 1) or max(j1, jlo) < min(j2, jhi + 1))]
    return {"span": list(sp), "old": raw[sp[0]:sp[1]], "text": text, "ops": inside}


def locate(md, raw):
    """the block's text as it stands in full.md: raw itself, or, when an earlier route edited the block, the stretch
    of full.md between the block's first and last 40 characters (each found once); None when not found once"""
    if md.count(raw) == 1:
        return raw
    if md.count(raw) > 1 or len(raw) < 100:
        return None
    head, tail = raw[:40], raw[-40:]
    if md.count(head) == 1 and md.count(tail) == 1:
        s = md.find(head); e = md.find(tail, s)
        if e != -1:
            cur = md[s:e + 40]
            return cur if abs(len(cur) - len(raw)) < 0.1 * len(raw) else None
    # an earlier route edited the block's first or last characters (10-30: 'ρ' corrected near the end of an abstract,
    # and the block's dropped brackets went unwritten): a block of one line is the line of full.md that holds the
    # stretches of it found once, starting or ending as the block does
    if "\n" in raw:
        return None
    lines = set()
    for i in range(0, len(raw) - 40, 20):
        w = raw[i:i + 40]
        if md.count(w) == 1:
            k = md.find(w)
            e = md.find("\n", k)
            lines.add((md.rfind("\n", 0, k) + 1, len(md) if e == -1 else e))
    if len(lines) != 1:
        return None
    s, e = lines.pop()
    cur = md[s:e]
    ok = (cur.startswith(raw[:10]) or cur.endswith(raw[-10:])) and abs(len(cur) - len(raw)) < 0.1 * len(raw)
    return cur if ok and md.count(cur) == 1 else None


def find(pdf_path, mdir, work, md=None):
    """localised findings: [{id, page, uid, layer (words), lay, prim, ops, bbox, crop}]. With md, each block is
    compared as it now stands in full.md (earlier routes' edits included); blocks not found there once are skipped."""
    pdf = pymupdf.open(pdf_path)
    A = MR.pages(mdir)
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    found = []
    for pg_no in sorted(A):
        pg = LY.page(pdf, pg_no - 1)
        words = LY.words(pg)
        if not words:
            continue
        last = {}
        for k, w in enumerate(words):
            last[(w[5], w[6])] = k
        units = [(uid, t, p) for uid, t, p in MR.units(A[pg_no]) if p.get("bbox")]
        figs = [p["bbox"] for _, t, p in units if t in CV.FIGURE]
        prose = [(uid, t, p) for uid, t, p in units if t in TR.PRIMARY_PROSE]
        got = collections.defaultdict(list)
        for k, w in enumerate(words):
            t = w[4]
            trimmed = k == last[(w[5], w[6])] and t[-1:] in CV.HY and len(t) > 1
            if trimmed:
                t = t[:-1]                                   # a line-break hyphen
            t = CV.INVISIBLE.sub("", t)
            if not t:
                continue
            r = pymupdf.Rect(w[:4]) * pg.rotation_matrix
            nb = CV._norm_box(r, pg); c = ((nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2)
            if any(CV._inside(c, f) for f in figs):
                continue
            hits = [u for u in prose if CV._inside(c, u[2]["bbox"])]
            if hits:
                u = min(hits, key=lambda u: (u[2]["bbox"][2] - u[2]["bbox"][0]) * (u[2]["bbox"][3] - u[2]["bbox"][1]))
                got[u[0]].append((t, pymupdf.Rect(w[:4]), trimmed))
        for uid, lw in got.items():
            typ, part = MR.unit(A[pg_no], uid)
            raw = part.get("content") or ""
            located = True
            if md is not None:
                cur = locate(md, raw)
                located = cur is not None
                raw = cur if located else raw
            pm = plain_map(raw)
            P = [c for c, _ in pm]
            L = _lay_chars([t for t, _, _ in lw])
            Lsrc = _lay_src([t for t, _, _ in lw])
            sm = difflib.SequenceMatcher(None, [c for c, _ in L], P, autojunk=False)
            ops = sm.get_opcodes()
            for n, (op, i1, i2, j1, j2) in enumerate(ops):
                if op not in ("delete", "replace"):
                    continue
                lost = "".join(c for c, _ in L[i1:i2])
                if CV.LEADER.fullmatch(lost):
                    continue
                ks = sorted({L[i][1] for i in range(i1, i2)})
                box = lw[ks[0]][1]
                for k in ks:
                    box |= lw[k][1]
                lay_words = " ".join(lw[k][0] for k in ks)
                # the primary's form of those words: the layer words with this op applied
                a = next(i for i, (_, k) in enumerate(L) if k == ks[0])
                b = max(i for i, (_, k) in enumerate(L) if k == ks[-1]) + 1
                prim_form = "".join(c for c, _ in L[a:i1]) + "".join(P[j1:j2]) + "".join(c for c, _ in L[i2:b])
                # anchor in the raw text: the raw index right after the last primary character before the change
                # and the raw span of the primary characters it replaces
                before = pm[j1 - 1][1] if j1 > 0 else None
                span = (pm[j1][1], pm[j2 - 1][1] + 1) if j2 > j1 else None
                after_next = pm[j2][1] if j2 < len(pm) else None
                # unique context: 6 matched characters on each side must exist (the change is placed inside one
                # alignment, not at a block edge)
                ctx_ok = (i1 >= 6 or j1 >= 6) and i1 > 0 and j1 > 0
                # and on the line of the matched character before or after them (10-30: a summation limit 's' of the
                # displayed equation below was in the layer after the paragraph's last word, and was written there)
                same = lambda k: min(box.y1, lw[k][1].y1) - max(box.y0, lw[k][1].y0) > 0.5 * min(box.height, lw[k][1].height)
                if ctx_ok and op == "delete" and not (same(L[i1 - 1][1]) or (i2 < len(L) and same(L[i2][1]))):
                    ctx_ok = False
                # dropped at the block start (an italic journal name, a footnote mark): placed before the block's
                # first characters when at least 6 of them follow matched
                nx = ops[n + 1] if n + 1 < len(ops) else None
                # and sit on the line of those characters (10-29: a fraction's denominator 'SE' fell in the box of
                # the line below and was written before it)
                if op == "delete" and j1 == 0 and nx and nx[0] == "equal" and nx[2] - nx[1] >= 6:
                    nr = lw[L[i2][1]][1]
                    ctx_ok = min(box.y1, nr.y1) - max(box.y0, nr.y0) > 0.5 * min(box.height, nr.height)
                # the lost characters as printed: spaces between layer words (not across a line-break hyphen) and
                # whether a space separates them from the text before and after
                gap = lambda i: L[i - 1][1] != L[i][1] and not lw[L[i - 1][1]][2]
                ins_text = "".join((" " if i > i1 and gap(i) else "") + Lsrc[i] for i in range(i1, i2))
                fid = f"r{pg_no}.{uid}.{n}"
                crop = work / "crops" / f"{fid}.png"
                ctxbox = pymupdf.Rect(box)
                for k in range(max(0, ks[0] - 3), min(len(lw), ks[-1] + 4)):
                    if abs(lw[k][1].y0 - box.y0) < 2 * box.height:
                        ctxbox |= lw[k][1]
                clip = pymupdf.Rect(ctxbox.x0 - 10, ctxbox.y0 - 8, ctxbox.x1 + 10, ctxbox.y1 + 8) & pg.rect
                d2 = pymupdf.open(); p2 = d2.new_page(width=clip.width, height=clip.height)
                p2.show_pdf_page(p2.rect, pdf, pg.number, clip=clip)
                p2.draw_rect(pymupdf.Rect(box.x0 - clip.x0 - 1.5, box.y0 - clip.y0 - 1.5, box.x1 - clip.x0 + 1.5,
                                          box.y1 - clip.y0 + 1.5), color=(1, 0, 0), width=0.8)
                p2.get_pixmap(dpi=220).save(str(crop))
                at_ = span[0] if span else (before + 1 if before is not None else (after_next or 0))
                retype = _retype(pg, raw, pm, L, Lsrc, lw, ops, at_) if _in_math(raw, at_) else None
                found.append({"id": fid, "page": pg_no, "uid": uid, "block_type": typ, "layer_words": lay_words,
                              "lay": "".join(c for c, _ in L[a:b]), "prim": prim_form, "lost": lost,
                              "insert": "".join(c for c, _ in L[i1:i2]), "insert_text": ins_text, "insert_src": "".join(Lsrc[i1:i2]),
                              "space_before": i1 > 0 and gap(i1), "space_after": i2 < len(L) and gap(i2),
                              "located": located, "replaces": "".join(P[j1:j2]),
                              "raw_after": before, "raw_next": after_next, "raw_span": span, "placeable": ctx_ok,
                              "superscript": _superscript(pg, box), "bbox": list(box), "crop": str(crop),
                              "retype": retype})
    return found


def judge(found, work):
    qs = []
    for f in found:
        img = "data:image/png;base64," + base64.b64encode(open(f["crop"], "rb").read()).decode()
        # the id carries the question's words: jev-call resumes by id from the out file
        qs.append({"id": f["id"] + "~" + hashlib.md5(f["layer_words"].encode()).hexdigest()[:8], "state": f"Quoted text: «{f['layer_words']}»", "instructions": INSTR, "images": [img],
                   "options": {"printed": f"The red box shows exactly «{f['layer_words']}»",
                               "not printed": f"The red box shows something different from «{f['layer_words']}»"}})
    v = jev.ask(qs, work, "dropped")
    for f, q in zip(found, qs):
        f["verdict"] = v.get(q["id"], "not judged")
    return found


OPENING = "([{“‘"


def edit(raw, f):
    """the block's markdown with the layer's characters written in: (new raw, old window, new window) or None when
    the place is not certain. A change inside a formula the primary read from the image retypes the formula from the
    layer (_retype) where the formula is linear."""
    r = _edit_plain(raw, f)
    rt = f.get("retype")
    # not where the retyped text would hold an accent: the layer has it as a glyph before its letter, and the text
    # would print 'ˆA' where the formula prints Â (10-30, abx: 'Corr( ˆA<sup>(j)</sup>, ...'); a formula whose accent
    # is the misreading is still retyped (conic: '\hat { M } o N u S A C' for 'MoNuSAC')
    if r is None and rt and f.get("retype_ok") and not any(a in rt["text"] for a in ACCENT_CMDS.values()):
        s, e = rt["span"]
        if raw[s:e] == rt["old"]:
            r = raw[:s] + rt["text"] + raw[e:], rt["old"], rt["text"]
            f["retyped"] = True
    return r


def _edit_plain(raw, f):
    ins = f["insert"]
    if "$" in ins:
        return None
    if f["raw_span"] is None:                      # dropped: insert next to the primary characters around it
        if f["raw_after"] is None and f.get("raw_next") is None:
            return None
        if f["raw_after"] is None:
            at = f["raw_next"]                     # at the block start, before its first characters
        elif ins and all(c in OPENING for c in ins) and f.get("raw_next") is not None:
            at = f["raw_next"]                     # an opening bracket belongs to what follows
            k = raw.rfind("$", 0, at)
            if k != -1 and re.fullmatch(r"(?:\s|[{}^_]|\\[A-Za-z]+)*", raw[k + 1:at]) and not _in_math(raw, k):
                at = k                             # before the formula it opens
        else:
            at = f["raw_after"] + 1
            while at < len(raw) and raw[at] in "}$" and _in_math(raw, at):
                at += 1                            # out of the formula the anchor ends
        if _in_math(raw, at):
            return None
        text = f.get("insert_text", ins)
        sup = f.get("superscript") or ""
        core = text.strip(".,; ")
        if sup and core and all(c in sup for c in core):
            text = text.replace(" ", "").replace(core.replace(" ", ""), f"<sup>{core.replace(' ', '')}</sup>", 1)  # citation numbers: no spaces
        else:
            if f.get("space_before") and at > 0 and not raw[at - 1].isspace():
                text = " " + text
            if f.get("space_after") and at < len(raw) and not raw[at].isspace():
                text += " "
        text = re.sub(r"([*_])", r"\\\1", text)          # '*' '_' are printed marks here, not emphasis
        return raw[:at] + text + raw[at:], raw[max(0, at - 12):at + 12], raw[max(0, at - 12):at] + text + raw[at:at + 12]
    s, e = f["raw_span"]
    old = raw[s:e]
    if len(ins) != len(f["replaces"]) or "$" in old or "<" in old or "\\" in old or _in_math(raw, s):
        return None                                # not character for character, or inside a formula: by hand
    ins = f.get("insert_src", ins)
    return raw[:s] + ins + raw[e:], raw[max(0, s - 12):e + 12], raw[max(0, s - 12):s] + ins + raw[e:e + 12]


def _doubled(layer, prim):
    """the layer writes every letter twice in a row (overprinted text; digits and punctuation once), and with each
    pair read once it is the primary's form"""
    a = [c for x in layer for c in _norm_char(x)]
    b = [c for x in prim for c in _norm_char(x)]
    out, i, pairs = [], 0, 0
    while i < len(a):
        if a[i].isalpha():
            if i + 1 >= len(a) or a[i + 1] != a[i]:
                return False
            out.append(a[i]); i += 2; pairs += 1
        else:
            out.append(a[i]); i += 1
    return pairs >= 2 and out == b


def apply(md, pages, found, second=None):
    """write the printed findings into full.md, right to left within a block, on the block as it now stands in
    full.md (the text find() compared); returns (md, edits, issues, counts).
    A change of the primary's characters (not a drop) is written only when the second reading also has the layer's
    form on that page (second: OXR pages): jev took a broken layer for the print there (10-29, mako '1⁄41:61')."""
    edits, issues, n = [], [], collections.Counter()
    seen = {}

    def second_has(pg, lay):
        if second is None:
            return False
        if pg not in seen:
            seen[pg] = "".join(c for c, _ in plain_map(" ".join(b.get("content") or "" for b in second.get(pg, []))))
        return lay in seen[pg]
    by_block = collections.defaultdict(list)
    for f in found:
        n[f["verdict"]] += 1
        if f["verdict"] == "not printed":
            continue                                   # the layer is wrong there
        if f["verdict"] == "printed" and _doubled(f["layer_words"], f["prim"]):
            n["layer prints each glyph twice"] += 1   # overprinted text (10-30, conic: '𝑚𝑚𝑅𝑅2,' for 'mR2,'); jev
            continue                                    # reads the print, which is the primary's
        if f["verdict"] != "printed":
            issues.append({"kind": "text layer not in the parse", "why": f"jev {f['verdict']}", "page": f["page"],
                           "layer": f["layer_words"], "parse": f["prim"], "crop": f["crop"]}); continue
        by_block[(f["page"], f["uid"])].append(f)
    verdict = {f["id"]: f["verdict"] for f in found}
    for (pg, uid), fs in by_block.items():
        # a formula is retyped only where the layer is right at every difference inside it: each finding there
        # printed (jev), and no letter or digit only the primary has
        for f in fs:
            rt = f.get("retype")
            f["retype_ok"] = bool(rt) and all(
                (verdict.get(f"r{pg}.{uid}.{n}") == "printed") if op != "insert" else not alnum for n, op, alnum in rt["ops"])
        raw = locate(md, MR.unit(pages[pg], uid)[1].get("content") or "")
        bad = raw is None or not all(f.get("located", True) for f in fs)
        raw = raw or ""
        new = raw
        done, spans = [], set()
        for f in sorted(fs, key=lambda f: -(f["raw_span"][0] if f["raw_span"] else f["raw_after"] or 0)):
            # a finding anchored inside a formula retyped already: the retyped text holds the layer's characters there
            # (10-30: an opening bracket, anchored at the first character inside the formula, was inserted into the
            # retyped text, '(p = 0.01 (0)')
            anchor = f["raw_span"] or [x for x in (f["raw_after"], f.get("raw_next")) if x is not None]
            if (f.get("retype") and tuple(f["retype"]["span"]) in spans) or \
                    any(s0 <= a < e0 for s0, e0 in spans for a in anchor if a is not None):
                n["in a formula already retyped"] += 1
                continue
            changed = f["raw_span"] is not None
            r = None if bad or not f["placeable"] or (changed and not second_has(pg, f["lay"])) else edit(new, f)
            if r is None:
                n["printed, not placed"] += 1
                issues.append({"kind": "text layer not in the parse", "why": "printed (jev); not placed, edit by hand",
                               "page": pg, "layer": f["layer_words"], "parse": f["prim"], "crop": f["crop"]}); continue
            new = r[0]
            if f.get("retyped"):
                spans.add(tuple(f["retype"]["span"]))
                n["formulas retyped from the layer"] += 1
            done.append({"id": f["id"], "page": pg, "route": "dropped" + (" (formula retyped)" if f.get("retyped") else ""),
                         "by": "jev", "old": r[1], "new": r[2]})
        if done:
            md = md.replace(raw, new, 1)
            edits += done
            n["written"] += len(done)
    return md, edits, issues, dict(n)
