"""The text layer, read once per page and process. Extracting words is slow on pages with many vector paths (10-28: a
supplement page with 46,000 drawings took 62 s per call, and six checks each called it), so every check reads the
page's words here, keyed by file and page number (each check opens the PDF itself). A clip keeps the words whose
centre lies inside the rectangle."""
import pymupdf

_cache = {}

# list bullets and check marks of symbol fonts that carry no Unicode map: the layer has the font's code in the private
# use area (U+F000 + code), which every check drops as unprintable (11-02, PTA-05 mmc3: Wingdings 'l' for the bullets
# of a list, 59 bullets and check marks in 5 supplements missing from the parse with no finding). Only codes whose
# glyph is a bullet, box or check mark in that font are mapped; any other stays as it is.
DINGBATS = {"wingdings": {0x6C: "●", 0x6E: "■", 0x6F: "□", 0x71: "❑", 0x75: "◆", 0x76: "❖", 0xA7: "▪", 0xD8: "➢",
                          0xFB: "✗", 0xFC: "✓", 0xFD: "☒", 0xFE: "☑"},
            "symbol": {0xB7: "•"}}


def _dingbats(page):
    """{private-use character: its glyph} for the symbol-font characters of the page"""
    m = {}
    for b in page.get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                fam = next((k for k in DINGBATS if k in sp["font"].lower()), None)
                for c in sp["chars"] if fam else ():
                    o = ord(c["c"]) - 0xF000
                    if o in DINGBATS[fam]:
                        m[c["c"]] = DINGBATS[fam][o]
    return m


def _unseen(page, tp):
    """rectangles of white text that the page renders as nothing: its box is blank white. The layer has such text,
    the reader cannot see it (11-03, Nature-family main texts: '1234567890():,;' in white at the left edge of page 1,
    a text-layer issue in 5 documents). White text on a dark ground is seen and stays; so does the invisible text of
    a scan's OCR layer, which is not white."""
    out = []
    for b in page.get_text("dict", textpage=tp)["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if sp["color"] != 0xFFFFFF or not sp["text"].strip():
                    continue
                r = pymupdf.Rect(sp["bbox"]) & page.rect
                if r.is_empty or min(page.get_pixmap(clip=r, dpi=72, alpha=False).samples) >= 250:
                    out.append(pymupdf.Rect(sp["bbox"]))
    return out


def words(page, clip=None):
    key = (page.parent.name, page.number)
    if key not in _cache:
        tp = page.get_textpage(flags=pymupdf.TEXTFLAGS_WORDS)   # the flags of get_text("words"): unmapped glyphs by CID
        ws = page.get_text("words", textpage=tp)
        unseen = _unseen(page, tp)
        if unseen:
            ws = [w for w in ws if not any(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) in r for r in unseen)]
        if any("\uf000" <= ch <= "\uf0ff" for w in ws for ch in w[4]):
            m = _dingbats(page)
            if m:
                tr = str.maketrans(m)
                ws = [(*w[:4], w[4].translate(tr), *w[5:]) for w in ws]
        _cache[key] = tuple(ws)
    ws = _cache[key]
    if clip is None:
        return list(ws)
    return [w for w in ws if clip.x0 <= (w[0] + w[2]) / 2 <= clip.x1 and clip.y0 <= (w[1] + w[3]) / 2 <= clip.y1]


def text(page):
    return " ".join(w[4] for w in words(page))


_pages = {}


def page(doc, i):
    """page i (0-based) of doc, loaded once per file: loading a page with many vector paths takes seconds"""
    key = (doc.name, i)
    if key not in _pages:
        _pages[key] = (doc, doc[i])      # the document is kept with its page: a page outlives its opener here
    return _pages[key][1]


def blank_glyphs(page):
    """rectangles of three or more spaces in a row inside a math font's span: glyphs the font maps to no character,
    which the layer gives as spaces (11-03, PTA-05 mmc3: a Word equation 'Prob(AR to Arm i) = Prob(Arm i is the
    best)^τ / Σ ...' layered as '(   ) = (  ℎ  ) ⁄Σ =1 (  ℎ  )', and the reader copied the gaps)"""
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                if "math" not in s["font"].lower():
                    continue
                cs, i = s["chars"], 0
                while i < len(cs):
                    j = i
                    while j < len(cs) and cs[j]["c"] == " ":
                        j += 1
                    if j - i >= 3:
                        out.append(pymupdf.Rect(cs[i]["bbox"]) | pymupdf.Rect(cs[j - 1]["bbox"]))
                    i = max(j, i + 1)
    return out
