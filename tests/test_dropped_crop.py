import tempfile, unittest
from pathlib import Path
import pymupdf
from mineru_plus.check import gemini as G


class RotatedPageCrop(unittest.TestCase):
    # 11-17, PTA-478 MOESM1 p12 (rotated 90): the dropped check clipped unrotated word boxes with the displayed page
    # rect; the crop is now drawn on a copy of the page and rendered upright
    def test_rotated_word_crop_holds_the_word(self):
        d = pymupdf.open(); pg = d.new_page(width=792, height=612)
        pg.insert_text((680, 40), "Figure", fontsize=14)
        pg.set_rotation(90)
        w = [x for x in pg.get_text("words") if x[4] == "Figure"][0]
        box = pymupdf.Rect(w[:4])
        self.assertGreater(box.x1, pg.rect.width)            # unrotated x beyond the displayed width
        clip = (box + (-10, -8, 10, 8)) & (pg.rect * pg.derotation_matrix)
        self.assertFalse(clip.is_empty)
        d2 = pymupdf.open(); d2.insert_pdf(d, from_page=0, to_page=0); p2 = d2[0]
        p2.draw_rect(box + (-1.5, -1.5, 1.5, 1.5), color=(1, 0, 0), width=0.8)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.png"
            G._image(p2, clip, 220).save(str(out))
            pix = pymupdf.Pixmap(str(out))
            dark = sum(1 for i in range(0, len(pix.samples), pix.n) if pix.samples[i] < 100)
            self.assertGreater(dark, 50)                        # the word is in the crop, not a blank page
        self.assertEqual(len(d[0].get_drawings()), 0)           # the page itself is not drawn on


if __name__ == "__main__":
    unittest.main()
