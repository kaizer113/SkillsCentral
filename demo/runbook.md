# SkillsCentral demo

Open the configured demo URL (application port `8084` by default). All procedures, thresholds, source teams, and retail records are fictional. The three source trees are local repository fixtures. The Iris service calls, model responses, and recorded application turns are real; no synthetic usage history is seeded.

This demo addresses four questions: where skills live, how their serving lifecycle is controlled, which procedures are used, and how an application can attribute estimated model spend to that use.

## Before the meeting

1. Open Integrations and check the deployed service statuses. Agent Playbooks, Agent Memory, Intent Router, Context Gateway, Lens, and Gemini are wired to existing services. Resolve an unexpected live error before presenting that part as working.
2. Open the catalog. The fixture has 15 skills across three sources: 10 initially published, four drafts, and one withdrawn. Counts can change after a presentation.
3. In return authorization, identify the **baseline** containing **30 calendar days** and the **candidate** containing **45 calendar days**. Note their actual remote version IDs. Earlier revisions remain in history; the version numbers can change after authoring or reset.
4. Confirm the baseline is serving and the candidate is available for review. The source file contains the candidate, and syncing it should preserve the current serving publication.
5. Use a fresh session for each policy comparison so an earlier answer cannot influence the next answer. Session and user IDs should accompany the Lens trace.
6. Keep Usage & cost available. Its history contains actual demo and verification turns. A use is defined by this application as loading the published procedure into model context; it is not proof that the model followed every instruction.

## A ten-minute path

| Time | Screen and action | Suggested talk track | Evidence to point to |
| --- | --- | --- | --- |
| 0:00–1:00 | Sources, then catalog | “Your authoring tools can stay where they are. We bring reviewed procedures into a serving catalog.” | Three source fixtures; owner, provenance, category, and lifecycle state. GitHub workflows are supplied examples, not a live remote-repository connection. |
| 1:00–2:00 | Inspect the baseline and candidate | “A revision can exist without changing what agents receive.” | Actual serving and candidate IDs; the 30-to-45-day diff; preserved earlier versions. |
| 2:00–3:00 | Ask the baseline prompt below | “The agent discovers published previews, then loads the relevant procedure.” | Discovered entry and version, full procedure load, response, and trace ID. |
| 3:00–4:00 | Publish the candidate; repeat in a fresh session | “Publishing changes serving guidance without redeploying the agent.” | Actual candidate ID returned by discovery; answer reflects the fictional 45-day rule. Check propagation through an actual read. |
| 4:00–5:00 | Withdraw, ask again, then restore the baseline | “Retirement removes content from serving while retaining history. Rollback selects a reviewed earlier version.” | No new load of the withdrawn procedure; baseline republished using its actual ID. |
| 5:00–6:30 | Ask the Gateway prompt below | “The model discovers relevant read-only tools through the existing Context Gateway and uses fictional order facts with the governed procedure.” | Gateway discovery step; `skillscentral__get_order`; SC-1001 result labeled synthetic and timestamped; final answer grounded in the current publication. |
| 6:30–7:30 | Inspect the turn trace and memory steps | “One agent turn contains the context and model calls, with a session and user identity.” | Trace ID, child operations, model tokens, memory recall, and conversation recording. Long-term promotion may be asynchronous. |
| 7:30–8:45 | Usage & cost | “This page is custom reporting over actual application events.” | Separate discovery/load counts; unused skills; measured tokens; explicit estimated-cost methodology. |
| 8:45–9:30 | Ask the support-hours FAQ | “A sufficient approved answer can avoid a generation call under our application policy.” | FAQ key, approved response, reported fast-path mode, and no model-generation tokens if that is what the turn records. |
| 9:30–10:00 | Integrations and deployment scope | “The context layer can support an existing agent platform and gateway.” | Existing services and runtime tool discovery. Explain the configured regional placement and cross-cloud network access. |

## Prompts to copy

Baseline and publication comparison:

> I bought an unworn jacket 38 days ago and I have the receipt. It is not final sale or personalized. Can I return it under the fictional demo policy?

