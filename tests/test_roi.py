"""Places of issues without a box of their own: the check's boxes of layer words, or the layer's words found once."""
import pymupdf
from mineru_plus.check import roi as RI
from mineru_plus import run


def _doc(tmp_path):
    # saved and opened by name: layer.page and layer.words cache by the file name
    doc = pymupdf.open()
    pg = doc.new_page(width=400, height=400)
    pg.insert_text((50, 60), "Editor Nature Biomedical Engineering")
    pg.insert_text((50, 90), "__________")
    pg.insert_text((50, 120), "Reviewer #1 (Report for the authors)")
    pg.insert_text((50, 380), "473 | Nature | Vol 634")
    path = tmp_path / "roi.pdf"
    doc.save(str(path))
    return pymupdf.open(str(path))


def test_layer_words_found_once(tmp_path):
    places = RI._layer_words(_doc(tmp_path), {"page": 1, "layer_words": ["__________"]})
    assert len(places) == 1
    page, r, mark, _ = places[0]
    assert page == 1 and mark and 80 < r.y1 < 95


def test_layer_words_in_several_places_give_no_place(tmp_path):
    assert RI._layer_words(_doc(tmp_path), {"page": 1, "layer_words": ["|"]}) == "several places"


def test_layer_words_not_on_the_page(tmp_path):
    assert RI._layer_words(_doc(tmp_path), {"page": 1, "layer_words": ["PathChat"]}) is None


def test_boxes_one_place_per_line(tmp_path):
    nbs = [[0.1, 0.9, 0.12, 0.92], [0.2, 0.9, 0.22, 0.92], [0.1, 0.2, 0.15, 0.22]]
    places = RI._boxes(_doc(tmp_path), {"page": 1, "layer_boxes": nbs})
    assert len(places) == 2
    assert abs(places[1][1].x0 - 40) < 1 and abs(places[1][1].x1 - 88) < 1


def test_not_prose():
    assert run._not_prose("$$\nx = 1\n$$")
    assert run._not_prose("| a | b |\n| --- | --- |")
    assert run._not_prose("<table><tr><td>a</td></tr></table>")
    assert run._not_prose("![](images/a.jpg)")
    assert not run._not_prose("Given logits o and temperature T > 0,")
    assert not run._not_prose("a | b is a ratio")
    assert not run._not_prose("|x| is the absolute value of x, and\n|y| that of y")
    assert run._not_prose("| a | b |\n|:---|---:|\n| 1 | 2 |")


def _sub(left, prim, oxr, right):
    return {"id": "d1", "left": left, "right": right, "primary_toks": prim, "oxr_toks": oxr}


def test_settled_later_across_an_equation():
    # PTA-716 p9: the comma written before a display equation; the neighbours stand on both sides of it
    md = "Given logits o and temperature T > 0,\n\n$$\np = q\n$$\n\nT is optimized"
    s = _sub(["temperature", "T", ">", "0"], ["."], [","], ["T", "is", "optimized"])
    keep, n = run._settled_later(md, [s], [{"kind": "disagreement", "id": "d1"}])
    assert n == 1 and keep == []
    # the equation ends with its own period: held as the reader wrote it, it is no place the primary's '.' went
    md = "Given logits o and temperature T > 0,\n\n$$\np = q.\n$$\n\nT is optimized"
    md0 = "Given logits o and temperature T > 0 .\n\n$$\np = q.\n$$\n\nT is optimized"
    assert run._settled_later(md, [s], [{"kind": "disagreement", "id": "d1"}])[1] == 0
    assert run._settled_later(md, [s], [{"kind": "disagreement", "id": "d1"}], md0)[1] == 1


def test_not_settled_where_the_primary_went_into_a_skipped_paragraph():
    # review 11-18: the primary reading's token inside the equation between the neighbours keeps the issue open
    md = "The bound is\n\n$$\na = 1\n$$\n\nand the rest follows"
    s = _sub(["The", "bound", "is"], ["1"], [], ["and", "the", "rest"])
    keep, n = run._settled_later(md, [s], [{"kind": "disagreement", "id": "d1"}])
    assert n == 0 and len(keep) == 1
