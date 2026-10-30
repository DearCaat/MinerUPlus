"""Character check by two readings: the primary reading (MinerU advanced; on born-digital pages it copies the text
layer) against an independent visual reading (OXR; reads the page image, planted tests 10-28).

Per page, prose tokens of both readings are aligned in order (difflib on token sequences). A substitution is a run
of tokens where both readings have something at the same place and differ: one of them misread the page, or the
text layer is wrong. Insertions/deletions are counted separately: OXR is known to omit content, so a token missing
from OXR is not evidence against the primary reading. Page headers, footers, page numbers and display equations are
not compared (OXR's default output has no headers or footers; equations are LaTeX on one side only).
"""
import difflib, hashlib, html, re, unicodedata
from ..readers import mineru as MR, oxr as OX

TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")
TOK = re.compile(r"[^\W_]+(?:[.,·:][0-9]+)*|[^\w\s]")
PRIMARY_PROSE = {"text", "paragraph_title", "list", "page_footnote", "doc_title", "ref_text", "aside_text",
                 "image_caption", "table_caption", "chart_caption", "image_footnote", "table_footnote",
                 "chart_footnote", "code_caption", "code_footnote"}
OXR_PROSE = {"Text", "Title", "Caption", "Footnote"}
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")          # markdown link: the text is content, the url is markup
MARKUP = re.compile(r"[*$^{}_\\]")                    # markdown emphasis and LaTeX wrappers; LaTeX commands stay


LATEX = {r"\pm": "±", r"\times": "×", r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\%": "%",
         r"\cdot": "·", r"\sim": "~", r"\approx": "≈", r"\mu": "μ", r"\alpha": "α", r"\beta": "β", r"\chi": "χ",
         r"\kappa": "κ", r"\dagger": "†", r"\ddagger": "‡", r"\to": "→", r"\rightarrow": "→", r"\infty": "∞",
         r"\lt": "<", r"\gt": ">", r"\ast": "*", r"\circ": "°", r"\sigma": "σ", r"\lambda": "λ", r"\delta": "δ",
         r"\gamma": "γ", r"\rho": "ρ", r"\tau": "τ", r"\theta": "θ", r"\Delta": "Δ", r"\prime": "′"}
import unicodedata as _ud
for _n in ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon "
           "phi chi psi omega").split():
    for _cap in (False, True):
        _name = _n.capitalize() if _cap else _n
        try:
            _ch = _ud.lookup(("GREEK CAPITAL LETTER " if _cap else "GREEK SMALL LETTER ") + _n.upper())
        except KeyError:
            continue
        LATEX.setdefault("\\" + _name, _ch)
        LATEX.setdefault("\\var" + _name, _ch)     # \varphi, \varPhi: a style of the same letter
# LaTeX commands that only style or delimit; their names are not printed
CMD = re.compile(r"\\(?:mathrm|mathsf|mathbf|mathit|mathcal|mathbb|text|textrm|textbf|textit|textsf|operatorname|"
                 r"boldsymbol|left|right|big|Big|bigl|bigr|lfloor|rfloor|lceil|rceil|langle|rangle|displaystyle|"
                 r"textstyle|scriptstyle|mathop|quad|qquad|hspace|vspace|mathtt|texttt|mathfrak|mathscr|textsc|"
                 r"textup|textnormal|mathnormal|emph|underline)\b|\\[,;:!> ]")   # last: LaTeX spacing commands
# one printed sign, several code points (the reader's choice, not the page's): typographic variants only.
# Middle dot vs period and minus vs hyphen are NOT here: those are different printed signs.
VARIANT = str.maketrans({"’": "'", "‘": "'", "′": "'", "“": '"', "”": '"', "∼": "~", "∗": "*", "●": "•", "∙": "•", "⁄": "/",
                         "\u00a0": " ", "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff"})


def latex_plain(x):
    """LaTeX symbols as the characters they print, styling commands dropped: applied to both readings before
    tokenising, so a command name ('mathbf', 'times') never becomes a word of the comparison"""
    for k in sorted(LATEX, key=len, reverse=True):
        x = x.replace(k, " " + LATEX[k] + " ")
    return CMD.sub(" ", x)


