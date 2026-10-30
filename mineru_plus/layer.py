"""The text layer, read once per page and process. Extracting words is slow on pages with many vector paths (10-28: a
supplement page with 46,000 drawings took 62 s per call, and six checks each called it), so every check reads the
page's words here, keyed by file and page number (each check opens the PDF itself). A clip keeps the words whose
centre lies inside the rectangle."""
_cache = {}


def words(page, clip=None):
    key = (page.parent.name, page.number)
    if key not in _cache:
        _cache[key] = tuple(page.get_text("words"))
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
