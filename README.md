# SkillsCentral

A demonstration of enterprise agent skill governance using existing Redis Iris services and a Redis Cloud database. Fictional retail procedures are served by real Agent Playbooks; the agent uses Gemini through Vertex AI in `us-east4`, Agent Memory, Context Gateway, and Lens. Click **Architecture** in the app header for the component map and turn flow, or read the [architecture document](docs/architecture.md).

## Run locally

Copy `.env.example` to `.env` and fill the existing service credentials. Install Python 3.12 and run:

```sh
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8084
```

Open `http://127.0.0.1:8084`, then use Sources → Sync all sources. Synchronization imports the fixture bundles into the existing Playbook; source revisions become drafts. Publication, withdrawal, and rollback use the real service. A serving publication is independent of the newest draft.

If the database is accessible only from the shared VM, run an SSH tunnel to its configured host and set `REDIS_TUNNEL_PORT=16384` in an ignored `.env.local` file. `.env.local` is excluded from deployment.

## Deploy, stop, and resume

```sh
bash scripts/deploy.sh
bash scripts/demo-service.sh status
bash scripts/demo-service.sh stop
bash scripts/demo-service.sh start
```

Set `GOOGLE_CLOUD_PROJECT`, `DEMO_VM_INSTANCE`, `DEMO_VM_ZONE`, `DEMO_APP_PORT`, and `DEMO_PUBLIC_HOST` in the ignored `.env` file before deploying. Use an existing VM in `us-east4`; the script builds its image there and replaces only the `skillscentral` container. No new VM, cluster, registry, disk, or IP is provisioned. The selected host port must be free and reachable. The app container and image carry `owner=lionel_giavelli` and `skip_deletion=yes` labels. Stop and start only this app container when the VM hosts other demos. The shared VM and existing Redis/Iris services retain their own billing.

The deploy script transfers the ignored `.env` to `/opt/skillscentral/.env` with restricted file permissions and mounts it read-only. Credentials never reach the browser or the Docker image. Deployment addresses and service IDs belong in that private configuration. All application Redis keys begin with `SkillsCentral:`. Demo content keys in Playbooks begin with `skillscentral-`; other entries and existing router intents are preserved.

## Present

Use the in-app Demo guide and [presenter runbook](demo/runbook.md). The central story is to ask the 38-day jacket question, compare the current 30-day publication with the 45-day draft, publish the draft, repeat the question, withdraw the skill, and roll back to the earlier reviewed procedure. Actual remote version numbers are displayed in the catalog; use those numbers, since verification created immutable earlier versions.

## What the evidence means

- Skill bundles and retail records are fictional. The three source repositories are local fixtures; `.github/workflows` contains examples for connecting real GitHub repositories.
- Usage starts at zero and comes from actual app turns. A use means a discovered skill was loaded into the model context; discovery alone is counted separately. This is application reporting, not a native Playbooks analytics dashboard.
- Tokens come from the model response. Cost uses illustrative configured input/output rates (defaults $1/$5 per million tokens), allocated equally across loaded skills. It excludes Iris service/tool charges and is not provider billing.
- A sufficiently confident approved FAQ is returned without a model call. Uncovered requests do not fabricate a policy. Router or memory outages are shown explicitly; Playbooks failures stop governed answering.
- When the agent fetches a fictional return order, the app calculates eligibility using the numeric window in the loaded published procedure. It returns that deterministic assessment without a second model call. This avoids relying on the model to compare purchase age with the policy window.
- Lens records one trace per agent turn with the session and user IDs. Gemini spans record usage explicitly because the Lens SDK does not automatically instrument `google-genai`.
- Reset restores demo lifecycle publications and drafts while retaining immutable service history and recorded usage.

See [architecture](docs/architecture.md), [source synchronization](docs/source-sync.md), and the [official Redis Iris documentation](https://redis.io/docs/latest/develop/ai/context-engine/).
