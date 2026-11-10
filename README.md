# Fluent Paper

A local PDF reader for Apple Silicon. Quarto renders the main text in the center and places figures, footnotes, and linked numbered references in a floating right column. Narrow screens use normal document order.

## Setup

Install [uv](https://docs.astral.sh/uv/) and [Quarto](https://quarto.org/docs/get-started/), then:

```sh
git clone https://github.com/fujiy/fluent-paper.git
cd fluent-paper
./setup.sh
uv run fluent-paper serve
```

Open **http://127.0.0.1:8790**. Upload a PDF; the server starts a background worker automatically. The first MinerU conversion downloads its models. Later parsing and reading run locally. Close the server with Ctrl-C. Interrupted jobs resume on the next worker start.

For local structural repair, install and start [Ollama](https://ollama.com/) and run `./setup.sh --with-llm`. The default model is `qwen3:4b` (about 2.5 GB). Set `FLUENT_PAPER_STRUCTURE_MODEL` to another Ollama model, or to an empty string for mechanical rules only.

The pipeline first restores numbered heading levels and joins clear page/column fragments. The local model decides uncertain heading levels, ambiguous paragraph joins (including printed hyphens), and the smallest figure scope within the reference paragraph and its immediate neighbors. It selects existing IDs and actions; it cannot rewrite scientific text. Decisions and input are cached in `structure-decisions.json`; the restored structure is in `reading-structure.json`. If Ollama is unavailable, conservative mechanical results remain usable and errors are recorded.

Figures are inserted between restored paragraphs. Figure/equation references use native Quarto cross-reference syntax, and citations use citeproc with a reconstructed bibliography. Every linked citation can appear in the right margin. Original reference numbers are restored after Quarto rendering because its custom-label support does not reliably handle nonconsecutive labels.

The older `correct` command is an optional whitespace-only correction pass. It does not repair equations or missing words.


The reader uses a 16 px reading font with a 640 px maximum text column. The right column is 50–62.5% of that width. **Compare → Original PDF** opens synchronized original page images on the left. **Compare → Japanese** aligns the translation to each paragraph; the navigation is hidden in both comparison modes. Scrolling either side follows the corresponding source position.

To enable local Japanese translation with the official PLaMo 3 Translate 2B model:

```sh
./setup.sh --with-translation
uv run --extra translation fluent-paper serve --host 0.0.0.0 --allowed-host YOUR_HOST_OR_IP
# Batch translation (one paper, or use “all”):
uv run --extra translation fluent-paper translate PAPER_ID
```

In a private reader, select **Japanese**, then **Translate**. The existing worker queues the job and updates the view when complete. Translation is cached per paragraph outside Git. The first use downloads the original model weights (about 5.76 GB); inference uses local MLX at 4-bit precision. Formulas and citation markers are preserved exactly. An interrupted job resumes from saved paragraphs; failures remain visible and can be retried. `FLUENT_PAPER_TRANSLATION_MODEL` can select another original PLaMo 3 checkpoint supported by the pinned backend.

The public sample includes a prebuilt machine translation and works without a server. Built with PLaMo; translations are model output under the bundled [PLaMo Community License](src/fluent_paper/plamo-license.html). See the [official backend](https://github.com/pfnet/plamo-translate-cli) for supported models and license details.

## Ingestion

```sh
uv run fluent-paper add paper.pdf other.pdf
uv run fluent-paper work --once
uv run fluent-paper work --inbox /path/to/inbox
uv run fluent-paper list
uv run fluent-paper retry PAPER_ID
uv run fluent-paper rebuild PAPER_ID
uv run fluent-paper correct PAPER_ID --model qwen3:4b
uv run fluent-paper rebuild PAPER_ID
```

One worker owns the library at a time. Use either `serve` (automatic worker) or `work` for processing. File hashes deduplicate repeated uploads. Failed conversions retain logs and can be retried; an existing extraction archive is reused when only rendering failed. `rebuild all` regenerates all ready papers without rerunning MinerU. The folder watcher waits until a file has not been modified for three seconds; for large copies, write to a temporary filename and rename to `.pdf` when complete.

HTTP API, while `serve` is running:

```sh
curl -H 'Accept: application/json' -F 'file=@paper.pdf' http://127.0.0.1:8790/api/papers
curl http://127.0.0.1:8790/api/papers
curl -X POST http://127.0.0.1:8790/api/papers/PAPER_ID/retry
```

Uploads are limited to 100 MiB. The server binds to loopback by default and rejects cross-origin writes. To preview from another device, run `uv run fluent-paper serve --host 0.0.0.0 --allowed-host YOUR_HOST_OR_IP`. This serves your private library to devices that can reach the port; no library contents are uploaded to GitHub.

## Reading and provenance

- **Source links** exposes each block's source-page button. Clicking it shows the original page image with the extraction bounding box highlighted.
- Click a figure to enlarge it; **Figures** opens a gallery.
- Figures referenced by `Fig. N` or `Figure N` follow those paragraphs. Pin controls come from the margin-layout extension.
- Original PDFs, raw MinerU ZIP/JSON/Markdown, stable block IDs, page coordinates, correction logs and build logs are retained.
- Long ambiguous captions remain in the main column so possible body text is not hidden in a margin.
- MathJax 3.2.2 and its fonts are bundled. Reading does not need a CDN.

Private data defaults to `~/Library/Application Support/fluent-paper`, outside Git. Set `FLUENT_PAPER_HOME` to use another private directory. `document.json` stores the intermediate representation; `evaluation-report.json` stores text-layer diagnostics. Model files use the normal MinerU/Ollama caches. MinerU telemetry and inherited LLM postprocessing are explicitly disabled in the parser subprocess.

## Public sample

`demo/` contains only the publisher's CC BY 4.0 sample *Swing-up control of double-inverted pendulum systems* (2024), acquired independently of Zotero. See [THIRD_PARTY.md](THIRD_PARTY.md) for attribution. It is a prebuilt static website; no model or private library is uploaded to GitHub Actions.

The live sample is at **https://fujiy.github.io/fluent-paper/**. GitHub Pages deploys the `gh-pages` branch. The main-branch workflow checks the public package. To publish a rebuilt sample, run `uv run python scripts/export_demo.py`, then `uv run python scripts/publish_demo.py`; the publisher copies only `demo/` into a normal, non-force `gh-pages` commit. The fixed-sample exporter checks the source hash and license metadata before copying selected rendering files.

## Validation and limits

See [VALIDATION.md](VALIDATION.md). This is a working prototype, not a guarantee of faithful OCR: particularly old scans, multi-column reading order, dense equations and caption associations need source checks. Model decisions are constrained to structure; uncertain OCR still needs source checks. The private evaluation report and PDFs are never included in the repository or public demo.

```sh
uv run python -m unittest discover -s tests
# Optional DOM-only interaction tests (no browser automation):
JSDOM_MODULE=/path/to/node_modules/jsdom node tests/reader.test.cjs
```
