# MinerUPlus

English | [中文](README_zh.md)

**A paper-PDF parser for AI agents that checks its own output.**
It compares every word with the PDF's text layer and with a second, independent reading of the page image.
It writes back the corrections it can settle, records each one with its source, and returns everything it
could not settle as a list of issues, each with the page, both readings and a crop of the page.

An agent that quotes a paper, extracts a sample size or a p-value, or builds a dataset from figures needs to know
which parts of the markdown it can trust. Current parsers return one reading and no statement of where it may be
wrong. MinerUPlus returns the reading together with that statement.

---

## A real run

Paper: Xu et al., *Predicting Axillary Lymph Node Metastasis in Early Breast Cancer Using Deep Learning on Primary
Tumor Biopsy Slides*, Frontiers in Oncology 2021 ([doi:10.3389/fonc.2021.759007](https://doi.org/10.3389/fonc.2021.759007),
CC BY 4.0), 11 pages. Every file of this run is in [`examples/frontiers_bcnb/`](examples/frontiers_bcnb/), with the
reader's untouched markdown next to the result, so you can compare them line by line.

**Sample sizes.** Here the reader got the numbers wrong:

![page crop](examples/frontiers_bcnb/crops/d0032.png)

| | text |
|---|---|
| MinerU (advanced) | `V, validation cohort $( n = 2 7 0 ) ; 1 - T ,$ independent test cohort $( n = 2 7 8 ) ; A L N ,$` |
| MinerUPlus | `V, validation cohort $( n = 210 ) ; I - T ,$ independent test cohort $( n = 218 ) ; A L N ,$` |

- `270 → 210`: the second reader (OXR) disagreed, and the page judge read the crop.
- `278 → 218`: the decision judge confirmed that the crop prints exactly `218`.
- `1 → I`: settled by the text layer.
- The spacing inside the numbers was removed, so a search for `n = 210` now finds it.

**p-values read as ρ.**

![page crop](examples/frontiers_bcnb/crops/d0001.png)

| | text |
|---|---|
| MinerU (advanced) | `density $\langle \rho   =   0 . 0 1 5 \rangle$ , circumference $\left( \rho   =   0.009 \right)$` |
| MinerUPlus | `density $\langle (p = 0.015 \rangle$ , circumference $\left( p = 0.009 \right)$` |

`ρ → p` was fixed. The angle brackets are still wrong. The text layer prints `(p = 0.015)`, but MinerUPlus could not
place that edit safely inside the formula, so it is left as an open issue with its crop for the calling agent
([`issues.json`](examples/frontiers_bcnb/issues.json)).

**An item it does not decide.**

![page crop](examples/frontiers_bcnb/crops/d0043.png)

MinerU read `Estained` and OXR read `E - stained`; the page prints `H&E-stained` across a line break. The crop shows
only the second line, so the page judge chose neither reading. The item goes back to the caller as an open issue,
with the crop.

**The report** ([`report.md`](examples/frontiers_bcnb/report.md)) starts like this:

```
# mineru_plus 0.5.5 — frontiers_bcnb.pdf

11 pages; every page has a text layer.
Readers: mineru, oxr.
Figure transcriptions: 4 (figures.json), 4 moved out of full.md; 0/215 of their tokens are printed in the figure's ...

## Measured on this document
- dropped: 9 places where the text layer has characters the primary lacks: jev reads the layer's form on the page ...
- reflow: 10 paragraphs end mid-sentence before the next text block: 8 joined with their continuation (1 with figu ...
- tables: 2 tables checked against the text layer cell by cell: 3 look-alike characters and 0 spaces between a cel ...
- characters: 8806/8903 primary tokens agree with OXR; 27 corrections written (3 line-break spellings), 1 left ope ...
- formula_spacing: 28 formulas respelled without the spaces LaTeX ignores ('0 . 0 1 5' as '0.015', '\mathrm { A U ...
...
## Not checked
- page headers, footers and page numbers: checked against the text layer only (coverage); a broken layer there is ...
- figure transcriptions beyond the printed labels (figures.json): the reader's estimate

## Open issues: 8 (issues.json)
```

The report goes on to list the backends of the run and the calibration of each check.

---

## Why

Modern document parsers read the page image with a vision model. On born-digital papers this produces failures
that look like correct text:

| Failure (seen in real runs) | Example | Why an agent cares |
|---|---|---|
| Characters misread inside inline math | `$\mu m$` read as `pm`, `ANC` as `ANN`, `156` as `I56`, `χ2` as `X^2` | wrong units and values in extraction |
| Numbers spelled with LaTeX spaces | `$( n = 2 1 0 )$` | a search for `n = 210` finds nothing |
| Text the reader dropped | journal names in italic footers, affiliation lines | quotes cannot be verified against the source |
| Printed typos "corrected" by the model | `microevironment` printed, `microenvironment` returned | verbatim quotes do not match the paper |
| Reading order broken at floats | a sentence cut by a figure and continued two blocks later | broken sentences, merged captions |
| Figure transcriptions mixed into body text | chart labels and model guesses inside the prose | unverified content presented as text |

None of these failures raises an error. The parser's output looks complete.

## What MinerUPlus does

```
            PDF
             │
   ┌─────────┼──────────────┐
   ▼         ▼              ▼
primary   second reader   PDF text layer
reader    (page image     (born-digital
(MinerU)   only)           pages)
   │         │              │
   └──── token-level comparison, per page ────┐
                                              ▼
           disagreements, dropped text, unread text, tables, formulas, reflow
                                              │
                       settled by evidence first (text layer: exact context → page words → document usage),
                       then by judges on page crops (both option orders must agree)
                                              │
                  ┌───────────────────────────┴───────────────────────────┐
                  ▼                                                       ▼
   settled: written into full.md, each edit                 not settled: issues.json, with page,
   recorded in checks/edits.json with its source             both readings and a crop of the page
                  │
   acceptance: the token multiset of the repaired markdown must differ from the
   original by exactly the tokens the edits declare
```

Design rules:

- **Evidence before judges.** If the text layer decides a disagreement, no model is asked.
- **Judges answer closed questions on the page image.** Every question is asked in both option orders, and an
  item counts as decided only when both orders agree.
- **"Undecided" is a valid answer.** It goes back to the calling agent with a crop instead of being guessed.
- **Report what was not checked.** Figure transcriptions beyond printed labels, and pages with no text layer, are
  listed in the report as unchecked.

## Output

One PDF in, one directory out:

| File | Content |
|---|---|
| `full.md` | the parse: primary reading with settled corrections written in and figure transcriptions moved out |
| `issues.json` | what the run could not settle, for the calling agent: kind, page, both readings, crop path |
| `report.md`, `report.json` | the quality statement of the run: what was compared, what was corrected, what was not checked, tool calibration |
| `sections.json` | sections with title, level (from the heading's numbering) and page range |
| `quote_index.json` | per-section text and whitespace-normalised text, for verbatim quote checks |
| `figures.json` | figure and chart transcriptions, with how much of each is printed text and how much is the reader's estimate |
| `checks/` | every disagreement with its route, verdict and source; `edits.json`; judge requests and crops |
| `readers/` | the untouched output of both readers |

In the outputs, `jev` names the decision judge and `Gemini` the page judge (the components we
run).

Example of an issue:

```json
{"kind": "text layer not in the parse", "why": "printed (jev); not placed, edit by hand",
 "page": 7, "layer": "(⇠20,000", "parse": "(~20,000", "crop": "/abs/path/out/checks/dropped/crops/r7.4.1.png"}
```

Example of an edit:

```json
{"id": "d0009", "page": 1, "route": "characters", "by": "jev (exactly printed)",
 "old": "Lu<sup>5</sup>,⇤,", "new": "Lu<sup>5</sup>,\\*,"}
```

## Compared with other open-source parsers

MinerUPlus is not a new reading model. It runs a reader (currently MinerU) and checks that reader's output. The
comparison below is about what each tool **returns to the caller**, not about reading accuracy. On reading accuracy
see [OmniDocBench](https://github.com/opendatalab/OmniDocBench), where MinerU 2.5 and PaddleOCR-VL rank near the top.

| | MinerU | Marker | Docling | olmOCR | PaddleOCR-VL | **MinerUPlus** |
|---|---|---|---|---|---|---|
| Output checked against the PDF text layer | – | – | – | layer used as prompt input, not as a check | – | per token |
| Second independent reading of the page | – | – | – | – | – | yes |
| Quality signal per run | – | – | model confidence scores (layout, OCR, parse) | – | – | what was compared, corrected, not checked |
| List of unresolved places, with page crops | – | – | – | – | – | `issues.json` |
| Each correction recorded with its source | – | LLM mode rewrites without a record | – | – | – | `edits.json` |
| Printed typos kept as printed | model-dependent | model-dependent | model-dependent | model-dependent | model-dependent | checked against the text layer |
| Sections with page ranges, quote index | – | – | document tree | – | – | `sections.json`, `quote_index.json` |

Docling's confidence scores are the closest feature. They are the models' own confidence, averaged per page,
and they are not checked against independent evidence. A garbled page can still be graded "good"
([docling-studio #360](https://github.com/scub-france/docling-Studio/issues/360)).

## Measured so far

These numbers come from our own test sets: biomedical and computer-science papers in English, born-digital.
They are not a benchmark.

- **Recall of character errors** (216 errors planted in the text layer of 18 pages from 9 papers): 191 surfaced as
  disagreements; the judge chose the printed side for 182 of them, with 0 wrong.
- **Page-reading judge** (106 items: 34 printed typos, 12 real disagreements, 60 planted errors): 0 wrong among
  the items it decided. Undecided items (18) became issues.
- **Second reader**: of 203 planted errors on 9 papers, OXR found 187, MiniCPM-OCR 186, and both together 188. One
  second reader is enough, but one is needed: a judge alone, with no second reader, rejected 36% of correct lines.
- **Held-out papers** (6, not used during development): acceptance passed on 6/6. Of 87,624 compared tokens, 83,338
  agreed with the second reader.
- **Time**: about 4 minutes for a 27-page paper. About 2:40 of this is spent in the two readers; the checks take
  about 1 minute.

The full calibration is printed in every `report.md`.

## Limitations

- **Born-digital PDFs are where it is strongest.** On scanned pages there is no text layer, so the checks rely only
  on the second reader and the judges. The report lists these pages.
- **Figure contents are not verified** beyond the labels printed in the text layer.
- **Display equations** are compared after canonical LaTeX; complex layouts (stacked scripts, fractions) are not
  retyped.
- **It is slower than a single reader**, because the PDF is read twice and judges are called.

## Requirements

- Python ≥ 3.10, `pymupdf`, `pillow` (`pip install .`)
- Four external components, one per role. Each role is chosen in a config file. Any implementation that meets
  the role's requirement can be plugged in:

| Role | Requirement | Backends |
|---|---|---|
| `primary_reader` | structured block output per page with bounding boxes and block types (MinerU 4.x `structured_content.json`) | `mineru_kit` (the `mineru-kit` CLI), `command` (any program that writes the documented files), `gateway` |
| `second_reader` | reads the page **image** and not the text layer. We test this by planting a falsified hidden text layer: a valid second reader must print what the page shows. | `openai_vlm` (any OpenAI-compatible vision model), `command`, `gateway` |
| `decision_judge` | multimodal; answers closed choices with option probabilities | `openai` (any OpenAI-compatible endpoint), `gateway` |
| `page_judge` | multimodal; reads characters literally (does not autocorrect printed typos) | `openai`, `agy` (a CLI agent that reads image files) |

The file formats each backend must produce are documented in `mineru_plus/backends/__init__.py`. How you deploy
a backend is up to you.

### What we run

All results in this README come from this setup:

| Role | Component | Public source |
|---|---|---|
| `primary_reader` | MinerU 4.1, tier advanced | [opendatalab/MinerU](https://github.com/opendatalab/MinerU) |
| `second_reader` | OXR 1.0 | [SoMarkAI/OXR](https://github.com/SoMarkAI/OXR) |
| `decision_judge` | d3-ultra (System One protocol) | [vllm-sr/d3-ultra](https://huggingface.co/vllm-sr/d3-ultra) |
| `page_judge` | Gemini 3.8 Flash, thinking high | Gemini API |

We reach the first three through our own tool gateway (`gateway` backend; `config.gateway.example.json`), and
Gemini through a CLI agent (`agy` backend).

## Configuration

Copy `config.example.json` to `mineru_plus.json` and fill in your services:

```json
{
  "primary_reader": {"backend": "mineru_kit", "command": "mineru-kit", "tier": "standard"},
  "second_reader":  {"backend": "openai_vlm", "base_url": "http://localhost:8000/v1", "model": "your-vision-model",
                     "api_key_env": "SECOND_READER_KEY"},
  "decision_judge": {"backend": "openai", "base_url": "https://api.example.com/v1", "model": "your-model",
                     "api_key_env": "JUDGE_KEY"},
  "page_judge":     {"backend": "openai", "base_url": "https://api.example.com/v1", "model": "your-vision-model",
                     "api_key_env": "JUDGE_KEY"}
}
```

Credentials never go into the file: `api_key_env` names the environment variable that holds the key. The file is
found via `--config PATH`, else `$MINERU_PLUS_CONFIG`, else `./mineru_plus.json`. A run without a second reader
still completes, and its report says the characters were not checked.

## Usage

```bash
pip install .
mineru-plus paper.pdf out/ --config mineru_plus.json
```

The command prints `report.md` and writes the output directory. Readers' outputs are cached in `out/readers/`, and
decision-judge answers are cached by question hash, so a rerun only asks what changed.

## Roadmap

- [ ] Unwrap prose that the reader typed as math (`$( n = 210 ) ; I - T ,$`)
- [ ] Front-matter boxes (journal banners, "Edited by") kept out of `sections.json`

## License

Apache-2.0 (see `LICENSE`). `mineru_plus/check/confusables.txt` is derived from Unicode TR39 data under the
[Unicode License](https://www.unicode.org/license.txt).
