# mineru_plus 0.5.6 — frontiers_bcnb.pdf

11 pages; every page has a text layer.
Readers: oxr, mineru.
Figure transcriptions: 4 (figures.json), 4 moved out of full.md; 0/215 of their tokens are printed in the figure's text layer, the rest is the reader's reading of the graphic and unverified; 3 figures have no text layer.

## Measured on this document
- dropped: 7 places where the text layer has characters the primary lacks: jev reads the layer's form on the page at 7 (5 written, 3 of them inline formulas the primary misread, retyped from the layer), not at 0 (the layer is wrong there), 0 undecided
- reflow: 11 paragraphs end mid-sentence before the next text block: 8 joined with their continuation (1 with figures, tables or footnotes moved after the paragraph); 3 not continued by the next block (3 of them because it starts a new sentence: a heading or author line typed as text), 0 undecided; 0 open issues
- tables: 2 tables checked against the text layer cell by cell: 3 look-alike characters and 0 spaces between a cell's glued lines written from the layer, 0 cells rewritten (OXR or jev settled the layer's reading); 2 tables equal the layer, 0 with open cells
- unread: 17 primary tokens OXR read elsewhere on the page (another order or a table); 3 tokens with letters or digits in 3 runs OXR did not read: jev reads them in the page at 3 runs (3 tokens), reads something else at 0, undecided 0; 0 found by jev in the figure they caption (the figure is a picture); not placed by the text layer 0, on pages without a layer 0 (those jev does not confirm, the undecided and the unplaced are open issues with their crops)
- characters: 8806/8903 primary tokens agree with OXR; 29 corrections written (3 line-break spellings), 2 left open; acceptance passed; 0 of 7 passages for the page judges had no crop jev found to show them whole (not judged, open); 1 of the open ones settled by later steps, 1 remain open
- tables_without_layer: 0 tables without text-layer words in their box: rows and cells equal OXR in 0; the rest are open issues with a crop
- equations: 0/0 display equations equal OXR's LaTeX after canonical spelling; of the rest 0 print the letters and digits of the text layer in their box (characters confirmed, not the layout); 0 open
- coverage: 1 text-layer characters missing from their block (0 repeated on many pages counted per page), 0 layer words in no block, of 6784 layer words; 5 dashes or middle dots written as ASCII look-alikes (line-break hyphens, invisible characters, figure-internal text and repaired characters excluded)
- margins: 45 page headers, footers, page numbers and side notes the reader left out of its markdown written to the closing section; 20 equal the text layer, 0 differ (open issues), 0 on pages without a text layer
- formula_spacing: 25 formulas respelled without the spaces LaTeX ignores ('0 . 0 1 5' as '0.015', '\mathrm { A U C }' as '\mathrm{AUC}')
- sections: sections.json and quote_index.json in the pdf_parser schema

## Backends of this run
- primary_reader: gateway (tool mineru, tier advanced)
- second_reader: gateway (tool oxr)
- decision_judge: gateway (model d3-ultra)
- page_judge: agy (command agy-min, model gemini-3.8-flash-high)
Calibration measured with: primary_reader gateway (tool mineru, tier advanced); second_reader gateway (tool oxr); decision_judge gateway (model d3-ultra); page_judge agy (model gemini-3.8-flash-high).

