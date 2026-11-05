# Streamlit Community Cloud: initial safe deployment

Deploy the existing repository, branch `main`, entry point `streamlit_app.py`,
using Python 3.13. The root requirements file includes the existing UI manifest.

## Credentials

The operator enters `OPENAI_API_KEY` directly in Streamlit's official **Secrets**
settings as a root-level TOML string. Never commit a secrets file or send the key
through chat. The app reports configuration presence only, not key validity.
Root secrets are loaded through Streamlit's normal secrets mechanism.
After saving changed Secrets, close the settings dialog and use **Manage app >
Reboot app**, then reload the page. File watching is disabled in this project;
an existing process or session can otherwise retain older configuration.
Never inspect or screenshot the Secrets editor while credential values are shown.

Optional root setting `CLOUD_MCP_CHECK = "true"` enables one anonymous, fixed Exa
connectivity/search check per process. It uses no OpenAI requests or paid Exa key.
Asta requires its own optional `ASTA_TOOL_KEY`; absent that key, its connectivity
is unverified. No paid research test is authorized by these settings.

## Durable cloud budget (approved Supabase Free integration)

The operator may connect a dedicated Supabase Free project using root Streamlit
Secrets `SUPABASE_URL` and `SUPABASE_SECRET_KEY` (the server-only `sb_secret_...`
key). Enter values privately; no credentials are included in code or SQL.
`requests` is already installed; the Supabase SDK is not required.

Run `scripts/supabase_budget.sql` in the project's SQL Editor. Installation does
not initialize or reset spending. Initialize once using the admin-only
`ai_budget_private.seed(project_nanos, day, day_nanos, reserved_nanos, calls)`
with a fresh snapshot of the existing local ledger. It includes outstanding
reservations; repeating initialization is rejected. Do not independently run a
paid local copy after cutover: any additional local usage must also be accounted
for before further cloud spending. The local ledger remains unchanged.

Before initialization, the application refuses all research. After checking the
remote snapshot and confirming restricted Streamlit access, the operator enables
`CLOUD_RESEARCH_ENABLED = "true"`. This permits user-submitted research, not
automatic paid smoke tests. Such tests still require explicit approval.

The database enforces the existing caps and maximum turns using a shared row
lock and atomic reservation before a model call. Timeouts are not retried and
uncertain reservations stay charged. There is no local fallback or automatic
reinitialization. Outages or a paused Free project stop research safely.

The ledger stores task IDs, dates, token counts and integer charges only. It is
in a private schema with RLS and no direct application-role grants. Only the
three fixed server budget functions are callable using the server secret.
Questions, answers and OpenAI credentials are never sent to Supabase.

Scientific/web research uses the existing engine and verification. Shared SQLite
history remains disabled; results and download data belong to the Streamlit
session. Saving the current session's report still requires explicit consent;
server files and JSONL traces remain ephemeral. Download important reports.

## Initial unconfigured cloud restrictions

The default runtime is cloud-safe: paid research, private history, memory access,
and real report saving are blocked. Local `.runtime/usage.json` and SQLite are
ephemeral on Community Cloud, so they cannot enforce cumulative spending after
storage loss. Key presence does not unlock research. No flag to bypass durable
budget requirements is exposed in the UI.

Do **not** set `AI_RESEARCH_RUNTIME = "local"` in Cloud Secrets. That flag belongs
to `scripts/start_streamlit.py`, which preserves the existing local workflow.

Make the hosted app private through Streamlit's sharing settings. A public
repository can initially create a public app; the restrictions above apply
before any visitor can use credits or view local history.

Arabic/English navigation and both research mode selectors can be checked
without API calls. Scientific mode displays its abstracts/metadata-only scope.
Any optional demo report is explicitly demo data, not live research evidence.

SQLite research memory and local traces/reports are not guaranteed to persist
through redeploys. Do not upload private local runtime files to the host.