# OXR writes these special characters as their ASCII look-alikes (10-28: middle dots became periods in 19 of 26
# planted cases, en dashes became hyphens throughout). Where the primary reading has the special character and OXR
# only its look-alike, OXR is no evidence against the primary reading.
FLAT = str.maketrans({"–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-", "·": "."})
# characters drawn alike: Unicode's confusables table (UTS #39), not a list of our own. The page image is no
# evidence between them (10-28: Gemini turned 9 layer minus signs into en dashes; 'AI' read 'Al'), the born-digital
# layer is. 10-29: rules that do not generalise go; the hand lists (I/l, O/0, dashes) kept 10 'Al' the layer
# prints 'AI' in one supplement.
CONFUSABLE = {}
for _l in open(__file__.rsplit("/", 1)[0] + "/confusables.txt", encoding="utf-8"):
    if _l[:1] != "#" and "\t" in _l:
        _a, _b = _l.split("\t")
        CONFUSABLE[chr(int(_a, 16))] = "".join(chr(int(h, 16)) for h in _b.split())


def skeleton(s):
    """UTS #39 skeleton: two strings with the same skeleton are drawn alike"""
    s = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFD", "".join(CONFUSABLE.get(c, c) for c in s))
RUN = re.compile(r"(.)\1+")


def _script(c):
    """the Unicode script of a letter, from its name: LATIN, GREEK, CYRILLIC, ..."""
    try:
        return unicodedata.name(c).split()[0]
    except ValueError:
        return None


def cross_script(a, b):
    """the two readings differ only by letters of one script read as letters of another ('ρ' for 'p', 'μ' for 'p',
    Cyrillic 'к' for 'κ'): the image is no evidence there (10-29: Gemini read a printed 'ρ' as 'p'), the born-digital
    text layer is. No table of look-alikes: any letter-for-letter change across scripts counts."""
    a, b = re.sub(r"\s", "", a), re.sub(r"\s", "", b)
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    return bool(ops) and all(op == "replace" and i2 - i1 == j2 - j1 and
                             all(x.isalpha() and y.isalpha() and _script(x) != _script(y)
                                 for x, y in zip(a[i1:i2], b[j1:j2])) for op, i1, i2, j1, j2 in ops)


def canon(x):
    """the printed characters of a reading: LaTeX symbols as characters, styling commands, markup and spaces dropped"""
    x = LINK.sub(r"\1", x).replace(" ", "").replace("‘‘", "“").replace("’’", "”").replace("''", '"')
    for k in sorted(LATEX, key=len, reverse=True):
        x = x.replace(k, LATEX[k])
    x = CMD.sub("", x)
    return MARKUP.sub("", x).translate(VARIANT).replace(" ", "")


def kind(a, b):
    """spacing: same characters, different spacing; markup: same printed characters after LaTeX/markdown markup and
    typographic code-point variants are normalised (canon); oxr flattening: OXR has the ASCII look-alike of the
    primary's dash or middle dot; reading order: the aligner paired runs of very different length; else content."""
    if a.replace(" ", "") == b.replace(" ", ""):
        return "spacing"
    ca, cb = canon(a), canon(b)
    if ca == cb:
        return "markup"
    if skeleton(ca) == skeleton(cb):
        return "look-alike"             # characters drawn alike: the text layer decides (check/resolve.py)
    if ca.translate(FLAT) == cb:        # OXR has only the look-alike of the primary's special character
        return "oxr flattening"
    if RUN.sub(r"\1", ca) == RUN.sub(r"\1", cb):
        return "repeat count"           # '3200003' / '320003': only the length of a run of one character differs
    na, nb = len(a.split()), len(b.split())
    if max(na, nb) >= 8 and max(na, nb) >= 3 * max(1, min(na, nb)):
        return "reading order"          # the aligner paired unrelated runs (captions, panels read in another order)
    return "content"


def toks(s):
    s = unicodedata.normalize("NFKC", html.unescape(TAG.sub(" ", s)))
    return TOK.findall(s)


TEXT_MODE = {"text", "textrm", "textbf", "textit", "textsf", "mbox", "textnormal", "textup"}
# the log-like operators LaTeX and amsmath define, which print their name (the complete set of LaTeX's \\log family)
FUNCS = set("arccos arcsin arctan arg cos cosh cot coth csc deg det dim exp gcd hom inf ker lg lim liminf limsup ln "
            "log max min Pr sec sin sinh sup tan tanh injlim projlim varliminf varlimsup varinjlim varprojlim "
            "bmod pmod mod".split())
