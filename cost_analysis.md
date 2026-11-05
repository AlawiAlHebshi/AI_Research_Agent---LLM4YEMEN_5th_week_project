# Cost Analysis - AI Research Assistant

**Prepared:** 5 November 2026  
**Status:** Development snapshot; suitable as the current capstone cost analysis, with hosting and final-production estimates pending.  
**Currency:** USD. **Provider/model recorded by the application:** OpenAI / `gpt-6-luna`.

## 1. Executive summary

The latest ledger contains **138 unique model calls across 39 run IDs**, with a locally estimated total model cost of **$0.04145523**. Its average is **$0.00106295 per recorded run**. These are measured token counts converted to estimated costs, **not a verified OpenAI invoice or remaining account balance**. [D1]

Of these, **37 research runs / 132 calls** have matching execution traces: 17 web and 20 scientific runs. Their average is **$0.00109844 per research attempt**, used as the primary mixed-workload projection. Two older runs, costing $0.00081307, have no corresponding traces and remain unclassified. [D1, D2]

At the observed workload, **100 / 1,000 / 10,000 research attempts** would cost approximately **$0.1098 / $1.0984 / $10.9844 in model usage alone**. Search-service charges, hosting, taxes, and use of the same key outside this application are excluded. A research attempt is not necessarily a completed answer.

## 2. Evidence and reconciliation

| Evidence | Use |
|---|---|
| `usage(1).json` | Authoritative supplied application ledger: calls, model, tokens, cached tokens, local charge, and accounting day. |
| `traces(1).zip` | 44 JSONL files containing 950 events: 38 CLI runs and 6 public-tool probes. |
| Project specifications and supplied reports | Agreed budgets, intended architecture, access arrangements, and deployment status; not proof of provider billing. |
| Official provider documentation | Public rate checks, separate from the supplied NotebookLM/book summary; checked 5 November 2026. |

**Reconciliation performed:**

- All 138 ledger call IDs are unique and marked `measured`; all have reproducible token charges.
- All 132 `model_usage` events in the archive match ledger entries exactly by reservation ID, task ID, input/output/cached tokens, and charge. Per-run totals also reconcile.
- The unmatched six calls belong to two older tasks. They are included in total expenditure but excluded from mode/outcome analysis.
- The remaining seven traces contain no model calls: six tool probes and one `invalid_input` run. They are not added to the model-run average denominator to make it appear cheaper. Public-tool probes can still consume service quotas.
- `model_reserved` events are pre-call estimates, not extra expenditure. No unresolved reservation balance is reported in the supplied snapshots.
- Only the latest ledger was counted. The earlier upload overlaps it, and the two uploaded ZIP archives are byte-identical. Adding both snapshots would double-count consumption.

A run is one distinct task ID. Re-running the same question creates a new, separately counted attempt; a call is one model invocation within that run. Ledger accounting days are retained as recorded; trace timestamps are UTC. No claims are made about unrecorded account usage.

## 3. Model pricing and calculation

### 3.1 Pricing basis

The official model-specific documentation lists these standard text rates for `gpt-6-luna`. They also reproduce every ledger charge exactly. [S1]

| Token category | USD per 1 million tokens |
|---|---:|
| Uncached input | $0.10 |
| Cached input read | $0.01 |
| Output | $0.50 |

The calculation assumes standard, short-context processing. The largest **measured** input in this sample is 11,718 tokens per call. Explicit cache-write charges, regional/processing-tier premiums, and other provider fees cannot be reconciled because the supplied files do not record those billing categories. The official pricing documentation lists such distinctions; this report does not infer missing usage. [S1]

### 3.2 Formula

For each call, let `I` be total input tokens, `K` the cached-input subset, and `O` total output tokens:

```text
call_cost_usd = ((I - K) * 0.10 + K * 0.01 + O * 0.50) / 1,000,000
run_cost_usd  = sum(call_cost_usd for all calls in the run)
```

Cached tokens are subtracted from total input before applying the uncached rate. Output tokens are counted once. Do not multiply the accumulated usage again by the number of turns or parallel calls.

The ledger's integer `charge` matches trace `cost_nanos`: divide by **1,000,000,000** for USD. This unit interpretation is corroborated by exact reproduction of every record using the formula above; it is an application accounting unit, not a separate provider fee. [D1, D2]

For the full snapshot:

```text
Uncached input: 262,056 * $0.10 / 1,000,000 = $0.02620560
Cached input:  184,813 * $0.01 / 1,000,000 = $0.00184813
Output:         26,803 * $0.50 / 1,000,000 = $0.01340150
Total:                                         $0.04145523
```

**Caching sensitivity:** pricing the same tokens without cache-read discounts would cost $0.05808840. Recorded caching reduces that comparison by **$0.01663317 (28.63%)**. The 90% discount applies only to cached input tokens at these rates, not to the entire bill or to every model. This comparison assumes unchanged token volumes and is not a separate measured run.

## 4. Recorded usage and outcomes

### 4.1 Usage by research mode

Input totals below already include the cached subset. All dollar amounts are local model-cost estimates. [D1, D2]

| Group | Runs | Model calls | Input tokens | Cached subset | Output tokens | Total USD | Mean USD/run |
|---|---:|---:|---:|---:|---:|---:|---:|
| Web research | 17 | 47 | 222,423 | 84,196 | 10,530 | $0.01992966 | $0.00117233 |
| Scientific research | 20 | 85 | 218,430 | 98,350 | 15,442 | $0.02071250 | $0.00103563 |
| Trace-matched research total | 37 | 132 | 440,853 | 182,546 | 25,972 | $0.04064216 | $0.00109844 |
| Earlier runs without matching traces | 2 | 6 | 6,016 | 2,267 | 831 | $0.00081307 | $0.00040654 |
| Entire usage ledger | 39 | 138 | 446,869 | 184,813 | 26,803 | $0.04145523 | $0.00106295 |

For the 37 trace-matched runs, the median is **$0.00110670**, with a range of **$0.00049260 to $0.00216484**. None exceeds the agreed $0.03 model-cost cap. This observation is not a proof that every future request is safely bounded.

### 4.2 Outcomes are not interchangeable

| Terminal status | Runs | Model cost | Interpretation |
|---|---:|---:|---|
| `success` | 9 | $0.01000358 | Completed; no degradation recorded |
| `degraded` | 6 | $0.00808695 | Completed with reported limitations |
| `invalid_response` | 14 | $0.01652813 | Output rejected by application validation |
| `no_evidence` | 3 | $0.00152460 | Insufficient usable evidence |
| `budget_stop` | 5 | $0.00449890 | Local guard stopped execution; not proof of monetary overspend |

The 37 trace-matched attempts produced **15 application-completed answers**: 9 `success` and 6 `degraded`. The latter are kept distinct. The other 22 runs did not produce a completed research answer. A correct `no_evidence` response can be valid behavior, but is not counted here as a delivered research synthesis. These are application labels, not an independent audit of scientific correctness.

Three different metrics must not be confused:

| Metric | Calculation | Result |
|---|---|---:|
| Cost per research attempt | $0.04064216 / 37 | $0.00109844 |
| Mean cost of completed runs only | $0.01809053 / 15 | $0.00120604 |
| Observed spend per delivered answer, including non-completion overhead | $0.04064216 / 15 | $0.00270948 |

The final metric distributes all measured research expenditure over delivered answers. It is not a measured retry policy or a guarantee of future performance. Fixing validation, retrieval, and context failures may change both completion rates and average costs.

## 5. Monthly volume projections

These are arithmetic extrapolations, **not forecasts or permission to exceed spending caps**. They retain the current per-run token mix and discounts unless stated otherwise. No additional discount is applied to a mean that already includes cached-input pricing.

| Scenario | 100/month | 1,000/month | 10,000/month |
|---|---:|---:|---:|
| Observed web/scientific mix: 37 traced runs | $0.1098 | $1.0984 | $10.9844 |
| Web research only | $0.1172 | $1.1723 | $11.7233 |
| Scientific research only | $0.1036 | $1.0356 | $10.3563 |
| Entire ledger: 39 runs, including 2 unclassified | $0.1063 | $1.0630 | $10.6295 |
| Same 37-run workload, no input-cache discount | $0.1542 | $1.5425 | $15.4247 |
| Delivered-answer target, retaining current non-completion overhead | $0.2709 | $2.7095 | $27.0948 |

In the first five rows, volume means **attempts**. In the last row, volume means **delivered answers**, with the observed non-completion overhead retained. The primary mixed scenario uses the observed 17:20 web/scientific split, not an assumed 50:50 split.

The no-cache row removes only cache-read discounts; it is a sensitivity case, **not a worst-case upper bound**. Longer outputs, larger contexts, new tools, retries, and different processing tiers can increase costs further.

