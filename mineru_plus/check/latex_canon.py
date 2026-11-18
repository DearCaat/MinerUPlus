"""Canonical LaTeX for comparing two readings of one display equation (11-18).

Two readings are taken as the same only when every step below provably leaves what standard LaTeX prints unchanged
in characters and their order (contract l1.text.fidelity: characters and their order count, layout whitespace does
not, and spellings the page cannot tell apart are no error). Each step carries the reason it holds for any formula;
a spelling no such reason covers is left as it is. Two spellings left different only raise an issue someone looks
at; two spellings merged wrongly would hide an error, so where in doubt the step is not taken (rule 执-1). Input
TeX could not print (unbalanced braces, an environment ended that was not begun) has no canonical form: canon
returns None and the readings count as different.

What the steps leave out: spacing (math mode ignores spaces; \\, \\quad and the like are spacing; spaces at the two
ends of a \\text, which cannot split a word), sizes (\\left, \\right, \\big..., \\displaystyle, \\tfrac), where limits
go (\\limits, \\operatorname*), the column alignment of an array, empty rows at its end, spacing-only atom classes
(\\mathop, \\mathrel...), braces around a single item (TeX reads {x} and x alike as an argument), the alias names
plain TeX and amsmath define for one glyph (\\to for \\rightarrow, \\le for \\leq, \\mid and \\vert for |), the
environments amsmath defines as a delimited array (pmatrix, cases), and where a formula's only \\tag is written when
the formula is one equation (one number printed at its right)."""
import re, unicodedata

TOK = re.compile(r"\\[A-Za-z]+|\\.|[ \t\r\n]+|.", re.S)

# plain TeX / LaTeX / amsmath define these as the same glyph (\let or the same \mathchar or \delimiter code);
# \dfrac and \tfrac are \frac in display and text style, a size only
ALIAS = {r"\to": r"\rightarrow", r"\gets": r"\leftarrow", r"\le": r"\leq", r"\ge": r"\geq", r"\ne": r"\neq",
         r"\lbrace": r"\{", r"\rbrace": r"\}", r"\vert": "|", r"\lvert": "|", r"\rvert": "|", r"\mid": "|",
         r"\Vert": r"\|", r"\lVert": r"\|", r"\rVert": r"\|", r"\land": r"\wedge", r"\lor": r"\vee",
         r"\lnot": r"\neg", r"\dfrac": r"\frac", r"\tfrac": r"\frac"}
# print nothing, or only a size or spacing
SIZE = {r"\left", r"\right", r"\middle"} | {a + s for a in (r"\big", r"\Big", r"\bigg", r"\Bigg") for s in ("", "l", "r", "m")}
DROP = {r"\displaystyle", r"\textstyle", r"\scriptstyle", r"\scriptscriptstyle", r"\limits", r"\nolimits",
        r"\quad", r"\qquad", r"\enspace", r"\thinspace", r"\medspace", r"\thickspace", r"\negthinspace",
        r"\negmedspace", r"\negthickspace", r"\,", r"\;", r"\:", r"\!", "\\ ", "~"}
DROP_ARG = {r"\hspace", r"\phantom", r"\hphantom", r"\vphantom"}
# an atom class changes the spacing around its argument only
TRANSPARENT = {r"\mathop", r"\mathbin", r"\mathrel", r"\mathord", r"\mathpunct", r"\mathinner", r"\mathopen",
               r"\mathclose"}
# math alphabets: one name per set of glyphs. rm: \operatorname and \text print the text roman, which is the math
# roman under standard LaTeX; bf: \textbf and \mathbf both bold upright; bm: \boldsymbol and \bm both bold math
FONT = {r"\mathrm": "rm", r"\operatorname": "rm", r"\mathbf": "bf", r"\boldsymbol": "bm", r"\bm": "bm",
        r"\mathit": "ti", r"\mathcal": "cal", r"\mathbb": "bb", r"\mathfrak": "frak", r"\mathscr": "scr",
        r"\mathsf": "sf", r"\mathtt": "tt", r"\pmb": "pmb"}