STYLE = set(CMD.pattern.split(r"\\(?:")[1].split(r")\b")[0].split("|"))   # styling commands: their argument prints
LEADER = re.compile(r"(?:\.[ \t]*){4,}|…{2,}")        # dot leaders of a table of contents: not content
DOLLAR = re.compile(r"(?<!\\)\$+")
LIST_MARK = re.compile(r"(?m)^[ \t]*((?:[-*+]|#{1,6})[ \t]+)")
# spacing accents (Unicode modifier symbols, category Sk) a LaTeX layer writes beside the letter they sit on
ACCENTS = {chr(c) for c in range(0x80, 0x3000) if unicodedata.category(chr(c)) == "Sk"} | {"`"}
# dollars jev judged printed dollar signs, not the start of a formula (settle_dollars); keyed by their context
LITERAL_DOLLARS = set()
# a word of three letters or more outside LaTeX commands: a pair of dollars around one may not be a formula (only a
# filter of what jev is asked: a formula with such a word is asked too)
WORD = re.compile(r"(?<![\\{A-Za-z])[A-Za-z]{3,}(?![A-Za-z])")


def math_spans(raw):
    """(start, end) of each $...$ (or $$...$$) span of a markdown text, dollars included. A pair jev judged to be two
    currency signs (LITERAL_DOLLARS; 10-29: OXR's '~US$1,000 where chemotherapy costs ~US$') is not a formula."""
    ds = _dollars(raw)
    return [(ds[k].start(), ds[k + 1].end()) for k in range(0, len(ds) - 1, 2)]


def _dkey(raw, m):
    return raw[max(0, m.start() - 30):m.start()] + "\0" + raw[m.end():m.end() + 30]


def _dollars(raw):
    """the unescaped dollars of a text that delimit formulas: all but those settle_dollars found literal"""
    return [m for m in DOLLAR.finditer(raw) if _dkey(raw, m) not in LITERAL_DOLLARS]


def printed_map(raw):
    """the text a markdown block prints, and for each of its characters the raw index it comes from.
    Links print their text. Outside $...$: emphasis (* _) dropped, escapes print their character, HTML tags are a
    space, entities their character, a stray LaTeX command as in a formula. Inside $...$: LaTeX symbols as their
    characters, function names (log, exp) as their name; styling and other commands, \\begin{..}/\\end{..} with their
    argument, ^ _ { } ~ & and spaces dropped (math mode does not print spaces: MinerU writes '\\mathrm { A U C }' for
    'AUC', and split into letters it was compared as six tokens, 10-29), except inside \\text{...}."""
    skip = bytearray(len(raw))
    for m in LINK.finditer(raw):                        # '[' and '](url)' are not printed
        skip[m.start()] = 1
        for k in range(m.end(1), m.end()):
            skip[k] = 1
    for m in LIST_MARK.finditer(raw):                   # list and heading markers are markdown, not print
        for k in range(m.start(1), m.end()):
            skip[k] = 1
    for m in re.finditer(r"\\(?:begin|end)\s*\{[^{}]*\}(?:\s*\{[lcr|\s]*\})?", raw):   # environments, column specs
        for k in range(m.start(), m.end()):
            skip[k] = 1
    inm = bytearray(len(raw))
    for a, b in math_spans(raw):
        for k in range(a, b):
            inm[k] = 1
    out, idx = [], []

    def emit(s, i):
        if s in ACCENTS:            # a LaTeX layer's spacing accent ('J´egou'): the page prints the accented letter
            return
        for c in unicodedata.normalize("NFKC", s):
            out.append(c); idx.append(i)
    i, depth, text_at, groups = 0, 0, [], 0      # groups: open braces of a stray command's argument outside math
    while i < len(raw):
        c = raw[i]
        if skip[i]:
            i += 1; continue
        m = re.match(r"\\([A-Za-z]+)", raw[i:i + 40]) if c == "\\" else None
        name = m.group(1) if m else None
        if inm[i] or (name and ("\\" + name in LATEX or name in STYLE or name in FUNCS)):
            if not inm[i]:
                depth, text_at = 0, []
            if c == "$":
                i += 1; continue
            if name:
                if "\\" + name in LATEX:
                    emit(LATEX["\\" + name], i)
                elif name in FUNCS:
                    emit(name, i)
                elif name in TEXT_MODE and raw[i + len(m.group(0)):].lstrip().startswith("{"):
                    text_at.append(depth + 1)
                if not inm[i] and raw[i + len(m.group(0)):].lstrip().startswith("{"):
                    groups += 1
                    i = raw.index("{", i) + 1; continue
                i += len(m.group(0)); continue
            if c == "\\" and i + 1 < len(raw):
                nx = raw[i + 1]
                if nx in "{}%#&_$|":
                    emit(nx, i)          # mapped to the backslash: an edit replaces both
                i += 2; continue
            if c == "{":
                depth += 1; i += 1; continue
            if c == "}":
                if text_at and text_at[-1] == depth:
                    text_at.pop()
                depth -= 1; i += 1; continue
            if c in "^_~&" or (c.isspace() and not (text_at and depth >= text_at[-1])):
                i += 1; continue
            emit(c, i); i += 1; continue
        depth, text_at = 0, []
        if groups and c == "}":
            groups -= 1; i += 1; continue
        if c == "\\" and i + 1 < len(raw) and not raw[i + 1].isalnum():
            emit(raw[i + 1], i); i += 2; continue
        if c in "*_":
            i += 1; continue
        if c == "<":
            m = TAG.match(raw, i)
            if m:
                emit(" ", i); i = m.end(); continue
        if c == "&":
            m = re.match(r"&(#?\w+);", raw[i:])
            if m:
                emit(html.unescape(m.group(0)), i); i += len(m.group(0)); continue
        emit(c, i); i += 1
    text = "".join(out)
    for m in LEADER.finditer(text):
        text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
    return text, idx


