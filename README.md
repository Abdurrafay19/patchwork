# Patchwork

A local, self-healing code-auditing agent. It reads a Python file, patches bugs, writes tests, and runs them in an isolated sandbox — using a small quantized LLM (Qwen 2.5 Coder 3B) that fits on a 4GB laptop GPU.

## Status

Day 1 of 5 complete: the deterministic tools the agent will call are built and tested. The LangGraph reflection loop that connects them to the model doesn't exist yet.

## What works right now

Three standalone Python tools, no LLM involved:

| Tool | File | What it does |
| --- | --- | --- |
| Sandbox runner | `patchwork/tools/sandbox.py` | Runs a pytest suite against source code in a disposable temp directory, with a hard timeout so a hung or infinite-looping test can't freeze the process |
| Linter wrapper | `patchwork/tools/linter.py` | Runs `ruff check` and returns structured, truncated diagnostics |
| AST inspector | `patchwork/tools/ast_inspector.py` | Parses source into an AST, extracts functions/classes/docstring coverage, and reports syntax errors without crashing |

Each tool returns a typed Pydantic model, never raises on expected failure modes (timeouts, bad syntax, missing binaries), and has its own test file mixing mocked unit tests with real subprocess/parse integration tests.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com), running locally
- `qwen2.5-coder:3b` pulled via `ollama pull qwen2.5-coder:3b`
- An NVIDIA GPU with 4GB+ VRAM (developed against an RTX 3050 Mobile)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Confirm Ollama can serve the model:

```bash
ollama run qwen2.5-coder:3b
```

## Running the tests

```bash
pytest tests/ -v
ruff check patchwork/ tests/
```

54 tests currently pass across the three tools.

## Project structure

```
patchwork/
├── patchwork/
│   ├── cli.py              # not yet implemented
│   ├── graph.py             # not yet implemented — LangGraph state machine
│   ├── state.py              # not yet implemented — shared schemas
│   ├── tools/
│   │   ├── ast_inspector.py
│   │   ├── linter.py
│   │   └── sandbox.py
│   └── telemetry/            # not yet implemented
├── benchmarks/                # not yet populated
└── tests/
    ├── test_ast_inspector.py
    ├── test_linter.py
    └── test_sandbox.py
```

## Roadmap

- [x] Day 1 — deterministic tools (sandbox, linter, AST inspector)
- [ ] Day 2 — Pydantic schemas, LangGraph node wiring, single-pass audit
- [ ] Day 3 — reflection loop with retry/reflect cycle
- [ ] Day 4 — VRAM/throughput profiling, 25-defect benchmark dataset
- [ ] Day 5 — benchmark results, comparison charts, final documentation

## Design notes

Full architecture, hardware constraints, and per-tool design decisions are documented as the project progresses — see commit history and PR descriptions for the reasoning behind specific choices (timeout values, memory limits, truncation strategy).
