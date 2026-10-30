"""Second reader. The reader is a backend (mineru_plus/backends), chosen in the config file under "second_reader". It
reads the page image only, never the text layer: with a falsified hidden text layer (planted test 10-28, local and free
API alike) it printed 51 of 73 numbers as on the page and 0 from the layer.

pages() reads the documented pages.json (the openai_vlm and command backends), or the raw OXR JSON that the gateway
backend keeps (one file, or the chunked layout chunks/chunk_<k>_*.json). The gateway's default output has no page headers
or footers, and its tool-call does not pass the option that keeps them."""
import json, re
from pathlib import Path
from .. import backends


def read(pdf, out_dir):
    out_dir = Path(out_dir)
    if not (out_dir / "reader_meta.json").exists():
        backends.get("second_reader").read(Path(pdf), out_dir)
    return json.loads((out_dir / "reader_meta.json").read_text())


def pages(out_dir):
    """{page: [block, ...]}; each block has a type and a content (the checks read no other field)"""
    d = Path(out_dir)
    if (d / "pages.json").exists():
        return {p["page"]: p["blocks"] for p in json.loads((d / "pages.json").read_text())["pages"]}
    files = sorted(d.glob("*.pdf.json"))
    if files:
        pg = json.loads(files[0].read_text())["data"]["result"]["outputs"]["json"]["pages"]
    else:
        pg = []
        for f in sorted((d / "chunks").glob("*.json"), key=lambda x: int(re.search(r"chunk_(\d+)", x.name).group(1))):
            pg += json.loads(f.read_text())["data"]["result"]["outputs"]["json"]["pages"]
    return {i + 1: p["blocks"] for i, p in enumerate(pg)}
