# ADR-016 Pilot Procedure (Phase 3) — ReAct Success Rate on Ollama + Llama 3.1

**ADR**: ADR-016 (Tool Capability Adapter — `ModelCapabilityMatrix` + `ToolCallingAdapter` native/react/hybrid).
**Source**: `ROADMAP.md` §14.1 (pilot: Ollama, ReAct success rate ≥80%), `BETA-PROMPTS.md` E-3, `scripts/pilot_ollama_react.py` (Блок D-6).
**Note**: This is a **manual** pilot procedure, not a CI test — Ollama runs on a developer machine (see `scripts/ci-local-staging.sh` Phase 3 E-3 comment).

## Pilot criteria (ROADMAP §14.1)

| Criterion | Threshold | Verdict |
|---|---|---|
| ReAct success rate (expected tool == actual tool call) | ≥ 80% (vs native ≥95%) | **PILOT PASS — ADR-016 Approved** |
| ReAct success rate | 60–80% | **PILOT PARTIAL** — tune ReAct prompt variant (D-4), re-run |
| ReAct success rate | < 60% | **ROLLBACK REQUIRED** — ADR-016 rollback |
| False `ModelCapabilityMatrix` entries | cause runtime errors | **ROLLBACK** |
| Sample size | < 20 tests | warning — verdict not trustworthy (`MIN_SAMPLE_SIZE=20`) |

## Prerequisites

- Local Ollama installed (https://ollama.com — `winget install --id Ollama.Ollama`).
- Llama 3.1 model pulled: `ollama pull llama3.1:8b` (~4.7 GB).
- LLM Client repo cloned + dependencies installed (`pip install -e ".[ollama]"` — the `ollama` extra provides `langchain-ollama`; without it the script falls back to `langchain-community`).
- `.env` present (copy from `.env.example`).

## Steps

1. Start Ollama: `ollama serve` (default port 11434; the Windows installer runs it in background).
2. Verify model available: `ollama list` should show `llama3.1:8b`.
3. Run pilot:

   ```bash
   python scripts/pilot_ollama_react.py \
     --ollama-url http://localhost:11434 \
     --model llama3.1:8b
   ```

   Optional flags:
   - `--variant v1_strict|v2_tolerant|v3_cot` — ReAct prompt variant (D-4), sets `REACT_PROMPT_VARIANT`.
   - `--output test-results/adr016_pilot_report.json` — JSON pilot report.

   The pilot sends 24 tool-calling prompts (8 × `web_search`, 8 × `rag_query`, 8 × `file_export`) through `ToolCallingAdapter.bind_tools(..., ToolCallingMode.REACT)` and counts matches between the expected tool and the model's tool call. Tools are only bound to the prompt — never executed — so no API keys (Tavily etc.) are required.

4. Review output:
   - `PILOT PASS - ADR-016 Approved (success rate >=80%)` — success rate ≥80%, ADR-016 Approved.
   - `PILOT PARTIAL - success rate NN.N% (need >=80%...)` — 60–80%, tune ReAct prompt variant (D-4), re-run.
   - `ROLLBACK REQUIRED (success rate <60%)` — ADR-016 rollback; investigate `ModelCapabilityMatrix` entries (false capability entries → runtime errors also trigger rollback per ROADMAP §14.1).
   - `Sample size warning: N tests (<20)` — verdict not trustworthy; use the full 24-case set.

## Tuning

If success rate is 60–80%, try different ReAct prompt variants (D-4):

```bash
python scripts/pilot_ollama_react.py --variant v2_tolerant
python scripts/pilot_ollama_react.py --variant v3_cot
```

or set the env var directly: `REACT_PROMPT_VARIANT=v2_tolerant` (default `v1_strict`; unknown values fall back to `v1_strict` with a warning — see `src/llm_client/agent/react_prompt_builder.py`).

Tuning tips:

- `v2_tolerant` — relaxed tool-selection instructions; helps when the model answers in prose instead of emitting a tool call (`no_tool_call_detected`).
- `v3_cot` — adds chain-of-thought preamble; helps when the model picks the wrong tool (`wrong_tool` failure reason).
- Failure reasons are printed per run (`failure_reasons` dict) — use them to pick the variant.
- Temperature is fixed at `0.0` in the pilot (`ChatOllama(temperature=0.0)`) for reproducibility.

## Exit / report

- The script prints total tests, successes, failures, success rate, failure reasons, and the verdict.
- With `--output <path>` it writes a JSON report: `pilot`, `ollama_url`, `model`, `react_prompt_variant`, `total_tests`, `successes`, `failures`, `success_rate`, `failure_reasons`, `sample_size_warning`, `verdict`.
- Exit code is `0` for all verdicts — automation must parse the `verdict` field / stdout, not the exit code.

## Related documents

- `scripts/pilot_ollama_react.py` — the pilot script (Блок D-6).
- `tests/unit/test_pilot_ollama_react.py` — unit tests for the script.
- `analytics/ROADMAP.md` §14.1 — pilot metrics and rollback criteria.
- `analytics/BETA-PROMPTS.md` E-3 — the prompt this procedure implements.
- `analytics/BETA-PROMPTS.md` D-4 — ReAct prompt variants (`REACT_PROMPT_VARIANT`).
