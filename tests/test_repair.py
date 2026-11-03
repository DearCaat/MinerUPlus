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
