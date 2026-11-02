"""The paper's source document, when the caller has one: JATS XML, the publisher's or arXiv's HTML, or the LaTeX source.

A source holds the words the authors wrote. It is a witness of the printed page, not the page: a preprint's source can
be another version, its tables and formulas are rendered differently, and a list marker or a citation may not be in
it as printed. So it answers two questions only, and only where its text around the place is the parse's text:

  hyphen(left, a, b, right)   which of two spellings of a line-break word the source writes ('well-documented' or
                              'welldocumented'): the page prints a hyphen at the line end either way, so the text
                              layer and the judges cannot tell; the source can (11-02, eight JATS and seven arXiv HTML
                              sources: the line-break words both readers had joined against the source,
                              'under-represented', 'under-specified', were the main residue no other check finds)
  spells(left, a, b, right)   which of two readings with different letters or digits the source writes; the caller
                              asks it about Latin words only and takes it where the text layer does not hold the other
                              reading (a source of another version may correct a word the page prints wrong)

Each holds when the reading, with up to two words of the parse on each side, is in the source and the other reading
with the same words is not. Spaces, punctuation and markup are not compared (a source renders them differently); the
hyphen question keeps hyphens. Nothing is fetched: the caller passes the files it has.

  load(paths)   the source documents as one Source: .xml/.nxml (JATS or other XML), .html/.htm/.xhtml, .tex, or a
                directory or .tar(.gz) of a LaTeX source
"""
import html, re, tarfile, unicodedata
from html.parser import HTMLParser
from pathlib import Path
from .check import two_readings as TR

# not printed: the TeX of a formula next to its MathML, scripts and styles, the head of an HTML page
SKIP = {"tex-math", "annotation", "annotation-xml", "script", "style", "head", "alt-text"}


class _Text(HTMLParser):
    """the character data of an XML or HTML document, outside SKIP elements (tag names without a namespace prefix)"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag.split(":")[-1] in SKIP:
            self.skip += 1
        self.out.append(" ")

    def handle_endtag(self, tag):
        if tag.split(":")[-1] in SKIP and self.skip:
            self.skip -= 1
        self.out.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.out.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def markup_text(s):
    p = _Text()
    p.feed(s)
    p.close()
    return "".join(p.out)


# LaTeX: what does not print, then commands; a command's text argument stays when its braces go
TEX_COMMENT = re.compile(r"(?<!\\)%.*")
TEX_DROP = re.compile(r"\\(?:cite[a-z]*|[cC]?ref|eqref|autoref|label|url|href|includegraphics|bibliography(?:style)?|"
                      r"input|include|usepackage|documentclass|[vh]space|newcommand|renewcommand|def)\*?"
                      r"(?:\[[^\]]*\])*(?:\{[^{}]*\})?")
TEX_MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.S)
TEX_QUOTES = [("---", "—"), ("--", "–"), ("``", "“"), ("''", "”"), ("`", "‘"), ("~", " "), (r"\-", ""),
              (r"\&", "&"), (r"\%", "%"), (r"\_", "_"), (r"\#", "#"), ("\uff04", "$")]


def tex_text(s):
    s = TEX_COMMENT.sub("", s)
    s = TEX_DROP.sub(" ", s).replace(r"\$", "\uff04")            # an escaped dollar is no math delimiter
    s = TEX_MATH.sub(lambda m: " " + TR.latex_plain(next(g for g in m.groups() if g is not None)) + " ", s)
    for a, b in TEX_QUOTES:
        s = s.replace(a, b)
    s = TR.LATEX_CMD.sub(lambda m: TR.LATEX.get(m.group(), " "), s)
    return re.sub(r"[{}^_]", "", s)


def _read(path):
    p = Path(path)
    if p.is_dir():
        return " ".join(tex_text(f.read_text(encoding="utf-8", errors="replace")) for f in sorted(p.rglob("*.tex")))
    name = p.name.lower()
    if name.endswith((".tar", ".tar.gz", ".tgz")):
        with tarfile.open(p) as t:          # read in memory, nothing extracted to disk
            return " ".join(tex_text(t.extractfile(m).read().decode(errors="replace"))
                            for m in sorted(t.getmembers(), key=lambda m: m.name)
                            if m.isfile() and m.name.lower().endswith(".tex"))
    s = p.read_text(encoding="utf-8", errors="replace")
    if name.endswith(".tex"):
        return tex_text(s)
    if name.endswith((".xml", ".nxml", ".html", ".htm", ".xhtml")):
        return markup_text(s)
    raise ValueError(f"source {p}: not .xml, .nxml, .html, .htm, .xhtml, .tex, a LaTeX directory or a .tar(.gz)")


def letters(x):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", html.unescape(x)))


def hyphened(x):
    """letters, digits and hyphens: a soft hyphen is not a hyphen of the word"""
    x = unicodedata.normalize("NFKC", html.unescape(x)).replace("­", "")
    return re.sub(r"[^\w-]", "", re.sub("[‐‑]", "-", x))


class Source:
    def __init__(self, text, names=()):
        self.names = list(names)
        self.chars = len(text)
        self._l, self._h = letters(text), hyphened(text)

    def _says(self, f, S, left, a, b, right):
        fa, fb = f(a), f(b)
        if fa == fb or not (fa or fb):
            return None
        for n in (2, 1):                    # two words of context each side, else one
            lc, rc = f("".join(left[-n:])), f("".join(right[:n]))
            if not (lc and rc):
                continue
            ha, hb = lc + fa + rc in S, lc + fb + rc in S
            if ha != hb:
                return 0 if ha else 1
            if ha:                          # both written in the source: it does not decide
                return None
        return None

    def hyphen(self, left, a, b, right):
        """0 where the source writes a, 1 where b, else None; a and b differ by a hyphen"""
        return self._says(hyphened, self._h, left, a, b, right)

    def spells(self, left, a, b, right):
        """0 where the source writes a, 1 where b, else None; letters and digits compared"""
        return self._says(letters, self._l, left, a, b, right)


def load(paths):
    paths = [p for p in (paths or []) if p]
    if not paths:
        return None
    return Source(" ".join(_read(p) for p in paths), [Path(p).name for p in paths])
