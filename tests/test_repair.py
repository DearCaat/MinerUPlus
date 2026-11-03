import unittest
from mineru_plus import repair as RP
from mineru_plus.check import gemini as G


class PunctuationAfterFormula(unittest.TestCase):
    # 10-30, conic p20: OXR 'mR2 ,' against '$R ^ { 2 }$' was written as '$R ^ { 2, }$'
    def test_comma_goes_after_the_formula(self):
        b = "d, 𝑚𝑚 $R ^ { 2 }$ e, x"
        s = {"raw_span": [3, 17], "oxr_text": "𝑚R2,", "by": "jev (exactly printed)"}
        self.assertEqual(RP.char_edits(b, [s])[0], "d, 𝑚 $R ^ { 2 }$, e, x")

    def test_period_at_block_end(self):
        b = "in terms of 𝑚𝑚 $\\iota R ^ { 2 }$"
        s = {"raw_span": [12, len(b)], "oxr_text": "𝑚R2.", "by": "jev (exactly printed)"}
        self.assertEqual(RP.char_edits(b, [s])[0], "in terms of 𝑚 $R ^ { 2 }$.")


class LocateEditedBlock(unittest.TestCase):
    # 10-30, frontiers: a character edit in the last 40 characters of the abstract hid the block from check/dropped
    def test_block_edited_at_its_end(self):
        from mineru_plus.check import dropped as DR
        raw = "Results: " + "the model was trained on many slides and validated on two cohorts; " * 3 + "orientation $\\rho = 0.012$"
        md = "# Title\n\n" + raw.replace("$\\rho = 0.012$", "$(p = 0.012$") + "\n\nNext paragraph.\n"
        self.assertEqual(DR.locate(md, raw), md.split("\n\n")[1])


class DroppedReading(unittest.TestCase):
    def test_capital_lambda_and_accents_print(self):
        # 10-30, abx: '\\Lambda' read as nothing and '\\hat' as nothing let the layer's 'Λ' and 'ˆ' look dropped
        from mineru_plus.check.dropped import plain_map
        self.assertEqual("".join(c for c, _ in plain_map("so $\\Lambda \\leq 1$")), "soΛ≤1")
        self.assertEqual("".join(c for c, _ in plain_map("and $\\hat { a } _ { k }$")), "andak")
        # 10-30, abx: the layer's 'ˆa' against the parse's 'â' is no dropped accent
        from mineru_plus.check.dropped import _norm_char
        self.assertEqual([c for x in "ˆa" for c in _norm_char(x)], [c for x in "â" for c in _norm_char(x)])

    def test_overprinted_layer(self):
        # 10-30, conic: the layer writes overprinted letters twice, '𝑚𝑚𝑅𝑅2,' for 'mR2,'
        from mineru_plus.check.dropped import _doubled
        self.assertTrue(_doubled("𝑚𝑚𝑅𝑅2,", "mR2,"))
        self.assertFalse(_doubled("0.011", "0.01"))
        self.assertFalse(_doubled("Hello", "Helo"))


class LookAlikeByLayer(unittest.TestCase):
    def test_dash_is_no_word_evidence(self):
        # 10-30, biomni: an en dash written as OXR's hyphen because the page has hyphens elsewhere
        from mineru_plus.check import resolve as RS
        self.assertIsNone(RS._differing_words({"primary": "tasks 13 –", "oxr": "tasks13 -"}))
        self.assertIsNotNone(RS._differing_words({"primary": "Al model", "oxr": "AI model"}))


class OrderedPlacement(unittest.TestCase):
    # 10-30: 'url' found in a reference entry other than the passage's, its context words elsewhere in the crop
    def test_context_must_surround_the_reading(self):
        self.assertEqual(G._ordered("p4urlhttpsp10", ["p4"], [["url"]], ["https"]), 3)
        self.assertEqual(G._ordered("urlhttpsp4", ["p4"], [["url"]], ["https"]), 2)

    def test_no_letters_in_reading(self):
        self.assertEqual(G._ordered("andmaskingprocedures", ["masking"], [], ["procedures"]), 3)


if __name__ == "__main__":
    unittest.main()


def test_unread_line_break_runs():
    from mineru_plus.check.unread import _other_split
    bk = [("pre", "dictions"), ("Pali", "soul,"), ("data", "set3")]
    assert _other_split("pre-dictions", bk) == "predictions"
    assert _other_split("Palisoul", bk) == "Pali-soul"
    assert _other_split("dataset 3", bk) == "data-set 3"
    assert _other_split("unrelated words", bk) is None


