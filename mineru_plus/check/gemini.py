"""Page-reading judge for character disagreements.

Each disagreement gets a tight crop around the passage (about 100 pt each side, 300 dpi); crops are stacked eight to
a numbered sheet, and one session per option order reads all sheets and answers A / B / neither for every item. The
session is the page_judge backend (mineru_plus/backends): a CLI agent or an OpenAI-compatible endpoint, as the config
file says. The question text and the crops are made here.

A reading is decided when both orders choose it. Cheap by design (10-28: undecided is acceptable, it goes back to the
calling agent): two sessions per document; undecided items keep their crop for the agent.

Measured 10-28 on 106 items (34 printed typos, 12 real, 60 layer errors): 0 wrong among decided; undecided 9/34,
4/12, 5/60; about 0.5k new input + 0.4k cached tokens per item and order.
"""
import base64, json, re, threading, unicodedata
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from .. import backends
from .. import layer as LY

PER_SHEET = 8
INSTR = ("Each strip is labelled #N on a yellow band; strips are separated by red lines. For each item, two programs "
         "read the passage in strip #N and disagree at the marked place. Which one matches what the page prints, "
         "character by character? The page may contain typing errors or unusual symbols; judge what is printed, not "
         "what is correct. Judge each item only from its own strip.")


def _letters(x):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", x))


def _lines(pg):
    """the page's text-layer lines as rectangles (unrotated coordinates). Pieces of one printed line that the layer
    keeps as separate lines (10-30: a line of a held-out paper set as several layer lines, the crop ending mid-line)
    are joined: same baseline band, a gap no wider than a word space."""
    ls = {}
    for w in LY.words(pg):
        k = (w[5], w[6])
        ls[k] = ls[k] | pymupdf.Rect(w[:4]) if k in ls else pymupdf.Rect(w[:4])
    out = []
    for r in sorted(ls.values(), key=lambda r: (round(r.y1), r.x0)):
        for i, o in enumerate(out):
            same = min(r.y1, o.y1) - max(r.y0, o.y0) > 0.6 * min(r.height, o.height)
            gap = max(r.x0 - o.x1, o.x0 - r.x1)
            if same and gap < 0.6 * min(r.height, o.height):
                out[i] = o | r
                break
        else:
            out.append(pymupdf.Rect(r))
    return out


def _rect(pg, hit, block):
    """the line of the hit with the line before and the line after, each line whole (10-30: a crop of 160 pt each
    side of the hit cut 'AUROC' to 'ROC)' and 'H&E-' off a line end; with the hit line and the next one only, 'H&E-'
    ending the line above was cut off and the judge could read neither reading). Lines are the text layer's; those
    taken are the ones in the block's column (the hit's own extent where the block is unknown)."""
    # a layer 'line' much taller than the hit is not a line of text (10-30: on pages set with math fonts some 'lines'
    # span a paragraph, and the crop grew to half the page)
    lines = [l for l in _lines(pg) if l.height <= 2 * hit.height]
    vo = lambda r: min(r.y1, hit.y1) - max(r.y0, hit.y0)
    own = [r for r in lines if vo(r) > 0.5 * min(r.height, hit.height) and r.x0 < hit.x1 and r.x1 > hit.x0]
    base = pymupdf.Rect(hit)
    for r in own:
        base |= r
    lh = min([r.height for r in own] or [hit.height]) or 8
    x0, x1 = (block.x0, block.x1) if block is not None else (base.x0, base.x1)
    lo, hi = base.y0 - 1.6 * lh, base.y1 + 1.6 * lh
    r = pymupdf.Rect(base)
    for l in lines:
        if lo <= (l.y0 + l.y1) / 2 <= hi and l.x0 < x1 and l.x1 > x0:
            r |= l
    return pymupdf.Rect(r.x0 - 6, r.y0 - 0.4 * lh, r.x1 + 6, r.y1 + 0.4 * lh) & pg.rect


def _image(pg, r, dpi):
    """the page inside r (unrotated coordinates) as an upright PIL image: rotated pages are rendered through the
    page's rotation, and text set sideways (rotated tables, margin notes) is turned to read left to right"""
    from .table_layer import _upright
    pix = pg.get_pixmap(dpi=dpi, clip=r * pg.rotation_matrix)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    rot = _upright(pg, r)
    return im.rotate(rot, expand=True) if rot else im


