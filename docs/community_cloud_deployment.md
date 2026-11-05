# Streamlit Community Cloud: initial safe deployment

Deploy the existing repository, branch `main`, entry point `streamlit_app.py`,
using Python 3.13. The root requirements file includes the existing UI manifest.

## Credentials

The operator enters `OPENAI_API_KEY` directly in Streamlit's official **Secrets**
settings as a root-level TOML string. Never commit a secrets file or send the key
through chat. The app reports configuration presence only, not key validity.
Root secrets are loaded through Streamlit's normal secrets mechanism.

Optional root setting `CLOUD_MCP_CHECK = "true"` enables one anonymous, fixed Exa
connectivity/search check per process. It uses no OpenAI requests or paid Exa key.
Asta requires its own optional `ASTA_TOOL_KEY`; absent that key, its connectivity
is unverified. No paid research test is authorized by these settings.

## Intentional cloud restrictions

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

Before enabling real cloud research, durable budget enforcement and authenticated
data isolation require a separately approved implementation. SQLite research
memory and local traces/reports are not guaranteed to persist through redeploys.
Local runtime files must never be uploaded to restore cloud state manually.
