"""check/spelling.py: words full.md spells otherwise than the text layer prints them."""
import pymupdf
from mineru_plus.check import spelling as SP
from mineru_plus.source import Source

LINES = ["All data in this sudy were collected from patients treated",
         "at two hospitals between 2015 and 2020, and the key findings",
         "are reported below together with the <a href=\"x\">upload</a> link."]


def _pdf(tmp_path, lines=LINES):
    doc = pymupdf.open()
    pg = doc.new_page()
    for n, t in enumerate(lines):
        pg.insert_text((50, 80 + 16 * n), t, fontsize=10)
    p = tmp_path / "p.pdf"
    doc.save(p)
    return pymupdf.open(p)


def _md(word="study", ligature="fi"):
    return ("# Methods\n\n"
            f"All data in this {word} were collected from patients treated at two hospitals between 2015 and 2020, "
            f"and the key {ligature}ndings are reported below together with the &lt;a href=\"x\"&gt;<u>upload</u>"
            f"&lt;/a&gt; link.\n")


def test_reader_correction_is_reported_with_the_page_letters(tmp_path):
    issues, st = SP.check(_pdf(tmp_path), _md())
    assert len(issues) == 1, issues
    i = issues[0]
    assert (i["page"], i["layer_letters"], i["parse_letters"]) == (1, "", "t")
    assert "sudy" in i["layer"] and "study" in i["parse"] and i["layer_boxes"]
    assert "suggested_edit" not in i            # no source: nothing says the page's spelling is the authors'


def test_printed_markup_and_underline_are_no_difference(tmp_path):
    # '&lt;/a&gt;' is printed text, '<u>' only underlines
    issues, _ = SP.check(_pdf(tmp_path), _md(word="sudy"))
    assert issues == []


def test_dropped_ligature_is_found(tmp_path):
    issues, _ = SP.check(_pdf(tmp_path), _md(word="sudy", ligature="\x94"))
    assert [(i["layer_letters"], i["parse_letters"]) for i in issues] == [("fi", "")]


def test_source_agreeing_with_the_layer_suggests_the_edit_back(tmp_path):
    src = Source("Title\n\nAll data in this sudy were collected from patients treated at two hospitals between 2015 "
                 "and 2020, and the key findings are reported below.\n\nOther passage with the word study in it.")
    md = _md()
    out, edits, issues, st = SP.apply(_pdf(tmp_path), md, src, write=False)
    assert out == md and edits == []
    assert issues[0]["source"] == "layer"
    assert issues[0]["suggested_edit"] == {"old": "t", "new": ""}
    out, edits, issues, st = SP.apply(_pdf(tmp_path), md, src, write=True)
    assert "this sudy were" in out and issues == [] and edits[0]["route"] == "spelling"


def test_source_agreeing_with_the_parse_gives_no_edit(tmp_path):
    # the aligned passage writes the parse's spelling: the source differs from the print too (PTA-607 'biopies')
    src = Source("All data in this study were collected from patients treated at two hospitals between 2015 and "
                 "2020, and the key findings are reported below.\n\nElsewhere: this sudy.")
    issues, _ = SP.check(_pdf(tmp_path), _md(), src)
    assert issues[0]["source"] == "parse" and "suggested_edit" not in issues[0]