NUM_GAP = re.compile(r"(?<=\d)\s+(?=\d)|(?<=\d)\s*([.,])\s*(?=\d)")
STYLED = re.compile(r"(\\(?:mathrm|mathit|mathbf|mathsf|mathtt|mathcal|mathbb|operatorname|it|rm|bf|tt|sf))\s*\{([^{}]*)\}")
TEXT_ARG = re.compile(r"\\(?:text|textrm|textit|textbf|mbox)\s*\{[^{}]*\}")


def tidy_math(md):
    """formulas spelled as they print where LaTeX ignores the spacing: MinerU writes numbers and styled words
    letter by letter ('$( n = 2 1 0 )$', '\\mathrm { A U C }'; 10-29, a consumer: a search for 'n = 210' finds nothing,
    23 such formulas in one paper). Inside math, spaces between the digits of a number and inside styled
    arguments are dropped, runs of spaces become one; \\text{...} keeps its spaces. The rendering is unchanged.
    Returns (md, formulas changed)."""
    out, pos, n = [], 0, 0
    for a, b in math_spans(md):
        f = md[a:b]
        keep = {}
        g = TEXT_ARG.sub(lambda m: keep.setdefault(f"\0{len(keep)}\0", m.group(0)) and f"\0{len(keep) - 1}\0", f)
        g = NUM_GAP.sub(lambda m: m.group(1) or "", g)
        g = STYLED.sub(lambda m: m.group(1) + "{" + re.sub(r"\s+", "", m.group(2)) + "}", g)
        g = re.sub(r"[ \t]{2,}", " ", g)
        for k, v in keep.items():
            g = g.replace(k, v)
        n += g != f
        out.append(md[pos:a] + g); pos = b
    return "".join(out) + md[pos:], n


def dollar_pairs(raw):
    """the pairs math_spans makes around a word (WORD): the ones that may not be a formula; jev decides (settle_dollars). [(context, key of the first)]"""
    ds, out = _dollars(raw), []
    for k in range(0, len(ds) - 1, 2):
        a, b = ds[k], ds[k + 1]
        inner = raw[a.end():b.start()]
        if WORD.search(re.sub(r"\\[A-Za-z]+\s*(\{[^{}]*\})?", " ", inner)):
            out.append((raw[max(0, a.start() - 80):a.start()] + "⟦" + a.group(0) + "⟧" + inner + "⟦" + b.group(0) + "⟧" +
                        raw[b.end():b.end() + 80], _dkey(raw, a)))
    return out


