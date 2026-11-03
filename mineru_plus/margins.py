"""Page margins: running headers, footers, page numbers and side notes. MinerU recognises them as blocks but leaves
many out of its markdown (9 papers, 10-29: 186 headers, 153 footers, 83 page numbers, 69 side notes missing). They
are content of the paper (journal, volume, dates, DOIs, author-manuscript notices), so every one missing from the
running text is written to a closing section of full.md, page by page, keeping the running text clean.

Each is checked against the text layer of its box where the page has one (born-digital pages: the layer is the
document's own text). A margin block whose characters differ from the layer is an open issue with its page; pages
without a text layer are written as read and counted.

A logo or badge is a picture, and a picture's text is not read (11-03 文浩: "logo是logo为什么算印的字？本质不和图片一样？
我们不读图，不做图片文本的解析"; the readings were 'Q', 'll', 'CelPress', 'heck k for'). Whether a block is one is
jev's question, not a rule of the layer (文浩: "让jev看下就知道是不是logo了"): a text drawn as outlines has no layer and
is printed text, the CellPress logo holds a layer 'll'. The blocks the layer does not confirm (other characters in
the box, or glyphs drawn as curves beside its words) are shown to jev, one crop per text and place; a logo is left
out (not written, not reported, counted), printed text is written and checked as before, an undecided one is written
and reported."""
import base64, collections, hashlib, re
from pathlib import Path
import pymupdf
from .readers import mineru as MR
from .check.two_readings import toks, printed_map
from .check import dropped as DR, jev, gemini
from .check.tables import layer_tokens
from . import layer as LY

MARGIN = ("header", "footer", "page_number", "aside_text", "page_footnote")
NAMES = {"header": "header", "footer": "footer", "page_number": "page number", "aside_text": "side note",
         "page_footnote": "page footnote"}
WS = re.compile(r"\s+")
LINK = re.compile(r"\[([^\]]*)\]\(\1\)")


def _same_words(lay, text):
    """the same words, the lines in another order: the layer of a side note set vertically runs its lines bottom to
    top (10-29, medRxiv: the copyright notice on every page, 24 pages reported as differing, word for word equal)"""
    norm = lambda ws: collections.Counter("".join(x for c in w for x in DR._norm_char(c)) for w in ws)
    mine = toks(printed_map(text)[0])
    return norm(w for w in lay if w.strip()) == norm(mine)


def _alnum(text):
    return "".join(c.lower() for c, _ in DR.plain_map(text) if c.isalnum())


def _outlined(pg, r, drawings):
    """glyphs drawn as curves in the box apart from its layer words: part of what the box prints is not in the layer
    (11-03, PTA-05 and PTA-10: the CellPress logo draws 'Ce' and 'Press' as curves around a layer 'll', and the
    block read 'll' matched the layer)"""
    words = [pymupdf.Rect(w[:4]) for w in LY.words(pg, r)]
    for d in drawings:
        q = pymupdf.Rect(d["rect"])
        if q.height >= 0.3 * r.height and (q & r).get_area() > 0.5 * q.get_area() and \
                any(it[0] == "c" for it in d["items"]) and not any(q.intersects(w) for w in words):
            return True
    return False


# the region alone, and no quoted reading: with the margin around it and the reader's 'CO' quoted, jev took the open
# access padlock beside the running head 'Article' for text (11-03, PTA-07; P 0.5 either way); cut to the box it reads
# the padlock, 'Cell', 'Q' and the CellPress logo as pictures and 'Article' as text (P >= 0.7 in both orders)
INSTR = "The image is a region of a printed page. Decide what it shows."
PICTURE = "A picture: a logo, an icon, a badge, an emblem or a drawing (letters may be part of the design)"
TEXT = "Plain text: letters or digits set in an ordinary font"


def _crop(page, box, path):
    # upright through the page's rotation (11-03, PTA-05 pages 6-8: the unrotated box cut a table heading, read as text)
    gemini._image(page, (box + (-4, -4, 4, 4)) & (page.rect * page.derotation_matrix), 200).save(str(path))
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _pictures(asked, work):
    """{(text, place): 'logo' | 'printed' | 'undecided' | ...} from jev, one crop per text and place"""
    qs = []
    for (text, place), (page, box) in asked.items():
        qid = "m" + hashlib.md5(f"{text}|{place}".encode()).hexdigest()[:10]
        img = _crop(page, box, Path(work) / f"{qid}.png")
        qs.append({"id": qid, "key": (text, place), "state": "A region of a page.", "instructions": INSTR,
                   "images": [img], "options": {"logo": PICTURE, "printed": TEXT}})
    v = jev.ask([{k: x for k, x in q.items() if k != "key"} for q in qs], work, "margins") if qs else {}
    return {q["key"]: v.get(q["id"], "not judged") for q in qs}


