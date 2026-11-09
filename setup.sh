#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v uv >/dev/null; then echo 'Install uv: brew install uv' >&2; exit 1; fi
if ! command -v quarto >/dev/null; then echo 'Install Quarto: brew install --cask quarto' >&2; exit 1; fi
uv sync --locked
if [ "${1:-}" = '--with-llm' ]; then
  command -v ollama >/dev/null || { echo 'Install Ollama: brew install ollama' >&2; exit 1; }
  ollama pull qwen3:4b
fi
printf '\nReady. Run: uv run fluent-paper serve\nOpen: http://127.0.0.1:8790\n'