def settle_dollars(primary_dir, oxr_dir, work):
    """jev on each pair of dollars the formula parser makes around running words, in either reading: one formula,
    or the first is a printed dollar sign (10-29: rules that do not generalise go to jev). A literal dollar
    shifts the pairs after it, so the pairs are made again and the new ones asked, until none is new.
    Fills LITERAL_DOLLARS; returns {context: verdict}."""
    from . import jev
    texts = [b.get("content") or "" for pg in MR.pages(primary_dir).values() for _, _, b in MR.units(pg)]
    texts += [x.get("content") or "" for pg in OX.pages(oxr_dir).values() for x in pg]
    LITERAL_DOLLARS.clear()
    out = {}
    for rnd in range(12):
        qs = {}
        for t in texts:
            for ctx, key in dollar_pairs(t):
                if ctx not in out and ctx not in qs:
                    qs[ctx] = {"id": "$$" + hashlib.md5(ctx.encode()).hexdigest()[:12],
                               "state": f"A passage of a scientific paper in markdown: «{ctx}»",
                               "instructions": "Two dollar signs in the passage are marked ⟦$⟧. Decide whether the "
                                               "marked pair opens and closes one LaTeX formula, or the first marked dollar "
                                               "sign is a dollar sign printed in the text (a currency sign) and opens no "
                                               "formula.",
                               "options": {"formula": "The two marked dollar signs open and close one LaTeX formula",
                                           "currency": "The first marked dollar sign is printed as a dollar sign "
                                                       "(currency); it does not open a formula"}}
        if qs:
            v = jev.ask(list(qs.values()), work, "dollars")
            out.update({ctx: v.get(q["id"]) for ctx, q in qs.items()})
        # in each text only the first pair judged literal counts: the pairs after it are made anew
        new = False
        for t in texts:
            for ctx, key in dollar_pairs(t):
                if out.get(ctx) == "currency":
                    LITERAL_DOLLARS.add(key); new = True
                    break
        if not new:
            break
    return out


def printed_toks(raw):
    """tokens of the printed text: [(token, start, end)] with start/end in the printed text"""
    text, _ = printed_map(raw)
    return text, [(m.group(0), m.start(), m.end()) for m in TOK.finditer(text)]


def _elsewhere(at, i1, i2, ob):
    """OXR's side of a substitution holds a run of words the primary has outside it on the page: the readers put a
    passage in another order (10-29, held-out paper: OXR read two affiliation lines as one and the aligner paired it
    with the primary's second; written back, the first line came twice). A run: three words with letters in a row
    (with the punctuation between them); two are too common ('image - to' is a compound the page also has)."""
    extra = []
    for op, x1, x2, y1, y2 in difflib.SequenceMatcher(None, at[i1:i2], ob, autojunk=False).get_opcodes():
        if op in ("insert", "replace"):
            extra.append(ob[y1:y2])
    for run in extra:
        al = [k for k, t in enumerate(run) if any(c.isalpha() for c in t)]
        for m in range(len(al) - 2):
            w = run[al[m]:al[m + 2] + 1]
            for q in range(len(at) - len(w) + 1):
                if (q + len(w) <= i1 or q >= i2) and at[q:q + len(w)] == w:
                    return True
    return False


def pos_in_block(a, i):
    """where token i sits in its block, 0 (first token) to 1 (last): in running text about where its line is"""
    own = [k for k, x in enumerate(a) if x[1] == a[i][1]]
    return round(own.index(i) / max(1, len(own) - 1), 3)


def _text(text, ts, k1, k2):
    """the printed text of tokens k1..k2-1 of one block, with its own spacing"""
    return text[ts[k1][1]:ts[k2 - 1][2]]