TEXT = {r"\text": "rm", r"\textrm": "rm", r"\textup": "rm", r"\mbox": "rm", r"\textnormal": "rm", r"\textbf": "bf",
        r"\textit": "ti", r"\textsf": "sf", r"\texttt": "tt"}
# log-like operators print their name in the math roman (LaTeX \def\max{\mathop{\operator@font max}})
OPNAME = {r"\arccos", r"\arcsin", r"\arctan", r"\arg", r"\cos", r"\cosh", r"\cot", r"\coth", r"\csc", r"\deg",
          r"\det", r"\dim", r"\exp", r"\gcd", r"\hom", r"\inf", r"\ker", r"\lg", r"\lim", r"\liminf", r"\limsup",
          r"\ln", r"\log", r"\max", r"\min", r"\Pr", r"\sec", r"\sin", r"\sinh", r"\sup", r"\tan", r"\tanh"}
# environments that print their cells in rows and columns, differing in alignment and spacing only, and that are one
# equation; the delimited ones are defined by amsmath as \left<d> ... \right<d> around such an array
GRID = {"array", "matrix", "smallmatrix", "aligned", "gathered", "split"}
DELIM = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": (r"\{", r"\}"), "vmatrix": ("|", "|"),
         "Vmatrix": (r"\|", r"\|"), "cases": (r"\{", None)}
DIMEN = re.compile(r"\s*-?[\d.]+\s*(pt|em|ex|mm|cm|in|mu|bp|pc|dd|cc|sp)\s*")
# environments of their own equations (numbered by row, or one number placed by the environment)
OUTER = {"align", "alignat", "xalignat", "xxalignat", "flalign", "gather", "multline", "eqnarray", "equation"}
ROW = "\\\\"                                         # a row break; input can only make it as a row break
TAGMARK = "\x02tag:"                                 # input control characters never reach the output as such
# after these \dots prints as \ldots (amsmath's \dotso and \dotsc; MathJax and KaTeX follow it): punctuation, a
# closing delimiter, a column or row break. The end of a group or of the formula counts the same (amsmath looks at the
# closing brace). Not ':': amsmath's \keybin@ counts it a relation, and \dots before it prints \cdots
LDOTS_AFTER = {",", ".", ";", ")", "]", r"\}", r"\right", r"\rangle", r"\rbrace", ROW, "&"}


class Invalid(Exception):
    pass


class _State:
    def __init__(self):
        self.env, self.seen = [], set()


def _tree(s):
    """tokens nested by braces; whitespace kept as ' ' (it matters in text mode)"""
    root, stack = [], []
    cur = root
    for t in TOK.findall(s):
        if t == "{":
            stack.append(cur); cur.append([]); cur = cur[-1]
        elif t == "}":
            if not stack:
                raise Invalid("a closing brace without an opening one")
            cur = stack.pop()
        else:
            cur.append(" " if t[0] in " \t\r\n" else t)   # TeX's spaces only; other code points are characters
    if stack:
        raise Invalid("an opening brace not closed")
    return root


def _next(items, i):
    """index of the next item that is not whitespace"""
    while i < len(items) and items[i] == " ":
        i += 1
    return i


def _plain(group):
    """the raw text of a group (an environment name, a column spec)"""
    if isinstance(group, list):
        return "".join(_plain(g) if isinstance(g, list) else g for g in group)
    return group


