"""mineru_plus parse: one PDF in, one output directory out.

  out/profile.json            counts read from the PDF per page (words, images, unusual glyphs)
  out/readers/mineru/         primary reader output, untouched (primary reading)
  out/readers/oxr/            OXR output, untouched (independent visual reading)
  out/full.md                 the parse: primary reading, figure transcriptions moved out, settled disagreements written in
  out/figures.json            the reader's transcriptions of figures and charts, with how much of each is printed text
  out/checks/                 disagreements of the two readings with their route, verdict and plan; jev requests
  out/issues.json             what the run could not settle, for the calling agent
  out/report.json, report.md  the quality statement of this run
"""
import argparse, collections, difflib, json, re, shutil, sys, tempfile, time, threading
import pymupdf
from pathlib import Path
from . import profile as PR, repair as RP, margins as MG
from .readers import mineru as MR, oxr as OX
from .check import unread as UR, dropped as DR, reflow as RF, table_layer as TL, omissions as OM, two_readings as TR, resolve as RS, coverage as CV, tables as TB, equations as EQ
from . import layer as LY, sections as SC, backends, config

VERSION = "0.5.5"
DETAILS = re.compile(r"<details>.*?</details>\n*", re.S)   # how MinerU's markdown wraps a figure transcription
TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.,][0-9]+)*")
WS = re.compile(r"\s+")
MERMAID_LABEL = re.compile(r'"([^"]*)"')
MEASURED_WITH = {   # the setup the CALIBRATION numbers were measured with (10-28 and 10-29), per role
    "primary_reader": {"backend": "gateway", "tool": "mineru", "tier": "advanced"},    # MinerU 4.1 V1 API
    "second_reader": {"backend": "gateway", "tool": "oxr"},
    "decision_judge": {"backend": "gateway", "model": "d3-ultra"},                    # jev
    "page_judge": {"backend": "agy", "model": "gemini-3.8-flash-high"},                # through the agy CLI
}
CALIBRATION = {   # tool-level measurements behind the checks; per-document numbers are in "checks"
    "readers independent of the text layer (10-28, planted hidden layer, 73 numbers)":
        "MinerU advanced copies the layer on born-digital pages (48 layer / 0 image in text blocks); OXR reads the image (51 / 0)",
    "character check recall (10-28, 216 planted text-layer errors on 18 pages of 9 papers)":
        "in compared text 191 surfaced as disagreements but 3; jev chose the printed side for 182, 0 wrong; headers, footers, "
        "page numbers, equations not compared (12). Only errors on the layer side were planted, so this does not measure "
        "pages that print a typo",
    "character judge (10-28, 106 items: 34 printed typos with an ordinary layer, 12 real, 60 planted layer errors)":
        "Gemini on numbered sheets of tight crops, both option orders: 0 wrong among decided; undecided 9/34, 4/12, 5/60 "
        "(undecided items are open issues with their crop). jev and deepseek-flash chose the corrected spelling of "
        "printed typos in 25-40% of decided cases and are not used for characters",
    "jev first for characters (10-29, 31 documents, 325 character items)":
        "jev asked per reading whether the crop prints exactly it decided 104; where Gemini (0.3.0) had decided the same "
        "item, 84 of 86 agree; the 2 others are printed spellings jev took for the common one ('Interpetation', "
        "'biomedcentral'), so a letters-only difference jev settles against the text layer goes to Gemini",
    "second reader (10-29, 203 planted errors on 9 papers)": "OXR found 187, MiniCPM-OCR 186, both together 188: one "
        "second reader is enough; jev alone on lines (no second reader) rejected 36% of correct lines, so one is needed",
    "dropped content (10-29, 9 papers)": "jev on red-box crops 'prints exactly «layer words»': 101 findings labelled on "
        "the page, 95 decided, 3 wrong; written only where the primary's own characters around place it (49 written, "
        "checked on crops; one wrong, a fraction's denominator written into the next line, led to the same-line rule)",
    "inline formulas (10-29, 31 documents)": "MinerU reads inline $...$ from the image even on born-digital pages: "
        "30 misread formulas ('pm' for 'µm', 'ANN' for 'ANC', 'M×ED' for 'MIXED', 'I56' for '156', 'X^2' for a printed "
        "'χ2') retyped from the layer with raised and lowered glyphs as <sup>/<sub>, only where every difference inside "
        "is a printed finding; doubtful ones checked on the page, all right. Stacked scripts, fractions and roots are "
        "not retyped",
    "reading order (10-29, 9 papers, about 120 pages checked on page images)": "block order wrong at 2 places, both at "
        "figures (a caption split over two columns; body text typed as a figure note); sentences cut by page or column "
        "breaks, with floats between, joined by jev: of 240 joins in 31 documents the 44 with an upper-case "
        "continuation all right, 25 sampled lower-case ones all right; one wrong join (a heading typed as text) led to "
        "the rule that only a paragraph skips blocks",
    "OXR (10-28)": "OXR itself corrects about half of printed letter typos and turns middle dots into periods; where both "
                   "readings agree on a corrected form nothing is flagged",
    "line-break spelling (10-28, 110 items labelled by document usage)": "jev decided 109, 108 right",
    "text-layer coverage, equations (10-28, 9 papers)":
        "coverage found the dropped italic journal names in page footers (2 papers); 8 display equations all agree "
        "with OXR after canonical LaTeX. 10-29, 31 documents: 29 display equations (pathology papers have few), 18 "
        "equal OXR, 1 differed by a tag only, 10 figure labels OXR did not read; rendering both readings for a visual "
        "judge was not built for so few",
    "tables (10-29, 87 tables of 31 documents on pages with a text layer)":
        "MinerU's cells aligned to the layer's characters (99.4% in content-stream order); differences were look-alikes "
        "(533: ✘ written ×, ✔ ✓, – -, · .), a cell's lines glued (206), 3 misread words ('tisse'); jev took MinerU's "
        "'tisse' for printed, so OXR's table decides first. Cell swaps planted in 84 tables (168, a cell with its right or lower neighbour) found 161. "
        "The earlier comparison of structure with OXR was mostly noise (OXR splits multi-line cells; 'F 1' vs 'F1')",
    "real-page edits (10-28, 31 documents: 9 papers, 15 supplements, 7 new papers incl. a 6-page scan)":
        "47 character edits checked on the page image: all right after two rules taken from Gemini's errors "
        "(I/l and O/0 are not judged: same glyph in sans-serif; runs of one repeated character, '3200003', are decided "
        "by the text layer: Gemini miscounted in both orders); 200 line-break spellings, one partial ('dual- and')",
    "omissions (10-28, same 31 documents)":
        "10 runs the text layer and OXR both have between the same three neighbours on each side and the primary "
        "dropped ('vs', compound hyphens, a period, an em dash); requiring only the two anchors let one wrong run in "
        "on a page whose layer runs in another order",
    "text-layer coverage (10-28, 9 papers, 180 findings checked by hand)":
        "about two thirds are content the primary dropped (journal names in footers, citation superscripts, a rotated "
        "table caption, 'vs', brackets inside formulas); the rest are pages whose layer is wrong (font maps such as "
        "'0:05' for 0.05, radical glyphs), which coverage cannot tell apart",
}


