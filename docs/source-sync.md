# Source synchronization and publication

The supplied source trees are fixtures, not independently hosted Git repositories. They demonstrate three authoring origins without claiming an already-installed GitHub integration. The GitHub Actions validate the checked-in packages. Remote synchronization runs only when the repository service variables and publisher secret are configured.

## Files and initial lifecycle

`demo/catalog.json` is the initial application fixture. Each skill includes source, owner, category, latest file content, intended initial publication, and version snapshots. Skill bundles live at `demo/sources/<source>/skills/<key>/SKILL.md`; each folder name equals its frontmatter `name`. The adjacent `.iris-playbook.json` holds discovery intents, attributes, and provenance metadata.

The return procedure has a **baseline** with a fictional 30-day window and a **candidate** with a fictional 45-day window. The source file contains the candidate. Use the actual IDs displayed in the catalog: verification appends immutable revisions, so baseline and candidate are not permanently versions 1 and 2. Inspect current state before each presentation. A source sync must not publish the candidate automatically. Four other skills stay drafts and the legacy automatic-refund entry stays withdrawn.

Initialization maps fixture snapshots to real remote versions, retains earlier immutable history, and selects the intended baseline publication. Source synchronization afterwards uploads changed drafts. It preserves the serving publication unless the presenter explicitly publishes a reviewed version.

## Local validation

Use the installed environment; these checks do not need service credentials:

```bash
.venv/bin/iris --json --no-input agent-playbooks skills validate demo/sources/retail-operations/skills demo/sources/customer-care/skills demo/sources/agent-lab/skills
.venv/bin/iris --json --no-input agent-playbooks faqs validate demo/faqs
```

These commands passed for all 15 skill bundles and three FAQ files with `redis-iris==1.0.1` during authoring.

With the content-publisher environment already loaded, preview and upload one source:

```bash
.venv/bin/iris --json --no-input agent-playbooks skills plan demo/sources/retail-operations/skills --publish none
.venv/bin/iris --json --no-input agent-playbooks skills sync demo/sources/retail-operations/skills --publish none
```

Run the same pair for the other two source directories. No example uses `--prune`: one fixture source must not delete entries belonging to another source. The commands create or update drafts and do not change the serving publication. Repeated identical synchronization should not append another content version.

Review the returned history, then select the exact reviewed candidate version shown in the catalog. Record the current baseline number before changing publication:

```bash
.venv/bin/iris --json --no-input agent-playbooks skills versions skillscentral-return-authorization
read -r -p 'Current reviewed baseline version from the catalog: ' baseline_version
read -r -p 'Reviewed candidate version from the catalog: ' candidate_version
.venv/bin/iris --json --no-input agent-playbooks skills show skillscentral-return-authorization --version "$candidate_version"
.venv/bin/iris --json --no-input agent-playbooks skills publish skillscentral-return-authorization --version "$candidate_version"
```

Republishing the recorded baseline is a rollback. Withdrawal stops new serving reads while preserving entry history:

```bash
.venv/bin/iris --json --no-input agent-playbooks skills withdraw skillscentral-return-authorization
.venv/bin/iris --json --no-input agent-playbooks skills publish skillscentral-return-authorization --version "$baseline_version"
```

After a publication change, test a fresh agent turn and inspect the actual returned entry/version. Management state and serving search may not become observable at the same instant.

## GitHub Actions configuration

Configure repository variables `IRIS_AGENT_PLAYBOOKS_URL` and `IRIS_AGENT_PLAYBOOKS_PLAYBOOK_ID`, and the repository secret `IRIS_AGENT_PLAYBOOKS_CONTENT_API_KEY`. Use a content publisher credential. Keep credentials in environment or secret storage, never in a skill file or committed configuration.

[Draft sync workflow](../.github/workflows/playbook-sync.yml) validates every pull request locally. On main, it previews and uploads draft changes from the three sources and FAQs. It deliberately leaves serving publication unchanged. [Exact-version publication workflow](../.github/workflows/playbook-publish.yml) is manually dispatched with an entry key and numeric version after review. An optional GitHub environment can enforce a publisher approval if the team later wants that control; it is not required by this demo.

To use three real source repositories, place the same local validation/plan/sync steps in each source's workflow and point all three at the existing Playbook. Preserve globally unique skill keys and source metadata. Alternatively, a central workflow can check out the approved sources into separate directories before those same commands. The demo does not create remote repositories or register GitHub credentials.

For a real authoring policy, decide who may upload, who may publish, and what qualifies an agent-generated candidate for review. The console's convenience controls are an application feature and must not be confused with a claim that every governance workflow is supplied by Playbooks itself.

See the official [manage skills documentation](https://redis.io/docs/latest/develop/ai/context-engine/agent-playbooks/manage-skills/) for package and lifecycle semantics. CLI flags above were checked through the installed version's `--help` output.