def test_formula_symbols_are_printed_characters():
    """prism 11-02: '\\ell', '\\in', '\\log' in a formula print 'ℓ', '∈', 'log'; '\\le' is not the start of '\\left'"""
    from mineru_plus.check import dropped as DR, two_readings as TR
    plain = lambda r: "".join(c for c, _ in DR.plain_map(r))
    assert plain(r"an $\ell_{2}$-regularized") == "anl2-regularized"
    assert plain(r"Stability $\in [0,1]$") == "Stability∈[0,1]"
    assert plain(r"against $\log_{10}$") == "againstlog10"
    assert TR.canon(r"$\left( x \right) \le 1$") == "(x)≤1"
    assert "∫" in TR.latex_plain(r"\int f") and "∈" not in TR.latex_plain(r"\int f")


def test_layer_context_on_both_sides():
    """wsicond 11-02: 'The resuls are' printed once and 'The results' elsewhere on the page; the left word alone
    finds both readings, both sides find only the printed one"""
    from mineru_plus.check import resolve as R
    from mineru_plus import layer as LY
    import pymupdf
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((50, 80), "The results of the first part. The resuls are presented in Tab. 12.")
    pg.insert_text((50, 100), "The results show it.")
    s = {"primary": "resuls", "oxr": "results", "left": ["NICER", "'s", ".", "The"], "right": ["are", "presented"]}
    assert R._layer_says(LY.page(doc, 0), s) == "primary"


def test_line_break_word_written_beside_markup():
    """rnasplice 11-02: the passage holds a superscript the tokens do not; the split word alone is found once"""
    from mineru_plus import repair as RP
    s = {"route": "line-break hyphen", "verdict": "hyphen", "split": "well-|documented",
         "primary_toks": ["welldocumented", "heterogeneity", "48", ",", "49"], "left": ["its"]}
    block = "because of its welldocumented heterogeneity<sup>48,49</sup>. The tumor"
    span = RP._locate(block, s) or RP._locate_split(block, s)
    assert block[span[0]:span[1]] == "welldocumented"
    assert RP._new_span(block[span[0]:span[1]], s) == "well-documented"


def test_table_cell_with_an_entity_keeps_positions():
    from mineru_plus.check import table_layer as TL
    cell = {"text": "&lt;0.0001"}
    chars = TL.cell_chars(cell)
    assert [c for c, _ in chars] == list("<0.0001")
    assert chars[0][1] is None and cell["text"][chars[2][1]] == "."


def test_spacing_the_reader_made_up_is_settled_by_the_layer_words(tmp_path):
    import pymupdf
    from mineru_plus.check import resolve as RS
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((72, 72), "the 90% confidence interval (CI) of the flow")
    pdf = tmp_path / "s.pdf"
    doc.save(pdf)
    pg = pymupdf.open(pdf)[0]
    assert RS._layer_spacing_says(pg, {"primary": "i nterval", "oxr": "interval"}) == "oxr"
    assert RS._layer_spacing_says(pg, {"primary": "C I", "oxr": "CI"}) == "oxr"
    assert RS._layer_spacing_says(pg, {"primary": "flow", "oxr": "f low"}) is None          # OXR cut the word
    assert RS._layer_spacing_says(pg, {"primary": "Shulman , 1,26", "oxr": "Shulman,1,26"}) is None
    assert RP._respace("confidence i nterval", "confidence interval") == "confidence interval"
    assert RP._respace("patientsUCMC", "patients UCMC") == "patients UCMC"
    assert RP._respace("**i nterval**", "interval") is None


def test_split_word_both_readers_join_is_written_as_the_document_spells_it(tmp_path):
    import json
    import pymupdf
    from mineru_plus.check import linebreak as LB
    doc = pymupdf.open()
    pg = doc.new_page()
    for k, line in enumerate(["The node-positive cohort and the", "similar results in node-", "positive patients."]):
        pg.insert_text((72, 72 + 30 * k), line)
    pdf = tmp_path / "n.pdf"
    doc.save(pdf)
    md = "The node-positive cohort and the similar results in nodepositive patients."
    mdir = tmp_path / "mineru"
    mdir.mkdir()
    (mdir / "structured_content.json").write_text(json.dumps(
        {"pages": [{"page_idx": 0, "blocks": [{"type": "text", "content": md, "bbox": [0, 0, 1, 1]}]}]}))
    subs = LB.agreed_splits(str(pdf), mdir, [])
    assert [(x["primary"], x["oxr"]) for x in subs] == [("nodepositive", "node-positive")]
    assert "usage" in subs[0]["source"]