def _seq(items, text, font, st):
    out = []
    i = 0
    while i < len(items):
        t = items[i]; i += 1
        if isinstance(t, list):                      # a group
            out.append(("G", _seq(t, text, font, st)))
            continue
        if t == " ":
            if text:
                out.append(" ")
            continue
        if text and t in ("~", "\\ "):
            out.append(" ")
            continue
        if text and t == "$":                        # math inside text
            k = i
            while k < len(items) and items[k] != "$":
                k += 1
            if k == len(items):
                raise Invalid("a $ not closed inside text")
            out.append(("G", _seq(items[i:k], False, None, st)))
            i = k + 1
            continue
        if t in ("\\operatorname", "\\tag", ROW, "\\hspace"):
            j = _next(items, i)
            star = j < len(items) and items[j] == "*"
            if star:
                i = j + 1
        else:
            star = False
        if t == ROW:
            j = _next(items, i)                     # \\[2pt]: the optional vertical space
            if j < len(items) and items[j] == "[":
                k = j + 1
                while k < len(items) and items[k] != "]":
                    k += 1
                if k < len(items) and DIMEN.fullmatch("".join(x for x in items[j + 1:k] if isinstance(x, str))):
                    i = k + 1
            out.append(ROW)
            continue
        if t in SIZE:
            j = _next(items, i)
            if j < len(items) and items[j] == ".":   # a null delimiter prints nothing
                i = j + 1
            continue
        if t in DROP:
            continue
        if t in DROP_ARG:
            j = _next(items, i)
            if j < len(items):
                i = j + 1
            continue
        if t == "\\tag":
            j = _next(items, i)
            if j < len(items):
                out.append(TAGMARK + ("*" if star else "") + _flat(_seq([items[j]], True, "rm", st)))
                i = j + 1
            continue
        if t in ("\\begin", "\\end"):
            j = _next(items, i)
            if j < len(items) and isinstance(items[j], list):
                name = _plain(items[j]).strip(); i = j + 1
                if t == "\\begin":
                    st.env.append(name); st.seen.add(name.rstrip("*"))
                elif not st.env or st.env.pop() != name:
                    raise Invalid(f"\\end{{{name}}} without its \\begin")
                key = name
                if t == "\\begin" and name in ("array", "tabular"):
                    k = _next(items, i)
                    if k < len(items) and isinstance(items[k], list):
                        spec = _plain(items[k]).replace(" ", "")
                        i = k + 1
                        if not set(spec) <= set("lcr"):  # rules or column types print something: kept
                            key = f"{name}:{spec}"
                if key in DELIM or key in GRID:
                    o, c = DELIM.get(key, (None, None))
                    if t == "\\begin":
                        if o:
                            out.append(o)
                        out.append("\\begin{grid}")
                    else:
                        while out and out[-1] == ROW:   # empty rows at the end: vertical space
                            out.pop()
                        out.append("\\end{grid}")
                        if c:
                            out.append(c)
                else:
                    out.append(f"{t}{{{key}}}")
                continue
        if t in TRANSPARENT:                          # its argument prints as it is, as one run
            j = _next(items, i)
            if j < len(items):
                out.append(("F", _unwrap(_seq([items[j]], text, font, st))))
                i = j + 1
            continue
        if t in FONT or t in TEXT:
            j = _next(items, i)
            if j < len(items):
                f = FONT.get(t) or TEXT.get(t)
                atoms = _unwrap(_seq([items[j]], t in TEXT, f, st))
                i = j + 1
                if t in TEXT:
                    while atoms and atoms[0] == " ":
                        atoms.pop(0)
                    while atoms and atoms[-1] == " ":
                        atoms.pop()
                    atoms = [a for k, a in enumerate(atoms) if not (a == " " and k and atoms[k - 1] == " ")]
                out.append(("F", atoms))
            continue
        if t in OPNAME:
            out.append(("F", [f"rm:{c}" for c in t[1:]]))
            continue
        if t == "'" and not text:
            if len(out) >= 2 and out[-2] == "^":
                raise Invalid("a prime after a superscript (TeX: double superscript)")
            n = 1
            j = _next(items, i)
            while j < len(items) and items[j] == "'":
                n += 1; i = j + 1; j = _next(items, i)
            sup = ["\\prime"] * n
            if j < len(items) and items[j] == "^":     # TeX's ' gathers a following superscript into its own
                k = _next(items, j + 1)
                if k < len(items):
                    sup += _unwrap(_seq([items[k]], text, font, st))
                    i = k + 1
            out.append("^")
            out.append(("G", sup) if len(sup) > 1 else sup[0])
            continue
        if t == r"\dots" and not text:
            # amsmath, MathJax and KaTeX print \dots as \ldots unless a binary operator, a relation or an operator
            # such as \sum follows; before punctuation, a closing delimiter or nothing it is \ldots for certain
            j = _next(items, i)
            if j >= len(items) or (isinstance(items[j], str) and items[j] in LDOTS_AFTER):
                t = r"\ldots"
        t = ALIAS.get(t, t)
        out.append(_glyph(t, text, font))
    return _finish(out)