def _settled_later(md, subs, issues):
    """open disagreements a later step settled: full.md now prints OXR's reading between the same neighbours and no
    longer the primary's"""
    T = []
    for para in md.split("\n\n"):
        T += [m.group(0) for m in TR.TOK.finditer(TR.printed_map(para)[0])]
    pos = collections.defaultdict(list)
    for i, t in enumerate(T):
        pos[t].append(i)
    has = lambda q: bool(q) and any(T[i:i + len(q)] == q for i in pos.get(q[0], []))
    by = {s["id"]: s for s in subs}
    keep, n = [], 0
    for x in issues:
        s = by.get(x.get("id")) if x["kind"] == "disagreement" else None
        if s:
            L, R = s["left"][-3:], s["right"][:3]
            if has(L + s["oxr_toks"] + R) and not has(L + s["primary_toks"] + R):
                s["settled_later"] = True; n += 1
                continue
        keep.append(x)
    return keep, n


def _printed_share(pdf, fig):
    """Tokens of a transcription that are printed in the text layer inside the figure box (bbox is page-normalised)."""
    pg = LY.page(pdf, fig["page"] - 1)
    x0, y0, x1, y1 = fig["bbox"]
    W, H = pg.rect.width, pg.rect.height
    words = LY.words(pg, pymupdf.Rect(x0 * W, y0 * H, x1 * W, y1 * H))
    layer = {}
    for w in words:
        for t in TOKEN.findall(w[4]):
            layer[t] = layer.get(t, 0) + 1
    text = fig["text"]
    if text.lstrip().startswith("```mermaid"):      # only the quoted labels are content; node ids and arrows are syntax
        text = " ".join(MERMAID_LABEL.findall(text))
    toks = TOKEN.findall(text)
    found = 0
    for t in toks:
        if layer.get(t, 0) > 0:
            layer[t] -= 1
            found += 1
    return {"text_layer_words_in_box": len(words), "tokens": len(toks), "tokens_printed": found}


