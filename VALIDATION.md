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
- Qwen3 4B now selects ambiguous heading levels, paragraph-join modes, and minimal figure scopes. It receives extracted caption/prose context and returns constrained JSON with existing IDs, never replacement scientific text. Mechanical rules run first; scope selections are bounded to adjacent paragraphs in the same subsection. Inputs, decisions and errors are retained privately. Original MinerU output remains immutable.
- Rebuilt headings use real Quarto section nesting. Figures follow restored paragraphs in source order. Native figure/equation links and citeproc references support repeated margin citations, including Japanese superscript citation marks. Original equation numbers are restored after rendering.

## Automated checks

- 27 Python tests, including hierarchy, layout-boundary joins, conservative figure scopes, Japanese and grouped figure labels, citation conversion, and: deduplication, invalid input rejection, upload API, cross-origin and host checks, traversal, ZIP extraction boundary, preservation of TeX characters, rejection of model changes to numbers/negation, and executable-cell removal.
- 14 DOM assertions: source links, original page image, bounding-box highlight, close action, enlarged figure, gallery, scrolling TOC highlight and repeated citation targets. These use jsdom, not a browser.
- Public sample's HTML image/script/style references resolve locally; no external rendering dependency remains. MathJax, fonts and source-page images are bundled.
- Final corpus checks passed for 12 readers: **78 paragraph joins, 331 linked citation occurrences, 672 figure/equation cross-reference links, and 397 visual objects with paragraph scopes**. No local LLM request errors were recorded. These are coverage counts, not semantic accuracy scores.
- `scripts/check_readers.py` checks all 12 rebuilt readers for unique HTML IDs, valid fragment links, existing local image/script/style assets, complete original-source mappings, figures outside prose containers, and preserved equation numbers. Equation fallback images are copied explicitly because Quarto does not discover data-attribute asset references.
- GitHub Pages and the Mac Pro sample mirror returned HTTP 200 for HTML, CSS, JavaScript and source-page images. The mirror was checked from the same Mac; separate-device viewing was not tested.
- The private preview listens on `0.0.0.0:8790`; both the Mac Pro Tailscale hostname and IP returned HTTP 200 from this Mac. Separate-device access has not been tested.
- Private data is excluded by location and a fixed publisher-sample export allowlist, not just `.gitignore`.

## Comparison reader update

- Reading text is 16 px, capped at 640 px. Geometry tests cover normal and comparison layouts at 800, 1100, 1440, 1800 and 2560 px: equal comparison/text widths and a figure width between 50% and 62.5% when the right column fits.
- All 12 readers include original-page comparison data. 2,498 blocks have verified DOM/source alignment targets; native Quarto author and abstract metadata are reconstructed from verified extracted content.
- PLaMo 3 Translate 2B, using the official pinned CLI's local MLX backend at 4-bit precision, completed 80 translation units for the public sample and 62 for a private seven-page Zotero paper. These 142 units include titles, headings, abstract and prose. Original math and citation markers are preserved; model output is not a certified translation. Both translations are cached privately; only the licensed sample's translation is exported.
- Comparison DOM tests exercise equal-height paragraph alignment, reverse and forward PDF scroll mapping, reverse Japanese scroll mapping, and restoring original heights/navigation after closing comparison. The live private API queue was exercised with a cached paper and completed successfully.
- Other papers can be translated on demand or using the batch CLI. The public sample is prebuilt and does not call a translation API.
- The comparison reader includes the model license and labels machine translation as Built with PLaMo.

## Limits

Browser control is disabled by the host's Work settings. Actual browser rendering, margin collision behavior and narrow-screen appearance could not be visually inspected in this session. DOM tests and static checks do not substitute for that inspection. A matching browser test should be run when browser access is enabled.

The source page viewer is the fallback for uncertain OCR, symbol identity, reading order and caption association. Syntax-valid equations can still be semantically wrong. Whole-corpus semantic fidelity is not claimed. Private per-paper reports remain under the configured library directory and are not copied to the public demo.