def test_dingbat_bullets_are_mapped_by_their_font():
    from mineru_plus import layer as LY
    assert LY.DINGBATS["wingdings"][0x6C] == "●" and LY.DINGBATS["symbol"][0xB7] == "•"


def test_margin_text_already_in_the_body_in_other_markup():
    from mineru_plus import margins as MG
    body = "A full list of affiliations appears at the end of the paper. e-mail: [x@y.org](mailto:x@y.org)"
    assert MG._alnum("A full list of affiliations appears at the end of the paper. e-mail: x@y.org") in MG._alnum(body)


def test_formula_letter_written_in_place_unless_the_formula_is_retyped():
    from mineru_plus.check import dropped as DR
    raw = r'odds $\frac { I n ( O R ) } { 2 }$ and'
    s = raw.index('I')
    f = {'insert': 'l', 'replaces': 'I', 'raw_span': [s, s + 1]}
    assert DR._edit_plain(raw, f)[0] == raw.replace('I n', 'l n')
    assert DR._edit_plain(raw, dict(f, retype_ok=True)) is None             # the retype writes it with the rest
    c = raw.index('frac') + 1
    assert DR._edit_plain(raw, {'insert': 'x', 'replaces': 'r', 'raw_span': [c, c + 1]}) is None   # a command name


def test_list_markers_open_their_lines():
    from mineru_plus.check import dropped as DR
    raw = ("Death;\nLife is in danger;\nResulting in hospitalization or prolonged hospitalization;\n"
           "Permanent or severely disabled;\nCongenital malformations/defects, significant medical events.")
    s = {"route": "omission", "primary_toks": ["danger;", "Resulting"], "insert": " \u27a2 ", "starts_line": True}
    assert RP._new_span("danger;\nResulting", s) == "danger;\n\u27a2 Resulting"
    assert RP._new_span("danger;\nResulting", dict(s, starts_line=False)) == "danger; \u27a2\nResulting"
    edited = raw.replace("\n", "\n\u27a2 ")
    md = "## 14.3 Serious Adverse Events\n\n" + edited + "\n\n## 14.4 Avenues"
    assert DR.locate(md, raw) == edited                   # the block's first characters edited by an earlier route
    f = {"insert": "\u27a2", "insert_text": "\u27a2", "raw_span": None, "raw_after": 5, "raw_next": 7,
         "starts_line": True, "space_before": True, "space_after": True}
    assert DR._edit_plain(raw, f)[0].startswith("Death;\n\u27a2 Life")


def test_layer_words_out_of_line_order_are_not_placed(tmp_path):
    """a symbol the layer holds after the line's last word, printed at the line's start, is not written after that
    word"""
    import json
    import pymupdf
    from mineru_plus.check import dropped as DR
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((90, 100), "indicates the Pearson correlation coefficient and the")
    pg.insert_text((72, 100), "R2")                     # drawn after the line: after 'the' in the layer, first on it
    pg.insert_text((72, 130), "associated two-sided p-value for the null hypothesis.")
    pdf = tmp_path / "x.pdf"
    doc.save(pdf)
    md = "indicates the Pearson correlation coefficient and the associated two-sided p-value for the null hypothesis."
    mdir = tmp_path / "mineru"
    mdir.mkdir()
    (mdir / "structured_content.json").write_text(json.dumps({"pages": [{"page_idx": 0, "blocks": [
        {"type": "text", "content": md, "bbox": [0.05, 0.05, 0.95, 0.3]}]}]}))
    (tmp_path / "work" / "crops").mkdir(parents=True)
    found = [f for f in DR.find(str(pdf), mdir, tmp_path / "work") if f["insert"] == "R2"]
    assert found and not any(f["placeable"] for f in found)


def test_logo_with_glyphs_drawn_as_curves_is_not_checked_by_its_layer_text():
    import pymupdf
    from mineru_plus import margins as MG
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((100, 60), "ll", fontsize=16)
    pg.draw_bezier((70, 62), (72, 44), (88, 44), (90, 62), fill=(0, 0, 0))    # 'Ce' drawn as a curve
    box = pymupdf.Rect(65, 40, 140, 66)
    assert MG._outlined(pg, box, pg.get_drawings())
    plain = doc.new_page()
    plain.insert_text((100, 60), "Article", fontsize=16)
    plain.draw_line((65, 64), (200, 64))                                   # a rule under a running head
    assert not MG._outlined(plain, box, plain.get_drawings())