## 6. External research services

The application ledger measures model usage only. A provider's free access, credit allowance, and a verified zero-dollar invoice are different things.

| Service | Evidence from this project snapshot | Cost treatment and current public access information |
|---|---|---|
| Exa MCP | 63 `exa_search` starts across 17 model-backed web runs; the supplied implementation report describes anonymous access. | No external charge is recorded. Public MCP documentation describes limited free access. Standard API search is advertised at $7/1,000 requests for up to 10 results; the account free tier advertises $10 monthly credits. These do not establish this project's billed usage or anonymous quota. [S2, S3] |
| Asta MCP | No completed Asta search; a probe reports `asta_key_missing`. | No Asta fee recorded. Ai2 describes free Scientific Corpus access and a key for higher rate limits; no fixed numeric quota is assumed. [S4, S5] |
| Semantic Scholar | Used; rate-limit errors recorded. | Public API access is rate-limited; no service charge is captured in these files. Do not infer unlimited capacity from unauthenticated access. [S6] |
| OpenAlex | Used for primary/fallback scientific retrieval. | Account access currently includes $1/day of API usage credit. Anonymous access and quotas are separate; no provider invoice or account allowance was supplied. Do not credit the project with an allowance it has not activated. [S7] |
| arXiv | Used for scientific retrieval. | No service charge recorded; respect its API request-spacing and caching guidance. [S8] |
| Wikipedia / DuckDuckGo | Used as secondary/fallback tools. | No paid subscription reported or charge recorded. Wikipedia access remains subject to rate limits; DuckDuckGo availability has failed in project tests. A free access path is not a service guarantee. [D3, S9] |

**Do not charge for MCP handshakes as if they were searches.** The Exa logs contain cumulative HTTP/byte counters per run. They are not per-event increments or billable-search counts. The 63 search starts are also not a provider billing statement.

**Illustrative paid-Exa sensitivity:** 63 / 17 = **3.706 search starts per web attempt**. If each were a billable standard search at $0.007, external search would add about **$0.02594118 per web attempt**, before any credits or extras. At 1,000 web attempts, model usage plus this hypothetical search component would be **$27.11**, rather than the model-only $1.1723. Failed, cached, or blocked calls may be treated differently by the provider; this is not the cost of the observed free-MCP tests. [S3]

## 7. Hosting and storage

**No hosting provider or actual hosting charge is established by the supplied evidence.** The figures below are options, not committed project expenditure.

| Option | Public price / planning basis | Persistence consideration |
|---|---|---|
| Streamlit Community Cloud | Free hosting. [S10] | Local files are not guaranteed to persist; insufficient by itself for reliable SQLite memory and a durable spending ledger. [S11] |
| Render free service | $0 under free-service restrictions. [S12] | No persistent disk; local data cannot be treated as durable. [S13] |
| Render paid example | $7/month compute plus $0.25/GB/month disk: **$7.25/month** for an illustrative 1 GB disk. [S12] | Only data under the persistent mount survives redeploys/restarts; workload capacity is untested. [S13] |
| Railway Free / Hobby | Free plan advertises $1/month resource credit after the trial; Hobby has a $5/month minimum credited toward resource usage. [S14] | Use a volume and check resource consumption and plan constraints. Hobby is not $5 plus the same first $5 of usage again. [S15] |

```text
monthly_total = model_usage + billable_search_services
                + hosting_and_storage + other applicable fees
```

For example, 1,000 attempts at the mixed model-only mean plus the illustrative Render configuration would be **$8.3484/month before search charges, taxes, egress, or other extras**. This does not assert that the hosting size can handle that workload.

## 8. Project controls and grant boundaries

| Control | Agreed value | Evidence / interpretation |
|---|---:|---|
| Model-cost cap per run | $0.03 | Approved specification; all recorded runs are below it. |
| Daily model-cost cap | $0.30 | Approved specification; ledger-day maximum in this snapshot is $0.04064216. |
| Cumulative experimentation cap | $5.00 | Project cap, not a monthly allowance or external-search cap. |
| Maximum model calls per run | 10 | Approved specification; observed maximum is 6. |
| Maximum output per call | 1,200 tokens | Recorded on all 138 calls; two calls reached this value. |
| Program-provided credit | $30; expiry 2 December 2026 | User-provided program allocation, not a verified current balance. |

