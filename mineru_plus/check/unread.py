"""Text only the primary reading has: a second look by jev.

two_readings.compare aligns both readings twice (in order, then the leftovers against what OXR has elsewhere on the
page, tables included). What OXR still did not read has no second reading: figure labels the primary typed into a
caption, captions OXR skipped, passages of pages OXR read in part (10-29, 31 documents: about 1,900 such tokens with
letters or digits, a third of them on two pages of one supplement).

On a page with a text layer each run is placed by the layer: the block's layer words aligned character by character
to the block's text give the words that print the run, one red box per line. jev is asked per line whether the box
prints exactly the primary's text there, in both option orders (its 'yes' is reliable, its 'no' less so: on clean
lines it said no to 36%, 10-29). A run is confirmed when every line gets yes; a run with a line jev reads otherwise,
or undecided, or that the layer cannot place, is an open issue with its crop for the calling agent.
"""
import collections, difflib, hashlib, base64, re
from pathlib import Path
import pymupdf
from ..readers import mineru as MR
from .. import layer as LY
from . import coverage as CV, dropped as DR, two_readings as TR, linebreak as LB, jev

INSTR = DR.INSTR.replace("a thin red box marks some text", "thin red boxes mark some text").replace(
    "inside the red box", "inside the red boxes")


FIG_INSTR = ("The image is a figure from a printed page. Look for the quoted text among the words printed in the figure "
             "(titles, labels, legends). Compare letters and digits; case, spaces and line breaks do not matter.")


def linebreak_subs(pdf_path, mdir, runs):
    """Runs that are a word split at a line end of the layer, which the primary reads one way (with or without the
    hyphen) and OXR the other: the alignment pairs 'pre - dictions' with nothing when OXR has 'predictions', so the run
    looked unread and jev was asked whether the box prints 'pre' (11-02, path2space: 3 of 17 open runs). They are a
    spelling question: returned as disagreements for resolve's line-break route (document usage, then jev spelling),
    with the other spelling as OXR's; the remaining runs are returned as they are."""
    pdf = pymupdf.open(pdf_path)
    A = MR.pages(mdir)
    subs, rest, bks = [], [], {}
    for r in runs:
        pg_no = r["page"]
        alt = None
        if 0 < pg_no <= pdf.page_count and pg_no in A:
            bk = bks.setdefault(pg_no, LB.breaks(LY.page(pdf, pg_no - 1)))
            alt = _other_split(r["text"], bk)
        if alt is None:
            rest.append(r)
            continue
        raw = MR.unit(A[pg_no], r["block"])[1].get("content") or ""
        lo, hi = r["raw_span"]
        left, right = raw[:lo].split()[-8:], raw[hi:].split()[:8]
        subs.append({"kind": "content", "page": pg_no, "blocks": [r["block"]], "bbox": r["bbox"],
                     "block_type": r["block_type"], "pos_in_block": round(lo / max(1, len(raw)), 3),
                     "primary": r["text"], "oxr": alt, "primary_text": r["text"], "oxr_text": alt, "raw_span": [lo, hi],
                     "primary_toks": r["toks"], "oxr_toks": alt.split(), "left": left, "right": right,
                     "context": " ".join(left) + " [...] " + " ".join(right),
                     "source": "a line-break word OXR did not pair (its other spelling stands for OXR's)"})
    return subs, rest


def _other_split(text, bk):
    """the run with the hyphen of a layer line break dropped (it holds 'pre-dictions') or put back (it holds
    'Palisoul'); None when the run holds no split word of the page"""
    for left, right in bk:
        # the next line's word may carry a reference mark ('data-|set3', a superscript 3): its letters are the word
        right = re.match(r"[^\W\d_]*", right or "").group()
        if not (left and right) or not left.isalpha():
            continue
        m = re.search(re.escape(left) + r"\s*[-­‐‑]\s*" + re.escape(right), text)
        if m:
            return text[:m.start()] + left + right + text[m.end():]
        m = re.search(r"(?<!\w)" + re.escape(left + right), text)
        if m:
            return text[:m.start()] + left + "-" + right + text[m.end():]
    return None