def test_words_broken_by_spaces_are_joined_where_layer_and_oxr_have_the_word(tmp_path):
    import json
    import pymupdf
    from mineru_plus.check import respace as RSP
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((72, 72), "Adverse events of grade 1-2 occurring in patients are listed log in to")
    pdf = tmp_path / "t.pdf"
    doc.save(pdf)
    text = "Adverse events of g rade 1-2 occu rri ng i n patients are l isted log in to"
    mdir = tmp_path / "mineru"
    mdir.mkdir()
    (mdir / "structured_content.json").write_text(json.dumps({"pages": [{"page_idx": 0, "blocks": [
        {"type": "table_footnote", "content": text, "bbox": [0, 0, 1, 1]}]}]}))
    oxr = {1: [{"type": "Table", "content": "<td>grade 1-2 occurring in patients are listed log in to</td>"}]}
    md, edits, issues, joined, _ = RSP.apply(str(pdf), mdir, "# T\n\n" + text + "\n", {1}, oxr)
    assert "of grade 1-2 occurring in patients are listed log in to" in md       # 'in to' printed apart stays
    md2, edits2, issues2, _, _ = RSP.apply(str(pdf), mdir, "# T\n\n" + text + "\n", {1}, None)
    assert edits2 == [] and {i["text"] for i in issues2} == {"g rade", "occu rri ng", "i n", "l isted"}  # reported
    glued = {1: [{"type": "Text", "content": "g rade 1-2 occu rri ng i n patients are l isted"}]}
    assert RSP.apply(str(pdf), mdir, "# T\n\n" + text + "\n", {1}, glued)[1:3] == ([], [])   # OXR reads them apart


def test_running_head_equal_to_a_heading_elsewhere_is_kept(tmp_path):
    import json
    import pymupdf
    from mineru_plus import margins as MG
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page().insert_text((450, 40), "Article")
    pdf = tmp_path / "m.pdf"
    doc.save(pdf)
    mdir = tmp_path / "mineru"
    mdir.mkdir()
    head = {"type": "header", "content": "Article", "bbox": [0.7, 0.03, 0.9, 0.07]}
    (mdir / "structured_content.json").write_text(json.dumps({"pages": [
        {"page_idx": 0, "blocks": [head]},
        {"page_idx": 1, "blocks": [{"type": "paragraph_title", "content": "Article", "bbox": [0.1, 0.2, 0.3, 0.25]}]}]}))
    md, _, _ = MG.add(str(pdf), mdir, "## Article\n\nBody text.\n")
    assert "- p1 header: Article" in md


def test_space_inside_a_word_the_layer_does_not_decide_is_reported(tmp_path):
    import pymupdf
    from mineru_plus.check import resolve as RS
    doc = pymupdf.open()
    pg = doc.new_page()
    # a spacing accent and a space, then the rest of the name drawn over the space (11-03, PTA-05: 'Ku¨' 'mmel,')
    pg.insert_text((72, 72), "Ku\u00a8 ")
    pg.insert_text((72 + pymupdf.get_text_length("Ku\u00a8", fontsize=11), 72), "mmel, M., and others")
    pg.insert_text((72, 100), "Galva\u00b4 ")
    pg.insert_text((72 + pymupdf.get_text_length("Galva\u00b4 ", fontsize=11) + 3, 100), "n, L.")    # apart
    pdf = tmp_path / "a.pdf"
    doc.save(pdf)
    pg = pymupdf.open(pdf)[0]
    assert RS._layer_spacing_says(pg, {"primary": "K\u00fc mmel", "oxr": "K\u00fcmmel"}) == "oxr"
    assert RS._layer_spacing_says(pg, {"primary": "Galv\u00e1 n", "oxr": "Galv\u00e1n"}) is None   # reported
    assert RS._splits_word({"primary": "Ferná ndez", "oxr": "Fernández"})
    assert not RS._splits_word({"primary": "patients UCMC", "oxr": "patientsUCMC2"})


def test_check_box_marks_drawn_as_images_are_written_with_column_and_row(tmp_path):
    import pymupdf
    from mineru_plus import marks as MK
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((24, 100), "n/a", fontsize=8)
    pg.insert_text((44, 100), "Confirmed", fontsize=8)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pix.clear_with(0)
    for k, item in enumerate(["The exact sample size", "A description of all covariates tested"]):
        y = 110 + 20 * k
        for x in (27, 43):
            pg.draw_rect(pymupdf.Rect(x, y, x + 10, y + 10), color=(0.3, 0.3, 0.3), fill=(1, 1, 1))
        mark_x = 46 if k == 0 else 30                        # Confirmed, then n/a
        pg.insert_image(pymupdf.Rect(mark_x, y + 3, mark_x + 4, y + 7), pixmap=pix)
        pg.insert_text((60, y + 8), item, fontsize=8)
    pdf = tmp_path / "f.pdf"
    doc.save(pdf)
    md = MK.add("Body.\n", MK.find(str(pdf)))
    assert "- p1, Confirmed: The exact sample size" in md and "- p1, n/a: A description of all covariates tested" in md