Expected direction: the baseline does not meet the standard fictional 30-day window and offers specialist review; the candidate is within the fictional 45-day window, subject to the stated conditions. The agent must not claim that a return or refund was issued. Always inspect which actual version was loaded.

Gateway-assisted assessment:

> I bought an unworn jacket 38 days ago and I have the receipt. It is not final sale or personalized. Can I return it under the fictional demo policy? Please look up order SC-1001 to verify these details before assessing eligibility.

The fixed fictional order SC-1001 contains the jacket, proof of purchase, unworn condition, no final-sale/personalization exclusion, and purchase age of 38 days at its fixture timestamp. Look for actual runtime Gateway discovery and the order tool call, not merely a reassuring answer. The policy decision should use the currently published return procedure. The record is not a live retailer order, and its purchase age is relative to the fixed snapshot.

FAQ:

> What are the demo customer support hours?

The approved fictional answer is Monday through Friday, 9 a.m. to 5 p.m. Pacific time. It must not be presented as a real retailer commitment.

Delivery triage:

> Demo order SC-1002 was marked delivered yesterday at 1 p.m. Pacific time, but I cannot find it. What should I do?

Expected direction: collect the supplied tracking details, suggest checking the delivery location and household recipients, and prepare a handoff. Do not claim to contact a carrier or issue a replacement.

Missing knowledge:

> Can you approve a corporate travel reimbursement?

Expected direction: no relevant approved retail procedure; say the knowledge is insufficient. Do not invent a travel policy. Existing Intent Router intents and the application's no-match fallback are preserved.

## How to describe the four requirements accurately

| Requirement | What is demonstrated | Boundary to state |
| --- | --- | --- |
| Consolidate skills | Agent Playbooks stores and serves skill packages; this app adds a cross-source view and fixture provenance. | Source connectors and the console are application work. Three local fixtures are not three connected remote repositories. |
| Lifecycle, including retirement | Drafts, exact-version publication, withdrawal, version history, and republishing an older version. | A candidate is not automatically published. Withdrawal preserves history and differs from deletion. |
| Usage | Application events record previews discovered and full procedures loaded into model context; Lens traces turn/context operations. | This is custom instrumentation, not a claim that a packaged Playbooks usage-analytics product is generally available. A load does not prove successful procedure execution. |
| Cost per skill | The app records model-response tokens and associates an illustrative model-cost estimate with loaded skills. | It divides turn model cost equally across loaded skills. This is an attribution convention, not measured causal cost or billing. Configured defaults are illustrative $1 input/$5 output per million tokens, not a provider price quote. Iris, tool, VM, and support costs are excluded. |

Lens is labeled beta in the official documentation checked for this demo. Consult the live documentation before making a release-status or export commitment.

## Connected services and future work

Agent Memory recall and conversation recording use the existing store. Recording a session does not establish that a long-term memory has already been promoted. Automatic learning-to-FAQ is not demonstrated: a supported extraction path and human review would be a separate extension.

Context Gateway has a real configured upstream in namespace `skillscentral`. The three available tools read fixed fictional orders, inventory, and loyalty profiles. Runtime discovery supplies the tool descriptions; the application also enforces a read-only allowlist and a bounded model/tool loop. No tool issues refunds, reserves stock, or modifies real accounts.

The app and model run in GCP `us-east4`. Existing supplied Iris endpoints are reused and identify AWS `use1`. The demo has cross-cloud network access; do not describe it as an all-in-AWS or no-ingress/no-egress deployment.

## Leave the demo ready for the next run

Restore the baseline return procedure containing 30 days using its actual version ID. Leave the 45-day candidate available for the next presentation and legacy automatic refund withdrawn. Reset restores the intended lifecycle and retains immutable service history and actual usage records.

Stop or resume only SkillsCentral using [the service-control script](../scripts/demo-service.sh):

```bash
bash scripts/demo-service.sh stop
bash scripts/demo-service.sh start
bash scripts/demo-service.sh status
```

The VM hosts other demos. Stopping this container prevents its model requests, but existing Redis Cloud/Iris services and the shared VM retain their own billing. See [deployment operations](../docs/deployment.md), [the feature map](../docs/architecture.md), and [source synchronization](../docs/source-sync.md).
