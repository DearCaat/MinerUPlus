"""Settle each content disagreement of the two readings.

  line-break hyphen   the readings differ only by a hyphen that sits at a line break of the text layer. The page prints
                      a hyphen either way, so the question is spelling: first how this document writes the word where
                      it is not split (mid-line words of its text layer), then jev on the passage in both spellings.
                      10-28, 110 items labelled by usage: jev decided 109, 108 right (d3-ultra; its one error went
                      against the paper's own usage, which is why usage comes first).
  characters          jev first: per reading, whether the crop prints exactly that reading (_jev_exact); what it
                      does not decide, Gemini looks at a tight crop of the passage and chooses the reading the page prints, or neither,
                      in both option orders (check/gemini.py). jev and deepseek-flash were replaced 10-28: both chose
                      the correct spelling where the page prints a typo (25-40% of decided printed-typo items wrong).
  omission            the text layer and OXR both have a run the primary dropped (check/omissions.py): written as the
                      layer prints it, no judge (two readings against one).
Disagreements in spacing or markup only are not judged (form, not content).
"""
import base64, re, unicodedata
from pathlib import Path
import pymupdf
from . import jev, gemini, linebreak as LB, two_readings as TR
from .. import layer as LY

CHAR_INSTR = ("The image is part of one page of a scientific paper. Two programs read the same passage of this page and "
              "disagree at the place marked with [[ ]]. Find that passage in the image and compare the marked words "
              "character by character: letters, digits, decimal points, commas, minus signs, superscripts and "
              "subscripts. Case, spaces and line breaks do not matter. Choose the reading that matches what the page "
              "prints there. If the page prints neither, choose neither.")
PURE_MARKUP = re.compile(r"[$^{}_\\]+")
SPELL_INSTR = "Which version of this passage is spelled correctly?"


def _detok(ts):
    s = " ".join(ts)
    return re.sub(r"\s+([,.;:)\]])", r"\1", re.sub(r"([(\[])\s+", r"\1", s))


def _crop(doc, page, bbox, pad=24, dpi=170):
    pg = LY.page(doc, page - 1)
    W, H = pg.rect.width, pg.rect.height
    r = (pymupdf.Rect(bbox[0] * W - pad, bbox[1] * H - pad, bbox[2] * W + pad, bbox[3] * H + pad) & pg.rect) if bbox else pg.rect
    return "data:image/png;base64," + base64.b64encode(pg.get_pixmap(dpi=dpi, clip=r).tobytes("png")).decode()


def _layer_says(pg, s, exact=False):
    """the reading the page's text layer holds after two words of left context: 'primary', 'oxr' or None. exact:
    every printed character counts (dashes, signs), only spaces are dropped; else letters and digits"""
    f = (lambda x: re.sub(r"\s", "", unicodedata.normalize("NFC", x))) if exact else gemini._letters
    lay = f(LY.text(pg))
    ctx = "".join(f(t) for t in s["left"][-2:])
    hp = ctx + f(s["primary"]) in lay
    ho = ctx + f(s["oxr"]) in lay
    return "primary" if hp and not ho else "oxr" if ho and not hp else None


def _layer_words_say(pg, s):
    """the reading whose words all are words of the page's layer while the other's are not (the context of two words
    may not be in the layer as it runs: a caption read in another order; 10-29, 'Value for AI' in one supplement)"""
    ws = set(TR.toks(LY.text(pg)))
    hp = all(w in ws for w in TR.toks(s["primary"]))
    ho = all(w in ws for w in TR.toks(s["oxr"]))
    return "primary" if hp and not ho else "oxr" if ho and not hp else None


_DOC_TOKS = {}


def _doc_words_say(doc, s):
    """where the page's layer holds neither (a figure drawn as paths): the reading whose differing words the
    document's layer prints elsewhere while it never prints the other's, as the document's usage decides a
    line-break hyphen (10-29: 'AI' 86 times in one supplement's layer, 'Al' never; a figure page has neither)"""
    if doc.name not in _DOC_TOKS:
        _DOC_TOKS[doc.name] = set(TR.toks(" ".join(LY.text(p) for p in doc)))
    ws = _DOC_TOKS[doc.name]
    a, b = TR.toks(s["primary"]), TR.toks(s["oxr"])
    a, b = [w for w in a if w not in b], [w for w in b if w not in a]
    if not a or not b:
        return None
    hp, ho = all(w in ws for w in a), all(w in ws for w in b)
    return "primary" if hp and not ho else "oxr" if ho and not hp else None


EXACT_INSTR = ("The image is a strip cut from a printed page. Compare the quoted text with the printed text in the image "
               "character by character: every letter, its order, digits, punctuation, symbols. The page may contain "
               "typing errors; judge what is printed, do not correct it.")