def substitution_groups(subs):
    """Character disagreements grouped by what changes (layer character -> OXR character). A broken font map
    repeats one substitution across the document (mako: ':' for '.'); a printed typo is a single case. Counts only."""
    groups = collections.defaultdict(list)
    for s in subs:
        if s.get("route") != "characters":
            continue
        a, b = " ".join(s["primary_toks"]), " ".join(s["oxr_toks"])
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op != "equal":
                groups[(a[i1:i2], b[j1:j2])].append({"id": s["id"], "page": s["page"], "primary": a, "oxr": b,
                                                     "verdict": s.get("verdict")})
    return [{"layer": k[0], "oxr": k[1], "count": len(v), "examples": v[:5]}
            for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]


def _coverage(pdf, mdir, edits):
    r = CV.check(pdf, mdir, edits)
    issues = []
    for f in r["repeated"]:
        issues.append({"kind": "text layer not in the parse", "repeated_on_pages": f["pages"], "missing": f["missing"],
                       "note": "the same characters missing on every listed page (running header or footer)"})
    for pg in r["pages"]:
        for f in pg["findings"]:
            issues.append({"kind": "text layer not in the parse", "page": pg["page"], **f})
    t = r["totals"]
    return ({**t, "summary": f"{t.get('missing_chars', 0)} text-layer characters missing from their block "
                             f"({len(r['repeated'])} repeated on many pages counted per page), "
                             f"{t.get('outside_words', 0)} layer words in no block, of {t.get('layer_words', 0)} layer words; "
                             f"{t.get('written_as_ascii', 0)} dashes or middle dots written as ASCII look-alikes "
                             f"(line-break hyphens, invisible characters, figure-internal text and repaired characters excluded)"},
            issues)


def _tables(pdf, mdir, odir, out, done):
    """tables the text layer did not check (pages without a layer, or no layer words in the box): MinerU against OXR"""
    res = [t for t in TB.check(pdf, mdir, odir) if (t["page"], t["block"]) not in done]
    doc = pymupdf.open(pdf)
    (out / "checks" / "crops").mkdir(parents=True, exist_ok=True)
    issues, chars_ok, struct_ok = [], 0, 0
    for t in res:
        L, O = t["layer"], t["oxr"]
        bad_chars = bool(L and L["chars_mineru_not_on_layer"])
        bad_struct = bool(O and O["diffs"])
        chars_ok += bool(L) and not bad_chars
        struct_ok += bool(O) and not bad_struct
        if not (bad_chars or bad_struct or L is None or O is None):
            continue
        pg = LY.page(doc, t["page"] - 1); W, H = pg.rect.width, pg.rect.height; b = t["bbox"]
        crop = out / "checks" / "crops" / f"table_p{t['page']}_b{t['block']}.png"
        pg.get_pixmap(dpi=150, clip=pymupdf.Rect(b[0] * W, b[1] * H, b[2] * W, b[3] * H)).save(str(crop))   # displayed page
        issues.append({"kind": "table", "page": t["page"], "block": t["block"], "crop": str(crop),
                       "characters_not_on_layer": L["chars_mineru_not_on_layer"] if L else "no text layer in the box",
                       "layer_characters_missing": L["chars_layer_not_in_mineru"] if L else None,
                       "structure_vs_oxr": (O["diffs"][:40] if O else "no OXR table matched"),
                       "shape_mineru_oxr": ({"rows": O["rows"], "cols": O["cols"]} if O else None)})
    (out / "checks" / "tables_oxr.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return ({"tables": len(res), "structure_equal_oxr": struct_ok,
             "summary": f"{len(res)} tables without text-layer words in their box: rows and cells equal OXR in "
                        f"{struct_ok}; the rest are open issues with a crop"}, issues)