def test_math_glyphs_the_layer_has_as_spaces_are_found():
    from mineru_plus import layer as LY
    ch = lambda c, x: {"c": c, "bbox": (x, 10, x + 4, 20)}
    span = lambda font, t: {"font": font, "chars": [ch(c, 10 + 4 * i) for i, c in enumerate(t)]}

    class Page:
        def __init__(self, spans):
            self.spans = spans

        def get_text(self, kind):
            return {"blocks": [{"lines": [{"spans": self.spans}]}]}
    assert len(LY.blank_glyphs(Page([span("Cambria Math", "    (     ) = ")]))) == 2
    assert LY.blank_glyphs(Page([span("Times New Roman", "a    b")])) == []    # spaces outside a math font


def test_space_before_a_mark_the_page_prints_against_the_word_is_dropped(tmp_path):
    import json
    import pymupdf
    from mineru_plus.check import respace as RSP
    doc = pymupdf.open()
    pg = doc.new_page()
    # a spacing accent and a space glyph, the comma drawn over the space (11-03, PTA-05: 'Pare´' ',' 0.1 pt apart)
    pg.insert_text((72, 72), "Pare´ ")
    pg.insert_text((72 + pymupdf.get_text_length("Pare´", fontsize=11), 72), ", L., and Smith")
    pg.insert_text((72 + pymupdf.get_text_length("Pare´, L., and Smith ", fontsize=11) + 3, 72), ", J.")  # apart
    pg.insert_text((72, 100), "a response,39 to it")
    pdf = tmp_path / "t.pdf"
    doc.save(pdf)
    text = "Paré , L., and Smith , J. a response ,39 to it"
    mdir = tmp_path / "mineru"
    mdir.mkdir()
    (mdir / "structured_content.json").write_text(json.dumps({"pages": [{"page_idx": 0, "blocks": [
        {"type": "text", "content": text, "bbox": [0, 0, 1, 1]}]}]}))
    oxr = {1: [{"type": "Text", "content": "Paré, L., and Smith, J. a response,39 to it"}]}
    md, edits, issues, _, _ = RSP.apply(str(pdf), mdir, "# T\n\n" + text + "\n", {1}, oxr)
    # the gap the layer prints stays; before a number the space is left (one token would be made of two)
    assert "Paré, L., and Smith , J. a response ,39 to it" in md and issues == []
    assert RSP.apply(str(pdf), mdir, "# T\n\n" + text + "\n", {1}, None)[1:3] == ([], [])   # no OXR: nothing


def test_line_break_hyphen_set_apart_after_a_spacing_accent(tmp_path):
    import pymupdf
    from mineru_plus.check import linebreak as LB
    doc = pymupdf.open()
    pg = doc.new_page()
    # the layer's line ends 'Gonza´' then a hyphen against it (11-03, PTA-05: '\xad' with no gap)
    pg.insert_text((72, 72), "Prat, A., Gonza´ ")
    pg.insert_text((72 + pymupdf.get_text_length("Prat, A., Gonza´", fontsize=11), 72), "-")
    pg.insert_text((72, 86), "lez Farre, B.")
    doc.save(tmp_path / "t.pdf")             # a named document: the layer's word cache is per document name
    bk = LB.breaks(pymupdf.open(tmp_path / "t.pdf")[0])
    assert ("Gonza", "lez") in bk
    # the split holds the reading's letters, which the repair finds in the block
    assert LB.is_linebreak({"primary": "Gonzá - lez", "oxr": "González"}, bk) == ("Gonzá", "lez", "Gonza")


def test_layer_word_kept_elsewhere_but_printed_in_a_gap_is_moved_into_it():
    from mineru_plus.check import omissions as OM
    w = lambda t, x0, x1, y=100: (x0, y, x1, y + 10, t, 0, 0, 0)
    # 11-03, PTA-11 MOESM1: the layer reads ', with being ... the' and then the formula and 'count' of that line
    words = [w(",", 275, 278), w("with", 283, 303), w("being", 341, 368), w("the", 374, 389),
             w("mean", 210, 237, 101), w("std", 259, 272, 101), w("count", 308, 336, 101), w("given", 72, 100, 120)]
    assert [x[4] for x in OM._line_order(words)] == [",", "with", "count", "being", "the", "mean", "std", "given"]