def _jev_exact(items, placed, work):
    """jev first (10-29: judgements prefer jev): per reading, 'does the crop print exactly X?' in both option
    orders, on the crops gemini.place() checked. Decided when one reading gets yes and the other no; the rest goes
    to Gemini. 10-29, 106 labelled items: 74 decided, 1 wrong; asking jev to choose between the two readings instead
    picked the correctly spelled one where the page prints a typo (25-40% wrong)."""
    qs = []
    for it in items:
        img = "data:image/png;base64," + base64.b64encode(open(placed[it["id"]]["path"], "rb").read()).decode()
        for side in ("primary", "oxr"):
            t = it[side]
            qs.append({"id": f"{it['id']}|{side}", "state": f"Quoted text: «{t}»", "instructions": EXACT_INSTR,
                       "images": [img], "options": {"yes": f"The image prints exactly «{t}»",
                                                    "no": f"The image does not print «{t}» exactly; what is printed differs"}})
    v = jev.ask(qs, work, "exact") if qs else {}
    out = {}
    for it in items:
        a, b = v.get(f"{it['id']}|primary"), v.get(f"{it['id']}|oxr")
        if a == "yes" and b == "no":
            out[it["id"]] = "primary"
        elif a == "no" and b == "yes":
            out[it["id"]] = "oxr"
    return out


def _drops_letters(s):
    """OXR's letters and digits are a proper subsequence of the primary's"""
    a = [c for c in s["primary"] if c.isalnum()]
    b = [c for c in s["oxr"] if c.isalnum()]
    if len(b) >= len(a):
        return False
    it = iter(a)
    return all(c in it for c in b)


