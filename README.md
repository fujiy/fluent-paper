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

For optional local whitespace correction, install and start [Ollama](https://ollama.com/), run `./setup.sh --with-llm`, then:

```sh
FLUENT_PAPER_LLM=qwen3:4b uv run fluent-paper serve
```

The default preserves MinerU text. LLM proposals cannot alter non-whitespace characters; rejected edits are recorded. This conservative mode deliberately does not repair equations, numbers, missing words, or uncertain captions by guessing. It can be omitted entirely.

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

Uploads are limited to 100 MiB. The server binds only to loopback and rejects cross-origin writes.

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

The Pages workflow deploys only `demo/`. In repository **Settings → Pages → Build and deployment**, select **GitHub Actions** once. Subsequent changes to `demo/` deploy automatically. The fixed-sample exporter checks the source hash and license metadata before copying selected rendering files.

## Validation and limits

See [VALIDATION.md](VALIDATION.md). This is a working prototype, not a guarantee of faithful OCR: particularly old scans, multi-column reading order, dense equations and caption associations need source checks. LLM correction is intentionally narrow. The private evaluation report and PDFs are never included in the repository or public demo.

```sh
uv run python -m unittest discover -s tests
# Optional DOM-only interaction tests (no browser automation):
JSDOM_MODULE=/path/to/node_modules/jsdom node tests/reader.test.cjs
```
