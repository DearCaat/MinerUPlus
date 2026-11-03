import json
import pymupdf
from mineru_plus import source as SRC
from mineru_plus.check import linebreak as LB


def test_source_text_of_each_format(tmp_path):
    (tmp_path / "a.html").write_text('<html><head><title>x</title></head><body><p>we train an <math alttext="\\ell_2">'
                                     '<semantics><mi>ℓ</mi><annotation encoding="application/x-tex">\\ell_2</annotation>'
                                     '</semantics></math> probe &amp; more</p></body></html>')
    (tmp_path / "a.xml").write_text('<article><body><p>with <inline-formula><alternatives><tex-math>\\alpha</tex-math>'
                                    '<mml:math><mml:mi>α</mml:mi></mml:math></alternatives></inline-formula> = 0.5</p>'
                                    '</body></article>')
    (tmp_path / "a.tex").write_text("% not printed\nan under\\-represented class~\\cite{x} with $\\ell_{2}$ costs \\$5\n")
    assert SRC.letters(SRC._read(tmp_path / "a.html")) == "wetrainanlprobemore"             # NFKC: ℓ compares as l
    assert SRC.letters(SRC._read(tmp_path / "a.xml")) == "withα05"
    t = SRC._read(tmp_path / "a.tex")
    assert "not printed" not in t and "underrepresented class" in t and "$5" in t
    assert "withl2costs5" in SRC.letters(t)


def test_source_says_only_where_its_context_is_the_parse():
    s = SRC.Source("because of its well-documented heterogeneity. The results are in Table 2.")
    assert s.hyphen(["of", "its"], "welldocumented", "well-documented", ["heterogeneity", "48"]) == 1
    assert s.hyphen(["at", "the"], "welldocumented", "well-documented", ["cohort", "level"]) is None
    assert s.spells([".", "The"], "resuls", "results", ["are", "in"]) == 1
    assert s.spells(["The"], "results", "results.", ["are"]) is None          # letters equal: not a spelling question
    both = SRC.Source("a long-term and a longterm study")
    assert both.hyphen(["a"], "longterm", "long-term", ["and"]) == 1
    assert both.hyphen(["a"], "longterm", "long-term", []) is None


def test_line_break_word_both_readers_join_against_the_source(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page()
    for k, line in enumerate(["The labels were hand-", "written by two staff, and the", "model is com-",
                              "putationally cheap."]):
        pg.insert_text((72, 72 + 30 * k), line)
    pdf = tmp_path / "p.pdf"
    doc.save(pdf)
    md = "The labels were handwritten by two staff, and the model is computationally cheap."
    mdir = tmp_path / "mineru"
    mdir.mkdir()
    (mdir / "structured_content.json").write_text(json.dumps(
        {"pages": [{"page_idx": 0, "blocks": [{"type": "text", "content": md, "bbox": [0, 0, 1, 1]}]}]}))
    src = SRC.Source("The labels were hand-written by two staff, and the model is computationally cheap.")
    subs = LB.agreed_splits(str(pdf), mdir, [], src)
    assert [(x["primary"], x["oxr"], x["raw_span"]) for x in subs] == [("handwritten", "hand-written", [16, 27])]
    assert LB.agreed_splits(str(pdf), mdir, [], SRC.Source("The labels were handwritten by two staff")) == []


def test_source_is_asked_about_latin_words_only():
    from mineru_plus.check import resolve as RS
    assert RS._source_may_spell("Sofène", "Sofiène") and RS._source_may_spell("MAST 84", "MAST64")
    assert not RS._source_may_spell("Skarlinski 1", "Skarlinski1 Sam Cox1,2 Jon M . Laurent1")    # reading order
    assert not RS._source_may_spell("network . Γ23A", "network.23 A")                           # a symbol
    assert not RS._source_may_spell("7", "†")
    s = {"primary": "2aI b", "oxr": "2ab"}
    assert RS._drops_letters(s, "oxr", "primary") and not RS._drops_letters(s, "primary", "oxr")
