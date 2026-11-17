import unittest
from mineru_plus.check import tables as TB


class BrokenSpanAttribute(unittest.TestCase):
    # 11-17, PTA-565 mmc4/mmc5: OXR dropped the '">' after a colspan value; int() on the swallowed rest stopped the parse
    ROW = '<table><tr><td colspan="5{\'PT\': 0.01, \'C\': 10}</td><td></td><td>0.917249</td></tr></table>'

    def test_unclosed_span_does_not_raise(self):
        self.assertEqual(TB.cells(self.ROW), [])         # the primary reading is left as written: the cells are lost

    def test_second_reading_closes_the_tag(self):
        g = TB.grid(TB.second_reading(self.ROW))
        self.assertEqual(g, [["{'PT': 0.01, 'C': 10}"] * 5 + ["", "0.917249"]])

    def test_well_formed_spans_unchanged(self):
        ok = '<table><tr><td colspan="2">a</td><td rowspan="2">b</td></tr><tr><td>c</td><td>d</td></tr></table>'
        self.assertEqual(TB.second_reading(ok), ok)
        self.assertEqual(TB.grid(ok), [["a", "a", "b"], ["c", "d", "b"]])

    def test_span_value_forms(self):
        self.assertEqual([TB._span(v) for v in (None, "", "3", " 2", "0", "x", "4px")], [1, 1, 3, 2, 1, 1, 4])


if __name__ == "__main__":
    unittest.main()