def add(pdf, mdir, md, no_layer_pages=(), work=None):
    pdf = pymupdf.open(pdf) if not isinstance(pdf, pymupdf.Document) else pdf
    pages = MR.pages(mdir)
    md_alnum = _alnum(md)
    paras = collections.Counter(_alnum(p) for p in re.split(r"\n\s*\n", md))
    # the running text's own blocks hold their occurrences: a margin block is 'in the text' only by the ones left over
    # (11-03, PTA-10: the heading 'Article' of page 2 counted for the running head 'Article' of page 1, which was left
    # out)
    body = [_alnum(b.get("content") or "") for pg in pages for _, b in pages[pg] if b["type"] not in MARGIN]
    used = collections.Counter()
    for p in body:
        if p:
            used["p", p] += 1

    def already(text):
        """the reader wrote this block into the running text: a paragraph of its own, or (four words or more) inside
        one in other markup (11-02, PTA-09: the affiliation footnote of page 1 with a link). Each occurrence stands for
        one block: a running head printed on every page is not 'in the text' because a citation names the journal, and
        a logo read 'll' is no word of the text (11-02, PTA-05: the CellPress head of the odd pages was left out)"""
        k = _alnum(text)
        if k and paras[k] > used["p", k]:
            used["p", k] += 1
            return True
        if k and len(text.split()) >= 4 and md_alnum.count(k) > used["s", k] + sum(p.count(k) for p in body):
            used["s", k] += 1
            return True
        return False
    lines, issues, stats, drawn, ask, asked = [], [], collections.Counter(), {}, [], {}
    for pg in sorted(pages):
        for bi, b in pages[pg]:
            if b["type"] not in MARGIN:
                continue
            text = (b.get("content") or "").strip()
            if not text:
                continue
            stats[b["type"]] += 1
            if already(text):
                stats["already in text"] += 1
                continue
            item = {"line": f"- p{pg} {NAMES[b['type']]}: {WS.sub(' ', text)}", "page": pg, "block": bi,
                    "type": b["type"], "text": text}
            if pg in no_layer_pages or not b.get("bbox"):
                stats["unverified (no text layer)"] += 1
                ask.append((item, None))
                continue
            lay = layer_tokens(pdf, pg, b["bbox"])
            item["layer"] = " ".join(lay)[:500]
            # printed characters on both sides: markdown escapes and tags of the block dropped, spacing ignored
            # (letter-spaced running heads split words differently on the layer); a link printed as its address
            # once ('[https://doi.org/…](https://doi.org/…)', 11-03 PTA-05 and PTA-10: taken for a badge)
            shown = LINK.sub(r"\1", text)
            lc = "".join(c for w in lay for ch in w for c in DR._norm_char(ch))
            bc = "".join(c for c, _ in DR.plain_map(shown))
            page = LY.page(pdf, pg - 1)
            box = pymupdf.Rect(b["bbox"][0] * page.rect.width, b["bbox"][1] * page.rect.height,
                               b["bbox"][2] * page.rect.width, b["bbox"][3] * page.rect.height) * page.derotation_matrix
            if pg not in drawn:
                drawn[pg] = page.get_cdrawings()
            item["equal"] = lc == bc or _same_words(lay, shown)
            # the layer does not confirm it: other characters in the box (10-29: the CellPress logo holds only 'll'),
            # or glyphs drawn as curves beside the layer words there (11-03: 'Ce' and 'Press' around a layer 'll')
            if not item["equal"] or _outlined(page, box, drawn[pg]):
                place = (b["type"], round(box.x0 / 10), round(box.y0 / 10))
                item["key"] = (text, place)
                asked.setdefault(item["key"], (page, box))
            ask.append((item, item.get("key")))
    seen = {}
    if asked and work is not None:
        Path(work).mkdir(parents=True, exist_ok=True)
        seen = _pictures(asked, work)
    for item, key in ask:
        v = seen.get(key) if key else None
        if v == "logo":
            stats["logos and badges (jev), left out"] += 1
            continue
        stats["written"] += 1
        lines.append(item["line"])
        if "layer" not in item:
            continue
        if key and v != "printed":
            stats["picture or printed text not settled (jev)"] += 1
            issues.append({"kind": "margin block: a picture or printed text, not settled", "page": item["page"],
                           "block": item["block"], "type": item["type"], "text": item["text"],
                           "layer": item["layer"], "why": f"jev: {v or 'not asked'}"})
        elif item["equal"]:
            stats["equal to the text layer"] += 1
        else:
            stats["differs from the text layer"] += 1
            issues.append({"kind": "margin text differs from the text layer", "page": item["page"],
                           "block": item["block"], "type": item["type"], "text": item["text"], "layer": item["layer"]})
    # the same margin text differing the same way on many pages is one finding (a running head or logo)
    grouped = {}
    for i in issues:
        g = grouped.setdefault((i["kind"], i["type"], i["text"], i["layer"]), {**i, "pages": []})
        g["pages"].append(i["page"])
    issues = [{k: v for k, v in g.items() if k not in ("page", "block")} for g in grouped.values()]
    if lines:
        md = md.rstrip("\n") + "\n\n## Page headers, footers and page numbers\n\n" + "\n".join(lines) + "\n"
    return md, dict(stats), issues