def _seq(text, words, start=0):
    """end of the words found in order in text from start, or None"""
    for w in words:
        i = text.find(w, start)
        if i < 0:
            return None
        start = i + len(w)
    return start


def _ordered(inside, lw, reads, rw):
    """1 for a reading found in the crop, plus 1 for the context word before it, plus 1 for the one after it, all in
    reading order (10-30: in a reference list 'url' was found in another entry than the one of the passage, its
    context words elsewhere in the crop)"""
    if not reads:                      # readings without letters (a symbol, punctuation): the context words in order
        i = inside.find(lw[0]) if lw else -1
        e = i + len(lw[0]) if i >= 0 else 0
        return 1 + (i >= 0) + (bool(rw) and inside.find(rw[0], e) >= 0)
    best = 0
    for rd in reads:
        starts = [i for i in range(len(inside)) if inside.startswith(rd[0], i)]
        for i in starts:
            e = _seq(inside, rd, i)
            if e is None:
                continue
            before = bool(lw) and inside.rfind(lw[0], 0, i) >= 0
            after = bool(rw) and inside.find(rw[0], e) >= 0
            best = max(best, 1 + before + after)
    return best


def _crop(doc, page, bbox, toks, path, pos=None):
    pg, r, how = _place(doc, page, bbox, toks, pos)
    if r is None:
        _image(pg, pg.rect, 100).save(str(path))
        return str(path), None
    _image(pg, r, 300).save(str(path))
    return str(path), how


def _place(doc, page, bbox, toks, pos=None):
    """Crop around the passage. Candidate places come from searching the text layer (passage with left context, the
    passage, its longest words). A candidate is scored by the layer words inside it, a check that needs no judge:
    one reading whole (the primary copies the layer; where the primary is the wrong side, the layer reads like OXR),
    and the context word on each side, in reading order. 'text layer': reading and both sides; 'text layer, one
    side': reading and one side (the other side's context may be in another block). Returns (page, rect or None,
    how it was placed or None). _crop saves it; the crop the judges see is the one gate() passes."""
    pg = LY.page(doc, page - 1)
    W, H = pg.rect.width, pg.rect.height
    block = pymupdf.Rect(bbox[0] * W, bbox[1] * H, bbox[2] * W, bbox[3] * H) * pg.derotation_matrix if bbox else None
    left, prim = toks.get("left", []), toks.get("primary", [])
    right, alt = toks.get("right", []), toks.get("oxr", [])
    word = lambda ts: [_letters(t) for t in ts if len(_letters(t)) > 1]
    reads = [w for w in (word(prim), word(alt)) if w]
    lw, rw = word(left)[-1:], word(right)[:1]
    tries = [" ".join(left[-2:] + prim[:2]), " ".join(left[-1:] + prim[:1]), " ".join(prim)]
    if alt:
        tries += [" ".join(left[-2:] + alt[:2]), " ".join(alt)]
    tries += [" ".join(left[-2:]), " ".join(right[:2])]
    tries += sorted([t for t in prim + left[-2:] if len(t) >= 3], key=len, reverse=True)[:3]
    first, best, best_score = None, None, 0
    for t in tries:
        t = t.strip()
        if len(t) < 2:
            continue
        for clip in ([block, None] if block else [None]):
            for hit in (pg.search_for(t, clip=clip) if clip else pg.search_for(t)):
                r = _rect(pg, hit, block)
                first = first or r
                inside = _letters("".join(w[4] for w in LY.words(pg, r)))
                score = _ordered(inside, lw, reads, rw) if (lw or rw or reads) else 0
                if score > best_score:
                    best, best_score = r, score
                if best_score == 3:
                    break
            if best_score == 3:
                break
        if best_score == 3:
            break
    r = best if best_score >= 2 else None
    how = ("text layer" if best_score == 3 or (best_score == 2 and not (lw and rw)) else "text layer, one side") if r else None
    if r is None and block is not None and pos is not None:
        # no layer to verify against (scanned page) or it holds neither reading: a band of about five lines around
        # where the passage sits in its block (token position ~ line position in running text)
        y = block.y0 + pos * block.height
        r = pymupdf.Rect(block.x0 - 4, max(block.y0 - 4, y - 32), block.x1 + 4, min(block.y1 + 4, y + 32)) & pg.rect
        how = "position in block"
    if r is None:
        r, how = first, "text layer search, unverified"
    if r is None:
        r = block if block else pg.rect
        r = pymupdf.Rect(r.x0, r.y0, r.x1, min(r.y1, r.y0 + 60)) & pg.rect
        how = None
    if r.is_empty or r.width < 4 or r.height < 4:      # nothing locatable
        return pg, None, None
    return pg, r, how