def _equations(pdf, mdir, odir, layer_pages):
    res = EQ.check(mdir, odir, pdf, layer_pages)
    ok = ("same", "characters equal the text layer")
    issues = [{"kind": "display equation", **e} for e in res if e["status"] not in ok]
    same = sum(e["status"] == "same" for e in res)
    lay = sum(e["status"] == ok[1] for e in res)
    return ({"equations": len(res), "same_as_oxr": same, "characters_equal_layer": lay,
             "summary": f"{same}/{len(res)} display equations equal OXR's LaTeX after canonical spelling; of the rest "
                        f"{lay} print the letters and digits of the text layer in their box (characters confirmed, not "
                        f"the layout); {len(issues)} open"}, issues)


def _move_figures(pdf, rdir, md):
    """Move out of the running text only what the reader declares as a figure body (middle_json); a <details>
    region it does not declare stays in full.md and is reported."""
    figs = MR.figure_bodies(rdir)
    doc = pymupdf.open(pdf)
    for f in figs:
        f.update(_printed_share(doc, f))
        f["in_markdown"] = False
    undeclared = []

    def take(m):
        region = WS.sub(" ", m.group(0))
        for f in figs:
            if not f["in_markdown"] and WS.sub(" ", f["text"]).strip() in region:
                f["in_markdown"] = True
                return ""
        undeclared.append(m.group(0)[:2000])
        return m.group(0)
    return DETAILS.sub(take, md), figs, undeclared