Pre-call reservations, settlement, persistent accounting, permission-gated report saving, and run tracing are described in the project reports; reservation/settlement events are visible in the traces. Local controls do not cover Cline, OpenCode, other applications, or separate MCP-provider bills.

A trace labeled `budget_stop` is not evidence that $0.03 was spent. All five such traces cost less than $0.0011; supplied terminal logs associate these runs with the application's context-safety guard. Future diagnostics should distinguish context limits from monetary limits.

At the current **$5 cumulative cap**, the 10,000-attempt projections cannot run unchanged. A $0.30/day cap alone permits at most $9 over 30 days, before applying the stricter cumulative cap. Higher-volume tables describe cost scenarios only; budget changes require approval.

## 9. Assumptions, source differences, and limitations

The NotebookLM summary was used for the required report structure and 100/1,000/10,000 monthly volumes. Its Sonnet examples, suggested $0.25-$0.50 task cap, and $5 daily cap are **not** this project's prices or decisions. This report explicitly uses the supplied ledger, the approved $0.03/$0.30/$5 controls, and separately checked provider documentation.

The claim that Railway has no ongoing free option is not retained as a current pricing fact: its official page currently lists a Free plan. Likewise, a generic 90% caching saving is not applied to the entire model bill. [S14, S1]

The sample is small, spans development revisions, includes repeated questions, and has a substantial non-completion rate. Results therefore cannot establish production cost, quality, or throughput. Historical terminal summaries may differ from newer trace labels; the attached latest snapshots are the accounting basis here.

No OpenAI organization invoice, provider dashboard balances, external-service invoices, full source code, or final hosting configuration was supplied for this analysis. Discounts granted by LLM4Yemen, usage outside this application, and unrecorded cache-write/tier charges remain unverified. The $30 grant is funding, not evidence that inference has zero economic cost. Internet, electricity, hardware, labor, and Codex subscription costs are excluded.

**Before final submission:** update these files after final tests, reconcile with the provider dashboard if access is available, record actual search-service and hosting plans, and revise averages after reliability fixes. Keep failed attempts in the expenditure total.

## Sources and audit trail

**Local evidence**

- **[D1]** `usage(1).json`, supplied ledger; SHA-256: `60a508660682a43c4bf2784439cf91ced6b69c3a541a71e70908105e5e5e68f5`.
- **[D2]** `traces(1).zip`, supplied trace archive; SHA-256: `413c1cf8b792b8e478a69e1adb93df46d2a1bd55e7e45b7541e9e0362974f0b9`.
- **[D3]** Supplied `agent_spec.md`, LLM4Yemen project context, implementation reports, terminal logs, program-credit message, and NotebookLM extraction. These are project evidence, not current provider invoices.
- **Companion:** `cost_audit.json` contains per-task calculations, aggregates, projection values, and reconciliation metadata, without API keys, questions, or answer bodies.

**Official external references - checked 5 November 2026**

- **[S1]** [OpenAI GPT-6 Luna model pricing](https://developers.openai.com/api/docs/models/gpt-6-luna?trk=public_post_comment-text) and [current pricing listing](https://developers.openai.com/api/docs/pricing?upgrade-intent=undefined). Model-specific/current indexed rates were used; a cached rendering of the generic pricing page showed an older model catalog.
- **[S2]** [Exa MCP access](https://exa.ai/docs/reference/exa-mcp).
- **[S3]** [Exa pricing](https://exa.ai/pricing).
- **[S4]** [Ai2 Asta announcement - free Scientific Corpus access](https://allenai.org/blog/asta).
- **[S5]** [Asta MCP authentication and rate-limit guidance](https://allenai.org/asta/resources/mcp).
- **[S6]** [Semantic Scholar API access and limits](https://webflow.semanticscholar.org/product/api).
- **[S7]** [OpenAlex pricing](https://help.openalex.org/access/pricing/) and [authentication](https://help.openalex.org/api/authentication/).
- **[S8]** [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html).
- **[S9]** [Wikimedia API access](https://www.mediawiki.org/wiki/Wikimedia_APIs) and [rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits).
- **[S10]** [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud).
- **[S11]** [Streamlit local-storage persistence warning](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).
- **[S12]** [Render compute and disk pricing](https://render.com/pricing?trk=article-ssr-frontend-pulse_little-text-block).
- **[S13]** [Render persistent disks](https://render.com/docs/disks).
- **[S14]** [Railway pricing](https://railway.com/pricing).
- **[S15]** [Railway plan billing](https://docs.railway.com/pricing/plans).
