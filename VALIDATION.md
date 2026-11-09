# Prototype validation — 2026-11-10

Environment: Apple M2 Ultra, 192 GB RAM; MinerU 4.1.7; Quarto; Ollama Qwen3 4B. Private library and reports are outside Git.

## Corpus and findings

- **11 Zotero papers, 207 pages**, processed in full. A 479-page book accidentally included by Zotero's item classification was excluded from this journal-article evaluation.
- **One independent publisher sample, 8 pages**, CC BY 4.0, used for the public demo.
- Extracted page counts match the originals for all 12 documents; no empty parsed pages were found.
- Original page 2 was visually inspected for every document, including single-column text, two-column text, Japanese text, scanned typescript, figures and displayed equations. Representative displayed equations were compared with their extracted TeX. This is sampled inspection, not a full human transcription audit.
- The private papers' per-document average text-layer token overlap ranged from **0.857 to 0.993**. This is a diagnostic of word/character retention, not an accuracy score: equations, ligatures, reading order, OCR and PDF text-layer defects affect it.
- **3,099 displayed and inline math expressions** were parsed with MathJax. **Six expressions in two private papers** produced syntax errors, including unmatched array environments and duplicate equation tags. Those displayed equations use their original image in the rebuilt reader; the extracted TeX is retained. A browser-side error fallback also uses the original equation image when available.
- Two long possible body-text/caption misclassifications were found in one private paper. Ambiguous long captions now remain in the main column and are logged in `document.json`, rather than being hidden in the right margin.
- Qwen3 4B was tested for whitespace-only corrections. Content-changing proposals are rejected; equations and numbers are not sent for correction. This corpus did not establish a reason to enable LLM rewriting by default. Original MinerU output remains immutable.

## Automated checks

- 13 Python tests: deduplication, invalid input rejection, upload API, cross-origin and host checks, traversal, ZIP extraction boundary, preservation of TeX characters, rejection of model changes to numbers/negation, and executable-cell removal.
- Six DOM assertions: source links, original page image, bounding-box highlight, close action, enlarged figure and gallery. These use jsdom, not a browser.
- Public sample's HTML image/script/style references resolve locally; no external rendering dependency remains. MathJax, fonts and source-page images are bundled.
- Private data is excluded by location and a fixed publisher-sample export allowlist, not just `.gitignore`.

## Limits

Browser control is disabled by the host's Work settings. Actual browser rendering, margin collision behavior and narrow-screen appearance could not be visually inspected in this session. DOM tests and static checks do not substitute for that inspection. A matching browser test should be run when browser access is enabled.

The source page viewer is the fallback for uncertain OCR, symbol identity, reading order and caption association. Syntax-valid equations can still be semantically wrong. Whole-corpus semantic fidelity is not claimed. Private per-paper reports remain under the configured library directory and are not copied to the public demo.