## How far the checks can be trusted (tool calibration)
- readers independent of the text layer (10-28, planted hidden layer, 73 numbers): MinerU advanced copies the layer on born-digital pages (48 layer / 0 image in text blocks); OXR reads the image (51 / 0)
- character check recall (10-28, 216 planted text-layer errors on 18 pages of 9 papers): in compared text 191 surfaced as disagreements but 3; jev chose the printed side for 182, 0 wrong; headers, footers, page numbers, equations not compared (12). Only errors on the layer side were planted, so this does not measure pages that print a typo
- character judge (10-28, 106 items: 34 printed typos with an ordinary layer, 12 real, 60 planted layer errors): Gemini on numbered sheets of tight crops, both option orders: 0 wrong among decided; undecided 9/34, 4/12, 5/60 (undecided items are open issues with their crop). jev and deepseek-flash chose the corrected spelling of printed typos in 25-40% of decided cases and are not used for characters
- jev first for characters (10-29, 31 documents, 325 character items): jev asked per reading whether the crop prints exactly it decided 104; where Gemini (0.3.0) had decided the same item, 84 of 86 agree; the 2 others are printed spellings jev took for the common one ('Interpetation', 'biomedcentral'), so a letters-only difference jev settles against the text layer goes to Gemini
- crops for the character judges (10-30, 396 passages of 37 papers): each crop is checked by jev to show the two words before, the disputed part and the two words after, whole, before any judge sees it; 380 passed (363 at once, 17 after widening or on the side in the same block); the 16 that did not were inspected: 8 symbols the page does not print or text in figures and logos, 3 with their context in another block, 3 crops cut or misplaced, 2 crops that do show the passage (jev wrong). Of 26 crops passed that an earlier, stricter check had refused, 25 show the passage, 1 shows the same words in the next reference entry
- second reader (10-29, 203 planted errors on 9 papers): OXR found 187, MiniCPM-OCR 186, both together 188: one second reader is enough; jev alone on lines (no second reader) rejected 36% of correct lines, so one is needed
- dropped content (10-29, 9 papers): jev on red-box crops 'prints exactly «layer words»': 101 findings labelled on the page, 95 decided, 3 wrong; written only where the primary's own characters around place it (49 written, checked on crops; one wrong, a fraction's denominator written into the next line, led to the same-line rule)
- inline formulas (10-29, 31 documents): MinerU reads inline $...$ from the image even on born-digital pages: 30 misread formulas ('pm' for 'µm', 'ANN' for 'ANC', 'M×ED' for 'MIXED', 'I56' for '156', 'X^2' for a printed 'χ2') retyped from the layer with raised and lowered glyphs as <sup>/<sub>, only where every difference inside is a printed finding; doubtful ones checked on the page, all right. Stacked scripts, fractions and roots are not retyped
- reading order (10-29, 9 papers, about 120 pages checked on page images): block order wrong at 2 places, both at figures (a caption split over two columns; body text typed as a figure note); sentences cut by page or column breaks, with floats between, joined by jev: of 240 joins in 31 documents the 44 with an upper-case continuation all right, 25 sampled lower-case ones all right; one wrong join (a heading typed as text) led to the rule that only a paragraph skips blocks
- OXR (10-28): OXR itself corrects about half of printed letter typos and turns middle dots into periods; where both readings agree on a corrected form nothing is flagged
- line-break spelling (10-28, 110 items labelled by document usage): jev decided 109, 108 right
- text-layer coverage, equations (10-28, 9 papers): coverage found the dropped italic journal names in page footers (2 papers); 8 display equations all agree with OXR after canonical LaTeX. 10-29, 31 documents: 29 display equations (pathology papers have few), 18 equal OXR, 1 differed by a tag only, 10 figure labels OXR did not read; rendering both readings for a visual judge was not built for so few
- tables (10-29, 87 tables of 31 documents on pages with a text layer): MinerU's cells aligned to the layer's characters (99.4% in content-stream order); differences were look-alikes (533: ✘ written ×, ✔ ✓, – -, · .), a cell's lines glued (206), 3 misread words ('tisse'); jev took MinerU's 'tisse' for printed, so OXR's table decides first. Cell swaps planted in 84 tables (168, a cell with its right or lower neighbour) found 161. The earlier comparison of structure with OXR was mostly noise (OXR splits multi-line cells; 'F 1' vs 'F1')
- real-page edits (10-28, 31 documents: 9 papers, 15 supplements, 7 new papers incl. a 6-page scan): 47 character edits checked on the page image: all right after two rules taken from Gemini's errors (I/l and O/0 are not judged: same glyph in sans-serif; runs of one repeated character, '3200003', are decided by the text layer: Gemini miscounted in both orders); 200 line-break spellings, one partial ('dual- and')
- omissions (10-28, same 31 documents): 10 runs the text layer and OXR both have between the same three neighbours on each side and the primary dropped ('vs', compound hyphens, a period, an em dash); requiring only the two anchors let one wrong run in on a page whose layer runs in another order
- text-layer coverage (10-28, 9 papers, 180 findings checked by hand): about two thirds are content the primary dropped (journal names in footers, citation superscripts, a rotated table caption, 'vs', brackets inside formulas); the rest are pages whose layer is wrong (font maps such as '0:05' for 0.05, radical glyphs), which coverage cannot tell apart

## Not checked
- page headers, footers and page numbers: checked against the text layer only (coverage); a broken layer there is not caught (OXR output has no headers or footers)
- figure transcriptions beyond the printed labels (figures.json): the reader's estimate

## Open issues: 1 (issues.json)