def parse(pdf, out):
    """the PDF is read from a local copy: on a mounted Windows drive every page's text extraction goes back to the
    file (10-29: a mounted Windows drive, 27 pages: 14.7 s to extract all words against 0.2 s from the local disk; 527 of a run's
    820 s were text extraction)"""
    src = Path(pdf).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="mineru_plus_"))
    try:
        shutil.copyfile(src, tmp / src.name)
        return _parse(tmp / src.name, out, src)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse(pdf, out, src):
    pdf, out = Path(pdf), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    prof = PR.profile(pdf)
    (out / "profile.json").write_text(json.dumps(prof, indent=1))

    mdir, odir = out / "readers" / "mineru", out / "readers" / "oxr"
    metas, errs = {}, {}

    def go(name, f):
        try:
            metas[name] = f()
        except Exception as e:   # a failed reader is reported, not hidden
            errs[name] = repr(e)[:500]
    th = [threading.Thread(target=go, args=("mineru", lambda: MR.read(pdf, mdir))),
          threading.Thread(target=go, args=("oxr", lambda: OX.read(pdf, odir)))]
    [t.start() for t in th]; [t.join() for t in th]
    if "mineru" in errs:
        raise RuntimeError("primary reader failed: " + errs["mineru"])

    md0, figs, undeclared = _move_figures(pdf, mdir, MR.markdown(mdir))
    issues = [{"kind": "undeclared <details> left in text", "text": u} for u in undeclared]
    checks, unchecked = {}, []
    md, edits = md0, []
    if "oxr" in errs:
        unchecked.append("characters: the second reader failed (" + errs["oxr"] + "); the text is the primary reading as is")
    else:
        dollars = TR.settle_dollars(mdir, odir, out / "checks" / "dollars")
        stats, subs, unread = TR.compare(mdir, odir)
        layer_pages = set(MR.pages(mdir)) - set(prof["pages_without_text_layer"])
        om = OM.find(pdf, mdir, odir)
        subs = [s for s in subs if not any(OM.overlaps(o, s) for o in om)] + om
        subs = RS.settle(pdf, subs, out / "checks")
        md, edits, open_items = RP.apply(md0, MR.pages(mdir), subs)
        # text-layer content the primary dropped or changed, judged by jev and written back (check/dropped.py)
        found = DR.judge(DR.find(pdf, mdir, out / "checks" / "dropped", md), out / "checks" / "dropped")
        md, dedits, dissues, dcount = DR.apply(md, MR.pages(mdir), found,
                                               OX.pages(odir))
        edits += dedits
        issues += dissues
        (out / "checks" / "dropped.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
        checks["dropped"] = {**dcount, "summary": f"{len(found)} places where the text layer has characters the primary lacks: "
                              f"jev reads the layer's form on the page at {dcount.get('printed', 0)} "
                              f"({dcount.get('written', 0)} written, {dcount.get('formulas retyped from the layer', 0)} of them "
                              f"inline formulas the primary misread, retyped from the layer), not at "
                              f"{dcount.get('not printed', 0)} (the layer is wrong there), "
                              f"{dcount.get('undecided', 0)} undecided"}
        # sentences a page or column break cuts, with floats between the halves (check/reflow.py)
        found_r = RF.judge(RF.find(mdir, md), out / "checks" / "reflow")
        md, redits, rissues, rcount = RF.apply(md, found_r)
        edits += redits
        issues += rissues
        (out / "checks" / "reflow.json").write_text(json.dumps(found_r, ensure_ascii=False, indent=1, default=dict))
        checks["reflow"] = {**rcount, "summary": f"{len(found_r)} paragraphs end mid-sentence before the next text block: "
                             f"{rcount.get('joined', 0)} joined with their continuation ({rcount.get('floats moved', 0)} "
                             f"with figures, tables or footnotes moved after the paragraph); {rcount.get('new', 0)} not continued by "
                             f"the next block ({rcount.get('next block starts a new sentence', 0)} of them because it starts a "
                             f"new sentence: a heading or author line typed as text), {rcount.get('undecided', 0)} undecided; "
                             f"{len(rissues)} open issues"}
        # tables against the text layer, cell by cell (check/table_layer.py)
        found_t = TL.judge(pdf, TL.find(pdf, mdir, layer_pages), out / "checks" / "tables", OX.pages(odir))
        md, tedits, tissues, tcount = TL.apply(md, mdir, found_t)
        edits += tedits
        issues += tissues
        (out / "checks" / "table_layer.json").write_text(json.dumps(found_t, ensure_ascii=False, indent=1, default=str))
        checks["tables"] = {**tcount, "summary": f"{len(found_t)} tables checked against the text layer cell by cell: "
                            f"{tcount.get('look-alike characters', 0)} look-alike characters and "
                            f"{tcount.get('spaces between glued words', 0)} spaces between a cell's glued lines written from the "
                            f"layer, {sum(v for k, v in tcount.items() if k.startswith('cells rewritten'))} cells rewritten "
                            f"(OXR or jev settled the layer's reading); {tcount.get('tables equal the layer (after fixes)', 0)} "
                            f"tables equal the layer, {tcount.get('tables with open cells', 0)} with open cells"}
        # text only the primary read: jev on the layer-placed words (check/unread.py)
        runs_u, uissues, ucount = UR.check(pdf, mdir, unread, layer_pages, out / "checks" / "unread")
        issues += uissues
        (out / "checks" / "unread.json").write_text(json.dumps(runs_u, ensure_ascii=False, indent=1))
        checks["unread"] = {**ucount, "found_elsewhere_in_oxr": stats["found_elsewhere_in_oxr"],
                            "summary": f"{stats['found_elsewhere_in_oxr']} primary tokens OXR read elsewhere on the page "
                                       f"(another order or a table); {ucount.get('tokens', 0)} tokens with letters or "
                                       f"digits in {ucount.get('runs', 0)} runs OXR did not read: jev reads them in the "
                                       f"page at {ucount.get('printed', 0)} runs ({ucount.get('tokens printed', 0)} tokens), "
                                       f"reads something else at {ucount.get('not printed', 0)}, undecided "
                                       f"{ucount.get('undecided', 0)}; {ucount.get('printed in the figure', 0)} "
                                       f"found by jev in the figure they caption (the figure is a picture); not placed by the text "
                                       f"layer {ucount.get('not placed by the text layer', 0)}, on pages without a layer "
                                       f"{ucount.get('page without a text layer', 0)} (those jev does not confirm, the "
                                       f"undecided and the unplaced are open issues with their crops)"}
        acc = RP.accept(md0, md, edits)
        if not acc["passed"]:          # an edit changed more than it declared: keep the unrepaired text
            issues.append({"kind": "repair rejected by acceptance", "detail": acc})
            md, edits = md0, []
        (out / "checks" / "disagreements.json").write_text(json.dumps(subs, ensure_ascii=False, indent=1))
        (out / "checks" / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=1))
        groups = substitution_groups(subs)
        (out / "checks" / "substitutions.json").write_text(json.dumps(groups, ensure_ascii=False, indent=1))
        issues += [{"kind": "disagreement", **x} for x in open_items]
        cnt = lambda pred: sum(1 for s in subs if pred(s))
        lb = [s for s in subs if s.get("route") == "line-break hyphen"]
        ch = [s for s in subs if s.get("route") == "characters"]
        verdicts = {}
        for s in ch:
            verdicts[s.get("verdict")] = verdicts.get(s.get("verdict"), 0) + 1
        checks["characters"] = {
            "compared": {"pages": stats["pages"], "primary_tokens": stats["tokens"], "agreeing_tokens": stats["equal"],
                         "only_in_primary": stats["only_primary"], "only_in_oxr": stats["only_oxr"]},
            "disagreements_by_kind": dict(collections.Counter(s["kind"] for s in subs)),
            "disagreements": {"form only (spacing, markup, OXR flattening, reading order)": cnt(lambda s: s["route"] == "form only"),
                              "line-break hyphen": len(lb), "characters": len(ch)},
            "line_break": {"by document usage": cnt(lambda s: s.get("by") == "document usage"),
                           "by jev spelling": cnt(lambda s: s.get("by") == "jev spelling"),
                           "primary was wrong": cnt(lambda s: s in lb and s.get("plan") == "edit")},
            "characters_verdicts": verdicts,
            "edits_written": len(edits), "left_open": len(open_items), "acceptance": acc,
            "substitutions_most_repeated": [f"{g['layer']!r}->{g['oxr']!r} x{g['count']}" for g in groups[:8]],
            "summary": f"{stats['equal']}/{stats['tokens']} primary tokens agree with OXR; {len(edits)} corrections written "
                       f"({cnt(lambda s: s in lb and s.get('plan') == 'edit')} line-break spellings), {len(open_items)} left "
                       f"open; acceptance {'passed' if acc['passed'] else 'FAILED'}"}
        unchecked += ["page headers, footers and page numbers: checked against the text layer only (coverage); a "
                      "broken layer there is not caught (OXR output has no headers or footers)",
                      ]
        checks["tables_without_layer"], ti = _tables(pdf, mdir, odir, out, {(t["page"], t["block"]) for t in found_t})
        checks["equations"], ei = _equations(pdf, mdir, odir, layer_pages)
        issues += ti + ei
    if prof["pages_without_text_layer"]:
        unchecked.append(f"pages without a text layer {prof['pages_without_text_layer']}: coverage and table characters "
                         "not checked there; both readers read the image")
    checks["coverage"], ci = _coverage(pdf, mdir, edits)
    if "dropped" in checks:               # block findings were judged one by one there; keep the rest
        ci = [i for i in ci if i.get("block") is None]
    issues += ci
    md, mst, mi = MG.add(pdf, mdir, md, set(prof["pages_without_text_layer"]))
    checks["margins"] = {**mst, "summary": f"{mst.get('written', 0)} page headers, footers, page numbers and side notes the "
                          f"reader left out of its markdown written to the closing section; {mst.get('equal to the text layer', 0)} "
                          f"equal the text layer, {mst.get('differs from the text layer', 0)} differ (open issues), "
                          f"{mst.get('unverified (no text layer)', 0)} on pages without a text layer"}
    issues += mi
    if "characters" in checks:            # disagreements a later step settled (dropped, retyped formulas, tables)
        issues, later = _settled_later(md, subs, issues)
        checks["characters"]["settled_by_later_steps"] = later
        checks["characters"]["left_open"] = lo = sum(i["kind"] == "disagreement" for i in issues)
        checks["characters"]["summary"] += f"; {later} of the open ones settled by later steps, {lo} remain open"
        (out / "checks" / "disagreements.json").write_text(json.dumps(subs, ensure_ascii=False, indent=1))
    unchecked.append("figure transcriptions beyond the printed labels (figures.json): the reader's estimate")
    md, nt = TR.tidy_math(md)            # numbers and styled words in formulas spelled as printed (rendering unchanged)
    checks["formula_spacing"] = {"formulas": nt, "summary": f"{nt} formulas respelled without the spaces LaTeX ignores "
                                                            "('0 . 0 1 5' as '0.015', '\\mathrm { A U C }' as '\\mathrm{AUC}')"}
    (out / "full.md").write_text(md)
    checks["sections"] = {"sections": SC.write(pdf, md, mdir, out),
                          "summary": "sections.json and quote_index.json in the pdf_parser schema"}
    (out / "figures.json").write_text(json.dumps(figs, indent=1, ensure_ascii=False))
    (out / "issues.json").write_text(json.dumps(issues, indent=1, ensure_ascii=False))

    blocks = MR.blocks(mdir)
    types = {}
    for b in blocks:
        types[b["type"]] = types.get(b["type"], 0) + 1
    report = {
        "tool": "mineru_plus", "version": VERSION, "input": str(src), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wall_s": round(time.time() - t0, 1),
        "scope": {"pages": prof["n_pages"], "pages_without_text_layer": prof["pages_without_text_layer"],
                  "blocks_by_type": types},
        "readers": {**metas, **{k: {"failed": v} for k, v in errs.items()}},
        "figures": {"transcriptions": len(figs), "moved_out_of_text": sum(f["in_markdown"] for f in figs),
                    "tokens": sum(f["tokens"] for f in figs), "tokens_printed": sum(f["tokens_printed"] for f in figs),
                    "figures_without_text_layer": sum(f["text_layer_words_in_box"] == 0 for f in figs)},
        "checks": checks, "backends": backend_report(), "calibration": CALIBRATION, "open_issues": len(issues),
        "unchecked": unchecked,
    }
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (out / "report.md").write_text(render(report))
    return report