def _in_boxes(w, pg, boxes):
    """the layer word's centre lies in one of the normalized boxes"""
    nb = CV._norm_box(pymupdf.Rect(w[:4]) * pg.rotation_matrix, pg)
    return any(CV._inside(((nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2), b) for b in boxes)


def _figure_boxes(page_units, r):
    """normalized boxes of the figure a caption's or note's run belongs to (the page's image blocks and the run's own
    box), or None when the run is not in a figure's caption or note"""
    if "." not in str(r["block"]):
        return None
    if MR.unit(page_units, int(str(r["block"]).split(".")[0]))[0] not in CV.FIGURE:
        return None
    fb = [u[2]["bbox"] for u in MR.units(page_units) if u[1] in CV.FIGURE and u[2].get("bbox")]
    return fb + ([r["bbox"]] if r.get("bbox") else [])


def _block_words(pg, units):
    """layer words of each block (the smallest block whose box holds the word's centre): {uid: [(text, rect, line)]}"""
    got = collections.defaultdict(list)
    for w in LY.words(pg):
        r = pymupdf.Rect(w[:4]) * pg.rotation_matrix
        nb = CV._norm_box(r, pg); c = ((nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2)
        hits = [u for u in units if CV._inside(c, u[2]["bbox"])]
        if hits:
            u = min(hits, key=lambda u: (u[2]["bbox"][2] - u[2]["bbox"][0]) * (u[2]["bbox"][3] - u[2]["bbox"][1]))
            got[u[0]].append((w[4], pymupdf.Rect(w[:4]), (w[5], w[6])))
    return got


def _place(raw, lw, span, free=False):
    """the layer words that print raw[span]: [(line, [rect], (raw lo, raw hi))] per line, or None when fewer than
    nine in ten of its characters align to the layer. The block's text is aligned to the block's words; free: the
    run alone to any words of the page, matched within a stretch little longer than the run (figure labels the
    primary typed into a caption sit in the figure, not in the caption's box: 10-29, 232 of 510 runs)"""
    pm = DR.plain_map(raw)
    L = DR._lay_chars([t for t, _, _ in lw])
    js = [j for j, (_, r) in enumerate(pm) if span[0] <= r < span[1]]
    if not js or not L:
        return None
    p2w, at = {}, {}
    P = [pm[j][0] for j in js] if free else [c for c, _ in pm]
    off = js[0] if free else 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [c for c, _ in L], P, autojunk=False).get_opcodes():
        if op == "equal":
            p2w.update({off + j1 + k: L[i1 + k][1] for k in range(i2 - i1)})
            at.update({off + j1 + k: i1 + k for k in range(i2 - i1)})
    hit = [j for j in js if j in p2w]
    if len(hit) < 0.9 * len(js):
        return None
    if free and max(at[j] for j in hit) - min(at[j] for j in hit) > 1.5 * len(js) + 4:
        return None
    # the boxes hold whole words, so the quoted text is the primary's text of those whole words ('¹Department', not
    # '1'; 10-29: quoting part of a boxed word made jev answer 'not printed')
    ks = {p2w[j] for j in hit}
    lines = {}
    for j, k in p2w.items():
        if k not in ks:
            continue
        t, rect, ln = lw[k]
        e = lines.setdefault(ln, [[], [pm[j][1], pm[j][1] + 1]])
        if rect not in e[0]:
            e[0].append(rect)
        e[1][0], e[1][1] = min(e[1][0], pm[j][1]), max(e[1][1], pm[j][1] + 1)
    return [(ln, rects, tuple(rr)) for ln, (rects, rr) in sorted(lines.items(), key=lambda kv: kv[1][1][0])]


def _crop(page, rects, path, dpi=220):
    """crop around unrotated layer rects, each marked with a thin red box, turned upright"""
    from PIL import Image, ImageDraw
    from .table_layer import _upright
    D = [pymupdf.Rect(r) * page.rotation_matrix for r in rects]
    U = pymupdf.Rect(D[0])
    for r in D[1:]:
        U |= r
    clip = pymupdf.Rect(U.x0 - 40, U.y0 - 14, U.x1 + 40, U.y1 + 14) & page.rect
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    z = dpi / 72
    for r in D:
        ImageDraw.Draw(im).rectangle([(r.x0 - clip.x0 - 1.5) * z, (r.y0 - clip.y0 - 1.5) * z,
                                      (r.x1 - clip.x0 + 1.5) * z, (r.y1 - clip.y0 + 1.5) * z], outline=(255, 0, 0), width=2)
    U0 = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        U0 |= pymupdf.Rect(r)
    rot = _upright(page, U0)
    if rot:
        im = im.rotate(rot, expand=True)
    im.save(path)
    return path


def check(pdf_path, mdir, runs, layer_pages, work):
    """runs: two_readings.compare's unread runs. Returns (runs with verdicts, issues, counts)."""
    pdf = pymupdf.open(pdf_path)
    A = MR.pages(mdir)
    work = Path(work); (work / "crops").mkdir(parents=True, exist_ok=True)
    n = collections.Counter()
    qs, units_of, words_of = [], {}, {}
    runs = [r for r in runs if any(c.isalnum() for c in r["text"])]
    for k, r in enumerate(runs):
        n["runs"] += 1; n["tokens"] += len(r["toks"])
        pg_no = r["page"]
        if pg_no not in layer_pages:
            r["verdict"] = "page without a text layer"; continue
        pg = LY.page(pdf, pg_no - 1)
        if pg_no not in words_of:
            units = [(uid, t, p) for uid, t, p in MR.units(A[pg_no]) if p.get("bbox")]
            words_of[pg_no] = _block_words(pg, units)
        raw = MR.unit(A[pg_no], r["block"])[1].get("content") or ""
        short = sum(c.isalnum() for c in r["text"]) < 4
        own = words_of[pg_no].get(r["block"], [])
        placed = _place(raw, own, r["raw_span"])
        # a caption's or note's run that is not in its own box's words is looked for in the figure (its image blocks and
        # the run's own box), not anywhere on the page: a panel letter 'C' or title 'Chemotherapy' read from a picture
        # otherwise lands on '(C)' or 'chemotherapy' in the caption's sentences (11-02, path2space: 8 of 17 open runs)
        figs = _figure_boxes(A[pg_no], r)
        pool = [w for w in LY.words(pg) if figs is None or _in_boxes(w, pg, figs)]
        if not placed and not short:     # a panel letter matches anywhere on the page: only longer runs go free
            placed = _place(raw, [(w[4], pymupdf.Rect(w[:4]), (w[5], w[6])) for w in pool], r["raw_span"], True)
        if not placed and short:
            # a short label (panel letter 'B', 'a.'): placed at the one word of the layer that is it
            key = "".join(c for c in r["text"] if c.isalnum())
            hits = [w for w in pool if "".join(c for c in w[4] if c.isalnum()) == key]
            if len(hits) == 1:
                w = hits[0]
                rr = r["raw_span"]
                placed = [((w[5], w[6]), [pymupdf.Rect(w[:4])], (rr[0], rr[1]))]
        if not placed:
            r["verdict"] = "not placed by the text layer"
            # a caption or note of a figure holding text the layer does not have or has more than once (the figure
            # is a picture, or panel letters): jev looks for it in the figure
            parent = str(r["block"]).split(".")[0]
            if "." in str(r["block"]):
                ptyp, pb = MR.unit(A[pg_no], int(parent))
                # all figure blocks of the page: the reader splits a figure into panels and a caption's words may sit
                # in a neighbouring panel (10-29: 'D', 'A MRI-based ...' not in the caption's own block)
                fb = [u[2]["bbox"] for u in MR.units(A[pg_no]) if u[1] in CV.FIGURE and u[2].get("bbox")]
                if ptyp in CV.FIGURE and fb:
                    W, H = pg.rect.width, pg.rect.height
                    # a box of its own that holds no layer word: the reader read the run from a picture right there (a
                    # panel title or letter it set apart from the image blocks, which the union of those leaves out;
                    # 11-02, path2space: 6 of 17 open runs), so that box is the crop
                    bx = [r["bbox"]] if r.get("bbox") and not own else fb + ([r["bbox"]] if r.get("bbox") else [])
                    pad = 8 if len(bx) == 1 else 0
                    clip = pymupdf.Rect(min(b[0] for b in bx) * W - pad, min(b[1] for b in bx) * H - pad,
                                        max(b[2] for b in bx) * W + pad, max(b[3] for b in bx) * H + pad) & pg.rect
                    if not clip.is_empty:
                        dpi = max(72, min(220, int(2200 * 72 / max(clip.width, clip.height))))
                        crop = work / "crops" / f"f{pg_no}.{r['block']}.{k}.png"
                        pg.get_pixmap(dpi=dpi, clip=clip).save(str(crop))
                        t = r["text"].strip()
                        qid = f"f{pg_no}.{r['block']}.{k}"
                        img = "data:image/png;base64," + base64.b64encode(open(crop, "rb").read()).decode()
                        qs.append({"id": qid, "state": f"Quoted text: «{t}»", "instructions": FIG_INSTR, "images": [img],
                                   "options": {"printed": f"The figure prints the text «{t}» somewhere, with these letters",
                                               "not printed": f"The figure does not print the text «{t}»"}})
                        r["in_figure"] = {"id": qid, "text": t, "crop": str(crop)}
            continue
        text, idx = TR.printed_map(raw)
        r["lines"] = []
        for m, (ln, rects, (lo, hi)) in enumerate(placed):
            t = "".join(c for c, i in zip(text, idx) if lo <= i < hi).strip()
            if not t:
                continue
            crop = _crop(pg, rects, work / "crops" / f"u{pg_no}.{r['block']}.{k}.{m}.png")
            qid = f"u{pg_no}.{r['block']}.{k}.{m}"
            img = "data:image/png;base64," + base64.b64encode(open(crop, "rb").read()).decode()
            qs.append({"id": qid, "state": f"Quoted text: «{t}»", "instructions": INSTR, "images": [img],
                       "options": {"printed": f"The red boxes show exactly «{t}»",
                                   "not printed": f"The red boxes show something different from «{t}»"}})
            r["lines"].append({"id": qid, "text": t, "crop": str(crop)})
    v = jev.ask(qs, work, "unread") if qs else {}
    issues = []
    for r in runs:
        if "in_figure" in r:
            x = r["in_figure"]; x["verdict"] = v.get(x["id"], "not judged")
            r["verdict"] = {"printed": "printed in the figure", "not printed": "not printed"}.get(x["verdict"], "undecided")
            r["lines"] = [x]
        elif "lines" in r:
            vs = [v.get(x["id"], "not judged") for x in r["lines"]]
            for x, y in zip(r["lines"], vs):
                x["verdict"] = y
            r["verdict"] = ("printed" if vs and all(y == "printed" for y in vs) else
                            "not printed" if "not printed" in vs else "undecided")
        n[r["verdict"]] += 1; n["tokens " + r["verdict"]] += len(r["toks"])
        if r["verdict"] not in ("printed", "printed in the figure"):
            # the run in its block's text, so a short run ('x') can be told from others like it (11-03, PTA-09/11)
            raw = MR.unit(A[r["page"]], r["block"])[1].get("content") or ""
            s0, e0 = r.get("raw_span") or (0, 0)
            issues.append({"kind": "text only the primary read", "page": r["page"], "block": r["block"],
                           "block_type": r["block_type"], "text": r["text"], "verdict": r["verdict"],
                           "context": raw[max(0, s0 - 60):s0] + "[[" + raw[s0:e0] + "]]" + raw[e0:e0 + 60],
                           "crops": [x["crop"] for x in r.get("lines", [])],
                           "lines": [{"text": x["text"], "verdict": x["verdict"]} for x in r.get("lines", [])]})
    return runs, issues, dict(n)