def _glyph(t, text, font):
    if len(t) == 1 and (unicodedata.category(t) in ("Cc", "Cf", "Zl", "Zp") or t == "\x7f"):
        return f"U+{ord(t):04X}"                      # a control character is no space and no separator
    if t in ("^", "_", "&"):                          # structure, not a glyph of an alphabet
        return t
    if text:
        if t.isalnum():
            return f"{font}:{t}"
        # text punctuation is not the math glyph (- hyphen, − minus); a bold or typewriter one is not the roman one
        return f"t:{t}" if font == "rm" else f"t{font}:{t}"
    if font is None:
        return t
    if font == "rm":
        # \mathrm switches the family of letters and digits only (mathcode class 7); digits and capital Greek are
        # already roman, other symbols keep their own family
        if len(t) == 1 and t.isalpha():
            return f"rm:{t}"
        return t
    return f"{font}:{t}"


def _unwrap(seq):
    """the items of a normalised argument: a single group's content"""
    seq = list(seq)
    if len(seq) == 1 and isinstance(seq[0], tuple) and seq[0][0] in ("G", "F"):
        return list(seq[0][1])
    return seq


def _finish(out):
    """{x} and x alike; a run of one alphabet joins its neighbours unless it is an argument (after ^, _ or a
    command), where it stays one item"""
    res = []
    for a in out:
        if isinstance(a, tuple):
            kind, body = a
            body = list(body)
            if kind == "G" and len(body) == 1:
                res.append(body[0]); continue
            prev = res[-1] if res else None
            arg = prev in ("^", "_") or (isinstance(prev, str) and prev.startswith("\\") and len(prev) > 2
                                         and prev not in ("\\begin{grid}", "\\end{grid}", ROW))
            if kind == "F" and not arg:
                res.extend(body); continue
            if len(body) == 1:
                res.append(body[0]); continue
            res.append(("G", body))
            continue
        res.append(a)
    return res


def _flat(seq):
    parts = []
    for a in seq:
        if isinstance(a, tuple):
            parts.append("{" + _flat(a[1]) + "}")
        else:
            parts.append(a)
    return "\x1f".join(parts)


def _tags(seq):
    n = 0
    for a in seq:
        if isinstance(a, tuple):
            n += _tags(a[1])
        elif a.startswith(TAGMARK):
            n += 1
    return n


def _untag(seq):
    res, tag = [], None
    for a in seq:
        if isinstance(a, tuple):
            body, t = _untag(a[1])
            res.append((a[0], body)); tag = tag or t
        elif a.startswith(TAGMARK):
            tag = a
        else:
            res.append(a)
    return res, tag


def canon(s):
    """the canonical form, or None where the input is no LaTeX that prints"""
    try:
        st = _State()
        seq = _seq(_tree(s or ""), False, None, st)
        if st.env:
            raise Invalid(f"\\begin{{{st.env[-1]}}} not ended")
    except (Invalid, RecursionError):
        return None
    # one \tag in a formula that is one equation is one number at its right wherever it is written (inside the last
    # row of an array or after it); in an environment of several equations (align, gather...) a number belongs to its
    # row, and several numbers keep their places
    if _tags(seq) == 1 and not st.seen & OUTER:
        seq, tag = _untag(seq)
        seq = _finish(seq)
        return _flat(seq) + "\x1e" + tag
    return _flat(seq)