def backend_report():
    """The backends of this run, per role: name, model, tier or command name (no secret, no path)."""
    return {role: backends.describe(role) for role in config.ROLES}


def _fmt(b):
    if b.get("backend") is None:
        return b.get("note", "not configured")
    parts = [b["note"]] if "note" in b else []
    parts += [f"{k} {v}" for k, v in b.items() if k not in ("backend", "note")]
    return b["backend"] + (f" ({', '.join(parts)})" if parts else "")


def _backend_lines(r):
    measured = "; ".join(f"{role} {_fmt(m)}" for role, m in MEASURED_WITH.items())
    lines = ["## Backends of this run", *[f"- {role}: {_fmt(b)}" for role, b in r["backends"].items()],
             f"Calibration measured with: {measured}."]
    return [*lines, ""]


def render(r):
    s, fg = r["scope"], r["figures"]
    lines = [f"# mineru_plus {r['version']} — {Path(r['input']).name}", "",
             f"{s['pages']} pages" + (f"; no text layer on pages {s['pages_without_text_layer']}"
                                      if s["pages_without_text_layer"] else "; every page has a text layer") + ".",
             "Readers: " + ", ".join(f"{k}" + (" (FAILED)" if "failed" in v else "") for k, v in r["readers"].items()) + ".",
             f"Figure transcriptions: {fg['transcriptions']} (figures.json), {fg['moved_out_of_text']} moved out of full.md; "
             f"{fg['tokens_printed']}/{fg['tokens']} of their tokens are printed in the figure's text layer, the rest is the "
             f"reader's reading of the graphic and unverified; {fg['figures_without_text_layer']} figures have no text layer.", ""]
    if r["checks"]:
        lines.append("## Measured on this document")
        for k, v in r["checks"].items():
            lines.append(f"- {k}: {v.get('summary', v)}")
    lines += ["", *_backend_lines(r), "## How far the checks can be trusted (tool calibration)",
              *[f"- {k}: {v}" for k, v in r["calibration"].items()]]
    if r["unchecked"]:
        lines += ["", "## Not checked", *[f"- {u}" for u in r["unchecked"]]]
    lines += ["", f"## Open issues: {r['open_issues']} (issues.json)"]
    return "\n".join(lines) + "\n"


REQUIRED_ROLES = ("primary_reader", "decision_judge", "page_judge")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="mineru-plus",
        description="Parse a paper PDF and check the parse against its text layer and a second reading of the page "
                    "image. The external components are set in the config file (see config.example.json).")
    ap.add_argument("--config", metavar="PATH",
                    help="config file (default: $MINERU_PLUS_CONFIG, else ./mineru_plus.json)")
    ap.add_argument("pdf", help="the PDF to parse")
    ap.add_argument("out_dir", help="the output directory")
    a = ap.parse_args(argv)
    try:
        config.load(a.config)
        for role in REQUIRED_ROLES:          # fail before any work, naming the role and the config file
            backends.get(role)
    except config.ConfigError as e:
        sys.exit(f"mineru_plus: {e}")
    try:
        backends.get("second_reader")
    except config.ConfigError as e:          # the run goes on without a second reading, and says so in its report
        print(f"mineru_plus: warning: {e}", file=sys.stderr)
    print(render(parse(a.pdf, a.out_dir)))


if __name__ == "__main__":
    main()
