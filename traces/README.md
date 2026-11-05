# Submission trace provenance

All three files are complete, naturally occurring **historical CLI runs**, reused
without new paid API calls. They are not fault-injected scenarios or mocked traces.
The exporter preserved task identity, original chronology, outcomes, tools, token
usage and accounting. Private originals remain under `.runtime/traces/`.

| Deliverable | Original run ID | Events | Final outcome | Evidence |
|---|---|---:|---|---|
| `success_1.jsonl` | `46c433f92cc74827a77a5cddb3a26e6a` | 17 | `success` | Exa MCP discovery/search events, retrieved references, four final sources, two measured model calls, no tool failure |
| `near_failure_recovery.jsonl` | `d30d284e0f1341b18c34dea318dc1d8c` | 27 | `degraded` | Semantic Scholar/OpenAlex rate limits, explicit recovery events and later OpenAlex/arXiv evidence, four final references, five measured calls |
| `explicit_failure.jsonl` | `70d4c78c3b6b44b693f687d892df45d1` | 20 | `no_evidence` | All attempted scientific services rate-limited, no evidence, explicit safe rejection and four measured calls |

The previous two-event invalid-input example was preserved byte-for-byte as
`archive/explicit_failure_9615cdff6a3b4aae9e6bd04b89429f11.jsonl` before exporting
the more meaningful research failure. No original private trace was modified.

Run:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_submission.py
```

This validates JSON, event schema/sequence/identity, reservation and token totals,
required outcomes, and a recovery sequence that leads to actual evidence from the
recovery provider. Where private originals exist, the complete normalized event
list must match. A public clone can check the supplied files but cannot recover
the private originals or independently prove provider billing.

Validated SHA-256 values on the prepared files:

- `success_1.jsonl`: `da729291f2c2760590d0c53e2696c9445413059dca5db2094341255e73062aa3`
- `near_failure_recovery.jsonl`: `e812040ae8df68d3f2b160e95a8c64ecedf8f76d03b6f96fc86defff7b4553db`
- `explicit_failure.jsonl`: `b0138e1f0695f43067857354349552b0c4415f05e988c9b3223d27a4513455a3`

Byte hashes may change with newline conversion; event-list equality is checked
separately. Prompts, authentication values and answer bodies are intentionally
absent from the audit schema. `research_finished` is emitted after validation;
the final status is evidence of that code path, not a semantic fact-check of every
sentence. Source arrays in generic private traces are bounded to 20 entries;
these selected runs fit within that bound.
