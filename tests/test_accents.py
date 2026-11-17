"""Accents the reading has that the text layer does not print are raised, once per block."""
import json
import pymupdf
from mineru_plus.check import accents as AC


def _doc(tmp_path, text, content):
    pdf = tmp_path / "a.pdf"
    d = pymupdf.open(); pg = d.new_page(width=400, height=200)
    pg.insert_text((40, 60), text, fontsize=11)
    d.save(str(pdf))
    m = tmp_path / "mineru"; m.mkdir()
    (m / "structured_content.json").write_text(json.dumps({"pages": [{"page_idx": 0, "blocks": [
        {"type": "text", "bbox": [0.05, 0.1, 0.95, 0.5], "content": content}]}]}))
    return pdf, m


def test_raised_where_the_layer_prints_no_accent(tmp_path):
    pdf, m = _doc(tmp_path, "where N is the number of tiles", r"where $\bar { N }$ is the number of tiles")
    issues, n = AC.check(pdf, m, r"where $\bar { N }$ is the number of tiles", tmp_path / "w")
    assert len(issues) == 1 and issues[0]["page"] == 1 and r"\bar" in issues[0]["parse"] and n["raised"] == 1


def test_not_raised_where_the_layer_prints_it(tmp_path):
    pdf, m = _doc(tmp_path, "where ¯N is the number of tiles", r"where $\bar { N }$ is the number of tiles")
    issues, _ = AC.check(pdf, m, r"where $\bar { N }$ is the number of tiles", tmp_path / "w")
    assert issues == []


def test_no_formula_accent_nothing_to_do(tmp_path):
    pdf, m = _doc(tmp_path, "where N is", r"where $N$ is, \barrier")
    issues, n = AC.check(pdf, m, r"where $N$ is, \barrier", tmp_path / "w")
    assert issues == [] and n["blocks with accents in formulas"] == 0