def _widen(pg, r, block):
    """r with one more line above and below, to the block's width (or the page's, where the block is unknown)"""
    inner = [l for l in _lines(pg) if (l & r).height > 0.5 * l.height]
    lh = min([l.height for l in inner] or [10])
    x0, x1 = (min(block.x0, r.x0), max(block.x1, r.x1)) if block is not None else (pg.rect.x0 + 18, pg.rect.x1 - 18)
    out = pymupdf.Rect(x0, r.y0, x1, r.y1)
    for l in _lines(pg):
        if l.height <= 2 * lh and r.y0 - 2 * lh <= (l.y0 + l.y1) / 2 <= r.y1 + 2 * lh and l.x0 < x1 and l.x1 > x0:
            out |= l
    return pymupdf.Rect(out.x0 - 6, out.y0 - 0.4 * lh, out.x1 + 6, out.y1 + 0.4 * lh) & pg.rect


GATE_INSTR = ("The image is a strip cut from a page. Does the strip show this whole stretch of text: the words before, "
              "the disputed part, and the words after, all visible and not cut off at an edge of the strip? Small "
              "differences in characters, spacing and line breaks do not matter.")


GATE_SIDE = ("The image is a strip cut from a page. Does the strip show this stretch of text: the {side} and the "
             "disputed part, all visible and not cut off at an edge of the strip? Small differences in characters, "
             "spacing and line breaks do not matter.")


def _gate_q(qid, it, img, side=None):
    t = it["toks"]
    L, R = " ".join(t.get("left", [])[-2:]), " ".join(t.get("right", [])[:2])
    d = f"The disputed part, read in two ways: «{it['primary']}» or «{it['oxr']}»."
    if side:
        return {"id": qid, "images": [img], "instructions": GATE_SIDE.format(side=f"words {side}"),
                "state": f"Words before: «{L}». {d}" if side == "before" else f"{d} Words after: «{R}».",
                "options": {"yes": "Yes, the whole stretch is visible in the strip.",
                            "no": "No, part of it is missing or cut off."}}
    return {"id": qid, "images": [img], "instructions": GATE_INSTR,
            "state": f"Words before: «{L}». {d} Words after: «{R}».",
            "options": {"yes": "Yes, the whole stretch is visible in the strip.",
                        "no": "No, part of it is missing or cut off."}}


