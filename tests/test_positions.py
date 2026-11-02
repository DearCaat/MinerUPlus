import pymupdf
from mineru_plus import positions as P


def _lay(text, y=10.0, line=(0, 0)):
    """layer characters of one printed line, 5 points wide each, spaces left out as the layer reader does"""
    out, x = [], 0.0
    for ch in text:
        if not ch.isspace():
            out.append((ch, pymupdf.Rect(x, y, x + 5, y + 8), line))
        x += 5
    return out


def _spans(md, lay):
    mc, formulas = P._md_chars(md, 0)
    return P._spans(1, mc, formulas, lay, [0, 0, 100, 100], lambda a, b: md[a:b])


def test_words_get_their_own_boxes():
    md = "the cohort (n = 210) was"
    sp = _spans(md, _lay(md))
    assert all(s[3] == "layer" for s in sp)
    assert [md[s[0]:s[1]] for s in sp] == ["the", "cohort", "(n", "=", "210)", "was"]
    assert sp[1][4] == [[20.0, 10.0, 50.0, 18.0]]


def test_formula_lies_between_its_neighbours():
    md = "where $\\alpha = 0.5$ holds"
    sp = _spans(md, _lay("where α = 0.5 holds"))
    between = [s for s in sp if s[3] == "between"]
    assert len(between) == 1 and md[between[0][0]:between[0][1]] == "$\\alpha = 0.5$"
    assert between[0][4] == [[30.0, 10.0, 65.0, 18.0]]


def test_text_not_printed_between_adjacent_neighbours_gets_no_span():
    md = "see [https://x.org/a](https://x.org/a) now"
    sp = _spans(md, _lay("see https://x.org/a now"))
    assert {s[3] for s in sp} == {"layer"}
    assert not any("](" in md[s[0]:s[1]] for s in sp)


def test_unaligned_block_falls_back_to_its_box():
    sp = _spans("Chemotherapy", [])
    assert sp == [[0, 12, 1, "block", [[0, 0, 100, 100]]]]


def test_locate_finds_an_edited_block_by_its_words():
    md = "# Title\n\nFirst paragraph here.\n\nWe trained a model on the Bassiouni et al. cohort, with immune-excluded areas.\n\nNext."
    content = "We trained a model on the Bassiouni et al. cohort, with immuneexcluded areas."
    lo, hi = P._locate(md, content, 0)
    assert md[lo:hi] == "We trained a model on the Bassiouni et al. cohort, with immune-excluded areas."


def test_lines_merge_word_boxes_of_one_line():
    spans = [{"page": 2, "boxes": [[0, 10, 20, 18]]}, {"page": 2, "boxes": [[25, 10, 40, 18]]},
             {"page": 2, "boxes": [[0, 20, 30, 28]]}]
    assert P.lines(spans) == {2: [[0, 10, 40, 18], [0, 20, 30, 28]]}


def test_locate_finds_a_table_across_its_cells():
    md = "Text before.\n\n<table><tr><td>Adverse events</td><td>SNF2 (n = 50)</td></tr><tr><td>Rash</td><td>3 (6.0)</td></tr></table>\n\nAfter."
    lo, hi = P._locate(md, " Adverse events  SNF2 (n = 50)  Rash  3 (6.0) ", 0)
    assert md[lo:hi].startswith("<table><tr><td>Adverse") or md[lo:hi].startswith("Adverse")
    assert md[lo:hi].rstrip().endswith("3 (6.0)") or "3 (6.0)" in md[lo:hi]
