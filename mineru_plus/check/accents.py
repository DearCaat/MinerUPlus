"""Accents the reading's formulas have that the page's text layer does not print.

The primary reads formulas from the image and puts accents on letters the page prints plain ('\\bar { N }' for N,
'10,\\dot{0}00', '\\vec { V } ( t )', '\\tilde { P } = 2.837'), or reads a symbol as an accented letter
('\\hat { \\Sigma } yte' for IncuCyte, '\\widehat { w }' for a circled V). The alignment with the layer does not see
them: accents are not compared there (dropped.py), and the letter under one is printed. A text layer prints an accent
as a glyph of its own ('¯', 'ˆ', '˙', '˜', '→') or as a combining mark. A block whose formulas hold more accent
commands than its layer words hold accents is an open issue with its formulas and a crop; nothing is written, since
a layer can leave out an accent the page prints (PTA-570: wide hats over m and M printed, none in the layer).
11-17, the 69 parses of the paper line (dev_1114 and work): 28 blocks raised, looked at on the page: 24 with an
accent the page does not print or a symbol misread as an accented letter, 4 where the layer leaves out printed
accents. Three of the 24 had been edited by the paper line's L1-3, found only by chance near another issue."""
import re, unicodedata
from pathlib import Path
import pymupdf
from ..readers import mineru as MR
from .. import layer as LY
from . import coverage as CV, dropped as DR

ACCENT = re.compile(r"\\(?:hat|widehat|tilde|widetilde|bar|dot|ddot|check|breve|acute|grave|vec)(?![A-Za-z])")
FORMULA = re.compile(r"\$[^$]+\$")
# what a text layer prints for an accent: spacing accents, arrows over a letter, and combining marks
LAYER_ACCENT = set("ˆ˜¯˙¨ˇ˘´`^~→⃗")


def _layer_accents(words):
    s = unicodedata.normalize("NFD", " ".join(words))
    return sum(1 for c in s if c in LAYER_ACCENT or unicodedata.combining(c))


def check(pdf_path, mdir, md, work):
    """(issues, counts). Each block is taken as it stands in md (earlier edits included) where found there once."""
    pdf = pymupdf.open(pdf_path)
    A = MR.pages(mdir)
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    issues, n = [], {"blocks with accents in formulas": 0, "raised": 0}
    for pg_no in sorted(A):
        pg = LY.page(pdf, pg_no - 1)
        words = LY.words(pg)
        if not words:
            continue
        centres = []
        for w in words:
            nb = CV._norm_box(pymupdf.Rect(w[:4]) * pg.rotation_matrix, pg)
            centres.append((((nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2), w[4]))
        for uid, typ, part in MR.units(A[pg_no]):
            if not part.get("bbox"):
                continue
            raw = part.get("content") or ""
            cur = DR.locate(md, raw) or raw
            forms = [f for f in FORMULA.findall(cur) if ACCENT.search(f)]
            n_par = sum(len(ACCENT.findall(f)) for f in forms)
            if not n_par:
                continue
            lay = [t for c, t in centres if CV._inside(c, part["bbox"])]
            if not lay:
                continue                       # no layer words in the block: nothing to compare with
            n["blocks with accents in formulas"] += 1
            n_lay = _layer_accents(lay)
            if n_lay >= n_par:
                continue
            b = part["bbox"]
            W, H = pg.rect.width, pg.rect.height
            clip = (pymupdf.Rect(b[0] * W, b[1] * H, b[2] * W, b[3] * H) + (-4, -4, 4, 4)) & pg.rect
            crop = work / f"a{pg_no}.{uid}.png"
            if not clip.is_empty:
                pg.get_pixmap(clip=clip, dpi=170).save(str(crop))
            n["raised"] += 1
            issues.append({"kind": "accent in the parse, not in the text layer", "page": pg_no,
                           "why": f"{n_par} accents in the parse's formulas here, {n_lay} in the text layer: check each "
                                  f"accent on the page (the layer can leave out a wide accent the page prints)",
                           "parse": " … ".join(forms), "crop": str(crop) if not clip.is_empty else None})
    return issues, n
