# Fluent Paper

Local PDF reader for Apple Silicon. Private PDFs and conversion outputs are stored in `~/Library/Application Support/fluent-paper`, outside this repository.

## Development

Install [uv](https://docs.astral.sh/uv/) and [Quarto](https://quarto.org/docs/get-started/), then:

```sh
uv sync
uv run fluent-paper add paper.pdf
uv run fluent-paper work --once
uv run fluent-paper serve
```

Open http://127.0.0.1:8765. Run `uv run fluent-paper work --inbox /path/to/inbox` in a second terminal for continuous processing. Uploads enter the same queue. `list` reports state; `retry ID` requeues failures. Conversion logs and original MinerU output are retained per paper. Set `FLUENT_PAPER_HOME` to change the private storage location.

## Status

Initial ingestion, persistent queue, MinerU adapter, Quarto rendering, local upload API and library view. Not yet a validated release. Structured provenance, conservative LLM correction, scoped margin tracking, Zotero evaluation, and licensed public demo are still under development. Do not treat extracted equations as verified originals.
