# Example: Frontiers in Oncology 2021 (CC BY)

Source: Xu F, Zhu C, Tang W, Wang Y, Zhang Y, Li J, Jiang H, Shi Z, Liu J and Jin M (2021). *Predicting Axillary
Lymph Node Metastasis in Early Breast Cancer Using Deep Learning on Primary Tumor Biopsy Slides.* Front. Oncol.
11:759007. [doi:10.3389/fonc.2021.759007](https://doi.org/10.3389/fonc.2021.759007). The article is distributed
under the [Creative Commons Attribution License (CC BY)](https://creativecommons.org/licenses/by/4.0/). The text
and page crops below are derived from it. The PDF itself is not included; download it from the DOI.

The run used MinerUPlus 0.5.6 with the setup described in the main README ("What we run").

| File | Content |
|---|---|
| `mineru_markdown.md` | the primary reader's (MinerU's) markdown, untouched |
| `full.md` | the result |
| `report.md`, `report.json` | the quality statement of the run |
| `issues.json` | the one place left open for the calling agent, with its crop |
| `checks/edits.json` | the 29 edits, each with its source (`by`) |
| `checks/disagreements.json` | every disagreement between the two readers, with route and verdict |
| `sections.json`, `quote_index.json`, `figures.json` | sections with pages, quote index, figure transcriptions |
| `crops/` | the page crops referenced by the files above |

Changes made for publication: absolute paths in the files were shortened to paths inside this folder. Of the run's
check files, only the crops referenced here are included.
The paper's figure images, which the markdown files link to, are not included.
