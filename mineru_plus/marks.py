"""Check-box marks drawn as images.

A form's answers can be marks placed as an image in drawn boxes: the Nature Portfolio reporting summary puts one
small image of a cross in the 'n/a' or the 'Confirmed' box of each statistics item (11-03, PTA-09 and PTA-11
supplements). The text layer has no character for them and the readers keep a few as 'x' or drop them, so which
items the authors confirmed was lost. They are content: each marked box is written to a closing section with its
column's heading and the start of its row, read from the page's geometry (the boxes, the images in them, the layer
words above and beside them)."""
import collections
import pymupdf
from . import layer as LY

SIDE = (6, 16)            # a check box's side in points


def _boxes(pg):
    out = []
    for d in pg.get_cdrawings():
        r = pymupdf.Rect(d["rect"])
        if any(it[0] == "re" for it in d["items"]) and SIDE[0] <= r.width <= SIDE[1] and abs(r.width - r.height) < 1.5:
            if not any(abs(r.x0 - o.x0) < 1 and abs(r.y0 - o.y0) < 1 for o in out):
                out.append(pymupdf.Rect(r))
    return out


def _run(words, first, gap=20, most=14, until=float("inf")):
    """the words of first's layer line from first on, until a gap wider than gap points or x until"""
    line = sorted((w for w in words if (w[5], w[6]) == (first[5], first[6]) and w[0] >= first[0]), key=lambda w: w[0])
    out = [line[0]]
    for w in line[1:]:
        if w[0] - out[-1][2] > gap or len(out) == most or w[0] >= until:
            break
        out.append(w)
    return " ".join(w[4] for w in out)


def find(pdf):
    """[{page, column, row}] for each box holding an image"""
    doc = pymupdf.open(pdf) if not isinstance(pdf, pymupdf.Document) else pdf
    found = []
    for pno in range(len(doc)):
        pg = doc[pno]
        imgs = [pymupdf.Rect(i["bbox"]) for i in pg.get_image_info() if pymupdf.Rect(i["bbox"]).width < SIDE[1]]
        if not imgs:
            continue
        boxes = _boxes(pg)
        marked = [b for b in boxes if any(b.contains((im.tl + im.br) / 2) for im in imgs)]
        if not marked:
            continue
        words = LY.words(LY.page(doc, pno))
        cols = collections.defaultdict(list)
        for b in boxes:
            cols[round(b.x0 / 3)].append(b)
        for b in marked:
            col = cols[round(b.x0 / 3)]
            top = min(c.y0 for c in col)
            mid = (b.x0 + b.x1) / 2
            head = [w for w in words if w[0] - 2 <= mid <= w[2] + 2 and w[3] <= top and top - w[3] < 40]
            # the heading over the column, not the next column's ('n/a' and 'Confirmed' set close together)
            nxt = min((c.x0 for c in boxes if c.x0 > b.x1 and abs(c.y0 - b.y0) < 2), default=float("inf"))
            head = _run(words, max(head, key=lambda w: w[3]), until=nxt) if head else ""
            # the row: the words of one layer line after the row's last box, up to a wide gap (forms set two
            # tables side by side: 'Materials & experimental systems' and 'Methods')
            right = max(c.x1 for c in boxes if abs(c.y0 - b.y0) < 2 and abs(c.x0 - b.x0) < 25)
            near = [w for w in words if right <= w[0] < right + 40 and b.y0 - 1 <= (w[1] + w[3]) / 2 <= b.y1 + 1]
            row = _run(words, min(near, key=lambda w: w[0])) if near else ""
            found.append({"page": pno + 1, "column": head, "row": row, "box": [round(x, 1) for x in b]})
    return found


def add(md, found):
    if not found:
        return md
    lines = [f"- p{f['page']}, {f['column'] or 'marked'}: {f['row']}" for f in found]
    return md.rstrip("\n") + "\n\n## Check-box marks\n\n" + "\n".join(lines) + "\n"
