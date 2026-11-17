"""A MinerU page that comes with its index only (no blocks) reads as an empty page, not a crash (11-17, PTA-462)."""
import json
from mineru_plus.readers import mineru as MR


def test_page_without_blocks(tmp_path):
    (tmp_path / "middle_json.json").write_text(json.dumps({"pages": [
        {"page_idx": 0, "blocks": [{"type": "image_body", "bbox": [0, 0, 1, 1], "image_path": "a.jpg"}]},
        {"page_idx": 1}]}))
    (tmp_path / "structured_content.json").write_text(json.dumps({"pages": [{"page_idx": 0, "blocks": []}, {"page_idx": 1}]}))
    figs = MR.figure_bodies(tmp_path)
    assert [f["page"] for f in figs] == [1]
    assert MR.pages(tmp_path) == {1: [], 2: []}
