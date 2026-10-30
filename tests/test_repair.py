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