def _b64(pg, r, dpi):
    buf = __import__("io").BytesIO(); _image(pg, r, dpi).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def place(pdf, items, work):
    """The crop each judge sees, checked by jev before any judge looks at it (10-30: the placement rules are
    distances in points and text-layer search, and a crop that cuts the passage leaves every judge guessing).
    jev is asked whether the crop shows the two words before, the disputed part and the two words after, whole, in
    both option orders. 10-30, 396 crops of 37 papers: where the text layer found the passage, jev said yes to 334
    and no to 24, and the noes it gave were mostly crops that were wrong (another entry of a reference list, the
    bottom or the end of the line cut off); where the layer did not, jev said yes to 14, all right on inspection.
    A crop jev rejects is widened by a line each way and asked again, then placed by jev on windows of the block
    (_jev_place) and asked again. Returns {id: {"path", "placed_by", "checked"}}; checked False: no crop passed and
    the item is not judged."""
    from . import jev
    if not items:
        return {}
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    out, rect = {}, {}
    for it in items:
        pg, r, how = _place(doc, it["page"], it["bbox"], it["toks"], it.get("pos"))
        rect[it["id"]] = (pg, r)
        out[it["id"]] = {"path": str(work / "crops" / f"{it['id']}.png"), "placed_by": how or "not placed",
                         "checked": False}
    by_id = {it["id"]: it for it in items}

    def ask(ids, tag):
        qs = [_gate_q(i, by_id[i], _b64(*rect[i], 170)) for i in ids if rect[i][1] is not None]
        ans = jev.ask(qs, work, tag) if qs else {}
        for i in ids:
            if ans.get(i) == "yes":
                out[i]["checked"] = True
        return [i for i in ids if not out[i]["checked"]]

    left = ask(list(out), "gate")
    for i in left:
        pg, r = rect[i]
        if r is not None:
            b = by_id[i]["bbox"]; W, H = pg.rect.width, pg.rect.height
            block = pymupdf.Rect(b[0] * W, b[1] * H, b[2] * W, b[3] * H) * pg.derotation_matrix if b else None
            rect[i] = (pg, _widen(pg, r, block))
            out[i]["placed_by"] += ", widened"
    left = ask(left, "gate_widened")
    # where the text layer found the context of one side only, the other side's words are in another block (an
    # author list followed by the title, a colon before a displayed equation; 10-30, 21 of the 22 crops no step
    # passed were of this kind or wrongly placed): jev checks the side that is there
    one = [i for i in left if out[i]["placed_by"].startswith("text layer, one side")]
    if one:
        qs = [_gate_q(f"{i}|{sd}", by_id[i], _b64(*rect[i], 170), sd) for i in one for sd in ("before", "after")]
        ans = jev.ask(qs, work, "gate_one_side")
        for i in one:
            if "yes" in (ans.get(f"{i}|before"), ans.get(f"{i}|after")):
                out[i]["checked"], out[i]["placed_by"] = True, out[i]["placed_by"] + ", one side checked"
        left = [i for i in left if not out[i]["checked"]]
    for i, (pg, r) in _jev_place(doc, items, set(left), work).items():
        rect[i] = (pg, r)
        out[i]["placed_by"] = "jev window"
    left = ask([i for i in left if out[i]["placed_by"] == "jev window"], "gate_window")
    for i, o in out.items():
        pg, r = rect[i]
        _image(pg, r if r is not None else pg.rect, 300 if r is not None else 100).save(o["path"])
    tally = __import__("collections").Counter(f"{o['placed_by']} | {'checked' if o['checked'] else 'not checked'}"
                                              for o in out.values())
    (work / "gate.json").write_text(json.dumps({"items": len(items), "placed_by": dict(tally.most_common())}, indent=1))
    return out


def _jev_place(doc, items, unverified, work):
    """Fallback for crops the text layer cannot verify: the block is cut into windows of two lines and jev is asked
    per window whether it shows the passage (both option orders). A window is used only when jev says yes to exactly
    one. 10-28, 60 items the layer can place: 44 right, 4 wrong window, 12 none; so it is a fallback, marked as such."""
    from . import jev
    qs, wins_of = [], {}
    for it in items:
        if it["id"] not in unverified or not it.get("bbox"):
            continue
        pg = LY.page(doc, it["page"] - 1); W, H = pg.rect.width, pg.rect.height; b = it["bbox"]
        block = pymupdf.Rect(b[0] * W, b[1] * H, b[2] * W, b[3] * H) * pg.derotation_matrix
        lines = {}
        for w in LY.words(pg, block):
            lines.setdefault((w[5], w[6]), []).append(w)
        ls = [pymupdf.Rect(min(w[0] for w in v), min(w[1] for w in v), max(w[2] for w in v), max(w[3] for w in v))
              for _, v in sorted(lines.items())]
        wins = [pymupdf.Rect(block.x0 - 4, (ls[i] | ls[i + 1]).y0 - 3, block.x1 + 4, (ls[i] | ls[i + 1]).y1 + 3) & pg.rect
                for i in range(len(ls) - 1)][:12]
        if len(wins) < 2:
            continue
        wins_of[it["id"]] = (pg, wins)
        t = it["toks"]
        passage = " ".join(t.get("left", [])[-3:] + t.get("primary", []) + t.get("right", [])[:3])
        for k, r in enumerate(wins):
            buf = __import__("io").BytesIO(); _image(pg, r, 170).save(buf, "PNG")
            img = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            qs.append({"id": f"{it['id']}|{k}", "state": "A strip cut from a page of a scientific paper.",
                       "instructions": "Does this strip of the page show the following passage (wording may differ in "
                                       "small details, spacing and line breaks do not matter)? Passage: " + passage,
                       "options": {"yes": "Yes, the strip shows this passage.", "no": "No, the passage is not in this strip."},
                       "images": [img]})
    ans = jev.ask(qs, work, "place") if qs else {}
    placed = {}
    for iid, (pg, wins) in wins_of.items():
        yes = [k for k in range(len(wins)) if ans.get(f"{iid}|{k}") == "yes"]
        if len(yes) == 1:
            placed[iid] = (pg, wins[yes[0]])
    return placed