def compare(primary_dir, oxr_dir):
    """returns (stats, subs, unread). Both readings are compared as the text they print (printed_map), token by
    token. Each disagreement carries the printed text of both sides and, within one block of the primary, the raw
    span of the primary's markdown it covers (raw_span: where repair writes). Tokens only the primary has are aligned
    a second time against what OXR has left over on the page, its tables included (OXR reads some passages in another
    order or types them as a table); what is still unread comes back as runs per block (unread), for check/unread.py."""
    A, B = MR.pages(primary_dir), OX.pages(oxr_dir)
    subs, unread = [], []
    stats = {"pages": 0, "tokens": 0, "equal": 0, "substituted": 0, "only_primary": 0, "only_oxr": 0,
             "found_elsewhere_in_oxr": 0}
    for pg in sorted(set(A) & set(B)):
        a, blk = [], {}
        for bi, typ, b in MR.units(A[pg]):     # nested captions and footnotes are prose too (10-28: a supplement of
            if typ in PRIMARY_PROSE:            # 29 tables had 19 tokens compared before they were included)
                raw = b.get("content") or ""
                text, idx = printed_map(raw)
                ts = [(m.group(0), m.start(), m.end()) for m in TOK.finditer(text)]
                blk[bi] = (typ, b, raw, text, idx, ts)
                a += [(t[0], bi, k) for k, t in enumerate(ts)]
        o, oblk, other = [], {}, []
        for n, x in enumerate(B[pg]):
            text, _ = printed_map(x.get("content") or "")
            ts = [(m.group(0), m.start(), m.end()) for m in TOK.finditer(text)]
            oblk[n] = (text, ts)
            if x["type"] in OXR_PROSE:
                o += [(t[0], n, k) for k, t in enumerate(ts)]
            else:
                other += [t[0] for t in ts]
        at, bt = [x[0] for x in a], [x[0] for x in o]
        sm = difflib.SequenceMatcher(None, at, bt, autojunk=False)
        stats["pages"] += 1; stats["tokens"] += len(at)
        left_a, left_b = [], []
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                stats["equal"] += i2 - i1
            elif op == "delete":
                left_a += range(i1, i2)
            elif op == "insert":
                stats["only_oxr"] += j2 - j1
                left_b += range(j1, j2)
            else:
                stats["substituted"] += i2 - i1
                k = kind(" ".join(at[i1:i2]), " ".join(bt[j1:j2]))
                if k == "content" and _elsewhere(at, i1, i2, bt[j1:j2]):
                    k = "reading order"
                stats["sub_" + k] = stats.get("sub_" + k, 0) + 1
                if k == "reading order":         # unrelated runs paired: both sides are left over
                    left_a += range(i1, i2); left_b += range(j1, j2)
                bis = list(dict.fromkeys(a[i][1] for i in range(i1, i2)))
                typ, b = MR.unit(A[pg], bis[0])
                one = len(bis) == 1
                if one:
                    _, _, raw, text, idx, ts = blk[bis[0]]
                    k1, k2 = a[i1][2], a[i2 - 1][2] + 1
                    ptext, rspan = _text(text, ts, k1, k2), [idx[ts[k1][1]], idx[ts[k2 - 1][2] - 1] + 1]
                else:
                    ptext, rspan = " ".join(at[i1:i2]), None
                ons = {o[j][1] for j in range(j1, j2)}
                if len(ons) == 1:
                    n = o[j1][1]
                    otext = _text(oblk[n][0], oblk[n][1], o[j1][2], o[j2 - 1][2] + 1)
                else:
                    otext = " ".join(bt[j1:j2])
                subs.append({"kind": k, "page": pg, "blocks": bis, "bbox": b.get("bbox"), "block_type": typ,
                             "pos_in_block": pos_in_block(a, i1),
                             "primary": " ".join(at[i1:i2]), "oxr": " ".join(bt[j1:j2]),
                             "primary_text": ptext, "oxr_text": otext, "raw_span": rspan,
                             "primary_toks": at[i1:i2], "oxr_toks": bt[j1:j2],
                             "left": at[max(0, i1 - 8):i1], "right": at[i2:i2 + 8],
                             "context": " ".join(at[max(0, i1 - 8):i1]) + " [...] " + " ".join(at[i2:i2 + 8])})
        # second pass: the primary's leftovers against OXR's leftovers and its other blocks (tables); a match of
        # two tokens in a row, or of one token of five characters or more, is a reading of the same words
        sa, sb = [at[i] for i in left_a], [bt[j] for j in left_b] + other
        seen = set()
        for m in difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_matching_blocks():
            if m.size >= 2 or (m.size == 1 and len(sa[m.a]) >= 5):
                seen.update(left_a[m.a:m.a + m.size])
        stats["found_elsewhere_in_oxr"] += len(seen)
        rest = [i for i in left_a if i not in seen]
        stats["only_primary"] += len(rest)
        run = []
        for i in rest + [None]:
            if run and (i is None or i != run[-1] + 1 or a[i][1] != a[run[-1]][1]):
                bi = a[run[0]][1]
                typ, b, raw, text, idx, ts = blk[bi]
                k1, k2 = a[run[0]][2], a[run[-1]][2] + 1
                unread.append({"page": pg, "block": bi, "block_type": typ, "bbox": b.get("bbox"),
                               "toks": at[run[0]:run[-1] + 1], "text": _text(text, ts, k1, k2),
                               "raw_span": [idx[ts[k1][1]], idx[ts[k2 - 1][2] - 1] + 1]})
                run = []
            if i is not None:
                run.append(i)
    return stats, subs, unread
