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


def _rect(pg, hit, block):
    """the line of the hit and the next one (a word split at the line end continues there), across the block's
    column so the passage is not cut at the sides"""
    lh = hit.y1 - hit.y0
    narrow = block is not None and block.width < 0.6 * pg.rect.width
    x0, x1 = (block.x0 - 4, block.x1 + 4) if narrow else (hit.x0 - 160, hit.x1 + 160)
    return pymupdf.Rect(x0, hit.y0 - 0.4 * lh, x1, hit.y1 + 1.4 * lh) & pg.rect


def _crop(doc, page, bbox, toks, path, pos=None):
    """Crop around the passage. Candidate places come from searching the text layer (passage with left context, the
    passage, its longest words); a candidate is accepted when the layer words inside it contain the left context and
    the passage (the primary reading copies the layer), a check that needs no judge. Returns (path, how it was placed or None)."""
    pg = LY.page(doc, page - 1)
    W, H = pg.rect.width, pg.rect.height
    block = pymupdf.Rect(bbox[0] * W, bbox[1] * H, bbox[2] * W, bbox[3] * H) * pg.derotation_matrix if bbox else None
    left, prim = toks.get("left", []), toks.get("primary", [])
    right, alt = toks.get("right", []), toks.get("oxr", [])
    # the layer holds the passage as one of the two readings (the primary copies it; where the primary is the wrong
    # side, the layer reads like OXR)
    wants = []
    for p in (prim, alt):
        w = [_letters(t) for t in left[-2:] + p if len(_letters(t)) > 1]
        if not [t for t in p if len(_letters(t)) > 1]:      # passage of signs only: its words around it place it
            w = [_letters(t) for t in left[-2:] + right[:2] if len(_letters(t)) > 1]
        if w:
            wants.append(w)
    tries = [" ".join(left[-2:] + prim[:2]), " ".join(left[-1:] + prim[:1]), " ".join(prim)]
    if alt:
        tries += [" ".join(left[-2:] + alt[:2]), " ".join(alt)]
    tries += [" ".join(left[-2:]), " ".join(right[:2])]
    tries += sorted([t for t in prim + left[-2:] if len(t) >= 3], key=len, reverse=True)[:3]
    first, chosen = None, None
    for t in tries:
        t = t.strip()
        if len(t) < 2:
            continue
        for clip in ([block, None] if block else [None]):
            for hit in (pg.search_for(t, clip=clip) if clip else pg.search_for(t)):
                r = _rect(pg, hit, block)
                first = first or r
                inside = _letters("".join(w[4] for w in LY.words(pg, r)))
                if any(all(x in inside for x in w) for w in wants):
                    chosen = r; break
            if chosen:
                break
        if chosen:
            break
    r = chosen
    how = "text layer" if chosen else None
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
    if r.is_empty or r.width < 4 or r.height < 4:      # nothing locatable: the page, scaled down
        pg.get_pixmap(dpi=100).save(str(path))
        return str(path), None
    pg.get_pixmap(dpi=300, clip=r).save(str(path))
    return str(path), how


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
            img = "data:image/png;base64," + base64.b64encode(pg.get_pixmap(dpi=170, clip=r).tobytes("png")).decode()
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


def judge(pdf, items, work):
    """items: [{id, page, bbox, left, right, primary, oxr, toks}] -> ({id: 'primary'|'oxr'|'neither'|'undecided'|
    'not judged: ...'}, crop paths, usage)"""
    if not items:
        return {}, {}, {}
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    made = {it["id"]: _crop(doc, it["page"], it["bbox"], it["toks"], work / "crops" / f"{it['id']}.png", it.get("pos"))
            for it in items}
    crops = {k: v[0] for k, v in made.items()}
    verified = {k: v[1] for k, v in made.items()}
    for iid, (pg, r) in _jev_place(doc, items, {k for k, v in verified.items() if v != "text layer"}, work).items():
        pg.get_pixmap(dpi=300, clip=r).save(crops[iid])
        verified[iid] = "jev"
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
                                                        "crops_placed_by": dict(__import__("collections").Counter(
                                                            v or "not placed" for v in verified.values())),
                                                        "errors": {o: res[o][2] for o in res}}, indent=1))
    return out, {k: {"path": crops[k], "placed_by": verified[k] or "not placed"} for k in crops}, usage