def _sheets(crops, out):
    font = ImageFont.load_default(size=56)
    paths = []
    for s0 in range(0, len(crops), PER_SHEET):
        ims = [Image.open(c).convert("RGB") for c in crops[s0:s0 + PER_SHEET]]
        wd, band = max(im.width for im in ims), 72
        sheet = Image.new("RGB", (wd, sum(im.height + band + 20 for im in ims)), "white")
        y = 0
        for k, im in enumerate(ims):
            d = ImageDraw.Draw(sheet)
            d.rectangle([0, y, wd, y + band], fill=(255, 235, 160))
            d.text((16, y + 6), f"#{s0 + k + 1}", fill="black", font=font)
            sheet.paste(im, (0, y + band)); y += band + im.height
            d.line([0, y + 10, wd, y + 10], fill="red", width=4); y += 20
        p = out / f"sheet{len(paths) + 1:02d}.png"
        sheet.save(p); paths.append(str(p))
    return paths


def _shown(t):
    """control characters as U+FFFD: a reading may hold a NUL (10-29: one in a held-out paper's title page), and a
    prompt with one cannot be passed to the judge at all"""
    return "".join("\ufffd" if unicodedata.category(c) == "Cc" and c not in "\n\t" else c for c in t)


def judge(pdf, items, work, placed):
    """items: [{id, page, bbox, left, right, primary, oxr, toks}], each with a crop place() checked ->
    ({id: 'primary'|'oxr'|'neither'|'undecided'|'not judged: ...'}, usage)"""
    if not items:
        return {}, {}
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    crops = {it["id"]: placed[it["id"]]["path"] for it in items}
    sheets = _sheets([crops[it["id"]] for it in items], work / "crops")
    res, usage = {}, {}
    page = backends.get("page_judge")

    def ask(order):
        lines = []
        for n, it in enumerate(items, 1):
            a, b = (it["primary"], it["oxr"]) if order == "a" else (it["oxr"], it["primary"])
            a, b, L, R = (_shown(x) for x in (a, b, it["left"], it["right"]))
            lines.append(f"#{n}:\n  A: {L} [[ {a} ]] {R}\n  B: {L} [[ {b} ]] {R}")
        body = (INSTR + "\n\nItems:\n" + "\n".join(lines) +
                '\n\nAnswer with JSON only, one key per item: {"1": "A" | "B" | "neither", ...}')
        res[order] = page.session(body, sheets, work)
    th = [threading.Thread(target=ask, args=(o,)) for o in ("a", "b")]
    [t.start() for t in th]; [t.join() for t in th]
    out = {}
    for n, it in enumerate(items, 1):
        v = {}
        for order, (first, second) in (("a", ("primary", "oxr")), ("b", ("oxr", "primary"))):
            ans, use, err = res[order]
            if ans is None:
                v[order] = "not judged: " + (err or "no answer")
                continue
            x = str(ans.get(str(n), "")).strip()
            v[order] = first if x == "A" else (second if x == "B" else "neither")
        out[it["id"]] = (v["a"] if v["a"] == v["b"] else
                         ("not judged: judge session failed" if any(x.startswith("not judged") for x in v.values())
                          else "undecided"))
    usage = {o: res[o][1] for o in res}
    (work / "gemini_usage.json").write_text(json.dumps({"items": len(items), "sheets": len(sheets), "usage": usage,
                                                        "errors": {o: res[o][2] for o in res}}, indent=1))
    return out, usage