def settle(pdf, subs, work):
    work = Path(work)
    doc = pymupdf.open(pdf)
    usage_idx = LB.midline_index([doc])
    breaks = {}
    spell_q, char_q = [], []
    for i, s in enumerate(subs):
        s["id"] = f"d{i:04d}"
        if s["kind"] == "repeat count":
            # vision judges miscount runs of one character (10-28: Gemini read '3200003' as '320003' in both orders);
            # the text layer decides, and where it holds neither reading the item goes to the caller
            s["route"], s["by"] = "characters", "text layer (repeated character)"
            s["verdict"] = _layer_says(LY.page(doc, s["page"] - 1), s) or "undecided"
            continue
        if s["kind"] == "look-alike":
            # characters drawn alike: the image cannot decide, the text layer can; where it holds neither reading
            # (no layer, or the alignment fails) the primary's stays
            pg = LY.page(doc, s["page"] - 1)
            says = _layer_says(pg, s, exact=True) or _layer_words_say(pg, s) or _doc_words_say(doc, s)
            if says:
                s["route"], s["by"], s["verdict"] = "characters", "text layer (look-alike characters)", says
            else:
                s["route"], s["verdict"], s["by"] = "form only", "no action", "look-alikes the text layer does not decide"
            continue
        if s["kind"] != "content":
            s["route"], s["verdict"] = "form only", "no action"
            continue
        if TR.cross_script(s["primary"], s["oxr"]):     # letters of another script: the text layer decides
            says = _layer_says(LY.page(doc, s["page"] - 1), s)
            if says:
                s["route"], s["by"], s["verdict"] = "characters", "text layer (letters of another script)", says
                continue
        bk = breaks.setdefault(s["page"], LB.breaks(LY.page(doc, s["page"] - 1)))
        hit = LB.is_linebreak(s, bk)
        if not hit and s.get("source") == "text layer and OXR":
            s["route"], s["verdict"], s["by"] = "omission", "layer", "text layer and OXR"
            continue
        if hit:
            left, right, full = hit
            s["route"], s["split"] = "line-break hyphen", f"{left}-|{right}"
            u = LB.usage(full, right, usage_idx)
            s["usage"] = u
            if u["hyphen"] and not u["joined"]:
                s["verdict"], s["by"] = "hyphen", "document usage"
            elif u["joined"] and not u["hyphen"]:
                s["verdict"], s["by"] = "joined", "document usage"
            else:
                L, R = _detok(s["left"])[-120:], _detok(s["right"])[:120]
                spell_q.append({"id": s["id"], "state": "A passage of a scientific paper.", "instructions": SPELL_INSTR,
                                "options": {"hyphen": f"The paper reads: {L} {left}-{right} {R}",
                                            "joined": f"The paper reads: {L} {left}{right} {R}"}})
                s["by"] = "jev spelling"
            continue
        s["route"], s["by"] = "characters", "gemini page"
        # tokens that are pure markup ($ { } ^ _ \) are not printed: drop them from both readings before asking
        s["primary_toks"] = [t for t in s["primary_toks"] if not PURE_MARKUP.fullmatch(t)] or s["primary_toks"]
        s["oxr_toks"] = [t for t in s["oxr_toks"] if not PURE_MARKUP.fullmatch(t)] or s["oxr_toks"]
        # the judges see each reading as it prints, with its own spacing (two_readings.printed_map)
        s["primary_shown"] = (s.get("primary_text") or " ".join(s["primary_toks"])).strip()
        s["oxr_shown"] = (s.get("oxr_text") or " ".join(s["oxr_toks"])).strip()
        if s["primary_shown"] == s["oxr_shown"]:
            s["route"], s["verdict"], s["by"] = "form only", "no action", "markup tokens only"
            continue
        char_q.append({"id": s["id"], "page": s["page"], "bbox": s["bbox"], "pos": s.get("pos_in_block"), "left": " ".join(s["left"][-6:]),
                       "right": " ".join(s["right"][:6]), "primary": s["primary_shown"], "oxr": s["oxr_shown"],
                       "toks": {"left": [t for t in s["left"] if not PURE_MARKUP.fullmatch(t)][-3:],
                                "primary": s["primary_toks"], "oxr": s["oxr_toks"],
                                "right": [t for t in s["right"] if not PURE_MARKUP.fullmatch(t)][:3]}})
    ans = jev.ask(spell_q, work, "spelling")
    bys = {}
    # one crop per passage, checked by jev to show the passage whole; a passage no crop shows is not judged
    placed = gemini.place(pdf, char_q, work / "crops")
    shown = [q for q in char_q if placed[q["id"]]["checked"]]
    jans = _jev_exact(shown, placed, work / "jev_exact")
    # a spelling difference (letters only) that jev settles against the text layer goes to Gemini: jev took the
    # common spelling for the print (10-29: 'Interpetation' printed, 'biomedcentral' printed); where the layer
    # holds neither reading or agrees, jev's verdict stands
    by_id = {s["id"]: s for s in subs}
    for k in list(jans):
        s = by_id[k]
        if all(re.fullmatch(r"[A-Za-z*\- ]+", s[x + "_shown"]) for x in ("primary", "oxr")):
            says = _layer_says(LY.page(doc, s["page"] - 1), s)
            if says and says != jans[k]:
                del jans[k]
    gans, _ = gemini.judge(pdf, [q for q in shown if q["id"] not in jans], work / "gemini", placed)
    for q in char_q:
        if not placed[q["id"]]["checked"]:
            ans[q["id"]] = "not judged: no crop shows the passage whole"
    for k in jans:
        bys[k] = "jev (exactly printed)"
    ans.update(jans)
    ans.update(gans)
    for s in subs:
        if s["id"] in ans:
            s["verdict"] = ans[s["id"]]
        # OXR leaves words out; where its reading only lacks letters or digits the primary has and the text layer
        # prints them there, the judge's 'OXR' came from something else (10-29: 'thecount' against 'the', jev saying
        # the crop prints exactly 'the' because the primary lacks a space): the layer and the primary stand
        if s.get("verdict") == "oxr" and s.get("route") == "characters" and _drops_letters(s) and \
                _layer_says(LY.page(doc, s["page"] - 1), s) == "primary":
            s["verdict"], s["by"] = "primary", "text layer (OXR only lacks letters the layer prints)"
            bys.pop(s["id"], None)
        # a spelling difference where the vision judges read OXR's spelling and the text layer prints the primary's:
        # both judges take the common spelling for the print (10-29, held-out paper: 'microevironment' printed and in
        # the layer, jev and Gemini both read 'microenvironment'); judges against the layer settle nothing. Case alone
        # is not spelling (small capitals: the layer has 'url', the page shows 'URL')
        if s.get("verdict") == "oxr" and s.get("route") == "characters" and \
                not s.get("by", "").startswith("text layer") and \
                all(re.fullmatch(r"[A-Za-z*\- ]+", s.get(x + "_shown") or "") for x in ("primary", "oxr")) and \
                (s.get("primary_shown") or "").lower() != (s.get("oxr_shown") or "").lower() and \
                _layer_says(LY.page(doc, s["page"] - 1), s) == "primary":
            s["verdict"], s["by"] = "undecided", "vision judges against the text layer (spelling)"
            bys.pop(s["id"], None)
        if s["id"] in bys:
            s["by"] = bys[s["id"]]
        if s["id"] in placed:
            s["crop"], s["crop_placed_by"] = placed[s["id"]]["path"], placed[s["id"]]["placed_by"]
            s["crop_checked"] = placed[s["id"]]["checked"]
    return subs
