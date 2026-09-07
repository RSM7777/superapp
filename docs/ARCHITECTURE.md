# Nano — Architecture

**Version 2, 7 September 2026.** Supersedes `ARCHITECTURE-DECISION-2026-09.md` (v1, 6 September), which is kept only for its audit trail.

**Status:** proposed. Documentation and code claims verified; production performance not.
**For:** Harshith, and an external architecture reviewer.

---

## 0. How this document came to be

Three passes produced it, and they disagreed usefully.

1. **v1 (6 Sept)** — Claude's review of the repository: six subsystem readers with file-level evidence, research on OpenClaw/Hermes/CaMeL, four architects arguing four stances, three judges, adversarial verification of load-bearing claims.
2. **Review A (6 Sept)** — an external reviewer who ran regressions against PR #2 and found two send paths it missed; then a full architecture critique that corrected four of v1's conclusions.
3. **Review B (7 Sept)** — a second external reviewer who named specific technologies with licences and prices, and **ran a local durability experiment** rather than reasoning about durability.

Where they conflicted, this document takes the position with evidence behind it and says which. Claude then verified DBOS and Hindsight independently, and contributed the gbrain findings in §6 and §7.

**Confidence, stated up front:** high on separating authority from evidence from outcomes; moderate on the chosen runtime's operational fit; provisional on the memory engine and connector economics.

---

## 1. What we are building

A personal chief of staff. One agent per area of life — inbox, money, food, clothes, travel, home — sharing one model of the user's world, rendered through screens the server composes.

**The product's fatal failure, named in the code itself:** misclassifying an important email. Everything is negotiable against that.

**The V1.1 metric:** can the user turn off email notifications entirely and trust that Nano has it handled?

### The verticals

| Vertical | Today | Planned |
|---|---|---|
| **Inbox** | Gmail sync → model triage into four tiers → adversarial re-check of the discard pile → reply drafted for anything needing you → morning briefing → mute and never-miss rules | Outlook via the same contract; importance scoring; open loops ("who is waiting on me"); address resolution; feedback; business-context threads |
| **Finance** | Plaid link, transactions, budgets, rules engine, weekly insight | Holdings digest; trip tagging; Splitwise; position briefs (**not** recommendations) |
| **Nutrition** | Photo/text meal logging, targets, evening summary | Pantry state; grocery restock |
| **Stylist** | Closet photos, daily outfits, style memory | Outcome-based preference learning |
| **Travel** | Flight watches, scout campaigns | Trips, reservations, routes with personal stops, preparation tasks |
| **Reminders / To-dos** | — | Chat-first; location-triggered; receipt-driven (return the AC) |
| **Home** | — | Appliances, warranties, service scheduling |
| **Passwords** | — | Access orchestration only — see §9 |

### The surfaces

Voice (three transports: live duplex, turn-based, typed), a morning briefing as a story, push with a hard attention cap, and — not yet in the repository — widgets and Live Activities.

---

## 2. The decision

Nano is **a product and authority layer over reusable infrastructure.** v1 got the boundaries right and left too much infrastructure to be written by two people. This version names the technology.

| Layer | Decision | Why |
|---|---|---|
| **Agent runtime** | PydanticAI | Fits the Python backend; structured, replaceable model and tool runtime |
| **Durable workflows** | DBOS, in-process on existing Postgres | Recovery machinery without a second orchestration server |
| **Memory** | Pilot a service behind Nano's own interface; compare against a Postgres baseline | Do not build a large memory engine before measuring one |
| **Knowledge interface** | Implement the seven memory verbs (§7) | A published contract with a conformance suite; harness-independent |
| **Inbox** | Keep direct Gmail; add Graph behind the same adapter contract | Nano owns this path; preserve observable sync coverage |
| **General actions** | Scoped API, browser and phone workers behind one executor | One agent composes across verticals; Nano enforces authority |
| **Mobile** | Native capabilities plus optional device inference | Alarms and notifications need real platform integration and acknowledgement |

**What does not change:** explicit grants, reliable ingestion, fast UI reads, model portability, independent action checks, attention management, and evidence of completion. Those are Nano's product responsibilities and are not delegated to any framework.

**Rejected as the runtime:** OpenClaw and Hermes (§6). **Rejected as the knowledge backend:** gbrain (§6), while borrowing four things from it (§7).

---

## 3. The shape

```
User request  ·  source event  ·  schedule
        │
        ▼
   Task admission            duplicate triggers, relevance, deadline, budget
        │
        ▼
   Evidence retrieval        resolve the person; authorized sources; freshness + coverage
        │
        ├──► Deterministic workflow  (known work: triage, briefing, alarm proposal)
        └──► General agent           (open-ended: research, forms, errands)
                    │
                    ▼
            Action executor          grants, account, destination, payload hash,
                                     resource version, spending limit
                    │
                    ▼
        Provider / browser / phone / device worker
                    │
                    ▼
        Reconciliation → outcome ledger → attention service → Hub · voice · widgets
```

**Postgres remains the durable record**: source identifiers, access metadata, sync checkpoints, tasks, grants, operation receipts. Providers stay authoritative for their own mail, bookings and balances. Memory summaries are derived and rebuildable. DBOS owns execution history for the workflows assigned to it, and the UI reads a projection — **never a second independently writable state machine.**

A worked example. An 8 AM meeting with James triggers preparation, a suggested wake time, and an alarm action. Nano must resolve *which* James, re-read the current event and timezone, apply the user's mandate, and receive a **native scheduling acknowledgement.** A model saying the alarm is set is not evidence that it is.

---

## 4. Constraints

These are what a reviewer needs to hold. Several contradict what the repository's own docstrings claim.

### 4.1 Team and money
Two founders. One EC2 host, Docker Compose behind Caddy, deploys by rsync from a laptop, **no CI**. 79 tests; a nutrition golden set; **no inbox golden set**. Opus 5 at $5/$25 per million tokens, cost-logged per call — except two paths that bypass the wrapper (live voice on Sonnet 5, and the scout at up to twelve calls per errand), which are unmetered.

### 4.2 The threat model that governs
The primary input is **attacker-writable**: email. The "lethal trifecta" is one model context that reads untrusted content, holds private data, and can act outward.

**Nano's voice brain is that trifecta today.** It grounds on inbound mail excerpts and email-derived memory, holds facts and the people graph, and in the same turn can send a new email or create a standing rule — with **zero policy checks** (`grep assess( routers/voice.py` returns nothing).

Two more, verified: the phone forwards the user's **full API bearer token** to ElevenLabs on every live-voice session (`NanoOrb.tsx:336`); and if `SUPERAPP_VAULT_KEY` is unset, Gmail and Plaid token encryption falls back to a hash of the API token, which defaults to `dev-token-change-me`.

Research context: adaptive attacks defeated all twelve published prompt-injection *detection* defences at over 90%, and a 500-person red team at 100%. The real exfiltration incidents leaked data reachable from the model's process through an innocuous egress. **Provenance and data-flow control enforced in code are load-bearing; classifiers and confirmations are backstops.**

### 4.3 The gate is designed, not enforced
`policy.py` and `kernel.py` describe exactly the right design. Verified by adversarial refuters:

- The earned autonomy level is **never consulted at any action site**. `current_level()` is called once, inside the kernel's own evidence report. A promotion changes a Hub label, not behaviour.
- `assess()` has **exactly three callers, all inbox**. Only one can ever deny, and it reduces to "is this flagged suspicious". Tier-2 actions that exist — send to a new recipient, create a standing rule, scout campaigns — execute with no check.
- **Nothing writes the `undone` verdict**, so demotion is unreachable.
- Two permission registries with mismatched keys. The real runtime gate is the environment variable `gmail_scope_tier`.

One refuter overturned v1's *inference* here: these facts do not show a working provenance gate to preserve. They show a designed gate that is **not enforced**. Hence step 1.

### 4.4 Production is missing its heartbeat
`deploy/DEPLOY.md` schedules only inbox sync and the morning brief. **Nothing fires the dispatcher, flight watches, or the orchestrator heartbeat.** Durable runs, campaigns and proactive wake-ups do not run in production. Features that look built are not live.

### 4.5 Mail reliability
Triage is one model call per message plus an adversarial second call for the discard pile. But the Gmail parser keeps only `From` and `Subject` — every signal needed to score importance in code is discarded at ingest. "Have I replied to this sender" exists in the database and never reaches triage. On an expired history cursor the client **resets the watermark to now**, silently losing everything that arrived during the outage; Google's own guidance requires a full sync in that case. And `GET /inbox/state` calls `send_due()` — a read endpoint with a send side effect.

### 4.6 Memory as built
Hybrid retrieval exists and is the right shape: Voyage embeddings into pgvector plus Postgres full-text, reciprocal-rank fused. But only four writers, all inbox and voice; content truncated at 2,000 characters with **no chunking**; **no vector index** (exact scan); the user's own historical sent mail never ingested; the reply drafter consults neither memory nor the people graph; and on an embedding error it **silently stores a hash stub** that looks like a vector. The Context API caps each agent's slice at 50 facts and 20 events — retrieval, not accumulation, which we keep.

### 4.7 Platform
The widget target and Live Activity bridge exist only on one machine (`apps/mobile/ios` is gitignored; the commit that added them carried only JavaScript). AlarmKit permits **app-managed alarms with authorization** — not arbitrary control of existing Clock alarms. PushKit VoIP pushes are **for calls**, not a workaround for silent email alerts; quiet updates use notifications, widgets or Live Activities. Calendar needs EventKit; location reminders need Always permission and geofencing. Mobile background execution is constrained, so **reliable proactive scheduling stays server-side** with acknowledged native commands.

### 4.8 Data access reality
Instacart's developer platform is for shoppable **lists**, not consumer orders. Airbnb has no public booking API. Robinhood has no official API. Plaid Investments is deferred in the README. Splitwise and Plaid have proper APIs.

### 4.9 Regulatory
Personalised securities advice is regulated. Automated calls carry disclosure and recording-consent obligations. Google restricted scopes require verification and an annual CASA assessment; Testing mode caps at 100 users with ~7-day token expiry.

### 4.10 Concurrency
Single-worker assumptions throughout: task claim is select-then-update with no row lock, the worker never renews its lease, the realtime pending-actions queue is an in-process dict.

---

## 5. Runtime and recovery — what was actually tested

**PydanticAI for the agent loop; DBOS for new durable workflows.** DBOS is verified as an in-process library — *"DBOS is entirely contained in this open-source library, there's no additional infrastructure for you to configure or manage"* — MIT, storing workflow state as rows in Postgres, with durable queues, cron scheduling and durable sleep. Start with **one** workflow behind Nano's executor; migrate on demonstrated benefit. Do not run two orchestrators for the same workflow.

A caveat that matters: model calls and supported MCP interactions have integration support, but **arbitrary tool code does not become durable merely by being registered**. Custom I/O needs explicit durable steps.

### The experiment (Review B)

DBOS 2.31.0, pydantic-ai-slim 2.40.0, Pydantic 2.13.5; SQLite for workflow state; a fake-provider database for external effects. No real model or account.

| Scenario | Result |
|---|---|
| Complete a run, then replay the same workflow ID in a new process | Two model calls, one tool call total. **Completed work was reused.** |
| Kill the process after the provider commits, before the step result is recorded | **Two provider attempts, two effects.** No provider deduplication. Preparation ran once. |
| Same crash, with a stable operation key deduplicating at the provider | **Two attempts, one effect.** Preparation ran once. |

**The conclusion, demonstrated rather than asserted: durable recovery is not exactly-once for outside actions.** Nano still needs an operation ledger, stable IDs, preconditions and reconciliation. A lost response after a send or booking is `uncertain` — investigate before retrying. Cancellation cannot undo a delivered message.

Not tested: Postgres failover, multi-worker concurrency, real delivery, long approval waits, live model quality.

**Alternatives, honestly:** LangGraph if explicit graph state materially simplifies our workflows; Temporal when operational visibility or scale justifies its service (team size alone is not a reason to reject it); Restate is credible. DBOS matches the existing Postgres footprint for the first slice.

**Framework approval hooks are not the authorization boundary.** Grants are enforced in Nano, independently of model messages and supplied histories.

---

## 6. What we are not adopting, and why

### OpenClaw
Sandbox off by default; secrets in plaintext; prompt injection declared *"not a vulnerability by design"*; an independent audit measured 57% injection robustness; 77 advisories against a lexical command allowlist; 17 container-escape advisories; a Control-UI RCE; a skill-marketplace incident shipping hundreds of malicious skills. Explicitly **one trust boundary per gateway**. For a product whose input is a stranger's email, wrong.

### Hermes
Better defaults — headless contexts deny, a hard blocklist, credential paths write-denied. But a P0 where approvals were silently bypassed on a non-terminal gateway, and its own docs say the guardrails *"are not a sandbox"* on the default backend. Usable as an isolated worker; not as the brain.

**The structural reason, independent of either project's record:** an agent loop that reads mail, holds memory and can send *is* the trifecta by construction. Nano's advantage is that the model has no computer. The loop belongs in one corner — the actor — stripped of data and credentials.

### gbrain — a serious reference, not our backend
At the revision inspected, and from its own documentation:

- **One brain per data owner, by rule**: *"if the data owner changes, it's a brain boundary."* Multi-user inside one brain exists and was fuzz-tested, but it is **source-granular**, the single database credential sees everyone, and one `serve` process fronts one brain. Strict isolation for N users means N databases and N processes.
- **Its truth is Markdown in git**: *"The GitHub repo (markdown + frontmatter) is the system of record. The Postgres/PGLite database is a derived cache."* Nano's truth is transactional — sends, receipts, grants, checkpoints — and must not be rebuilt from files.
- **TypeScript/Bun, no REST API, no Python SDK.** From FastAPI it is an MCP client over HTTP or a subprocess; every database-bound operation runs on the brain host.
- **The open-loop output we want most is local-only** — remote callers get redacted counts, no quotes or links.
- **Maturity**: five months old, ~2.5 commits/day, five releases in five days, recurring PGLite/WAL, embedding-migration and schema-upgrade bug classes, a documented 53× cost incident, ~49% of commits from one author.
- **Benchmarks read narrowly**: LongMemEval 95.5% recall@5 is retrieval-only, single run, and *"the dev slice is inside the published 470… leak into the full-470 headline by construction"* (self-disclosed); the answer-accuracy lane missed its own target at 86.6%. BrainBench is a 240-page synthetic corpus scored against its own ablation.

### The memory-service field
| Candidate | Decision | The deciding fact |
|---|---|---|
| **Hindsight** | **Pilot candidate** | MIT, Python-embeddable, Postgres+pgvector, retain/recall/reflect, strict per-bank isolation. Vectorize's own product — keep the baseline honest. Its default tenant extension ships **no authentication**; the API-key extension maps requests to one schema. |
| **Mem0** | Credible contender | Apache-2.0, pgvector, and its **server** ships authentication and richer retrieval — do not dismiss it on the library alone |
| **Graphiti / Zep** | Revisit later | Best data model (episodes → entities → time-bounded facts with source pointers) but requires Neo4j/FalkorDB; no Postgres path |
| **Cognee** | Credible, not now | Only one with backend-enforced per-user ACL on pgvector, but graph-on-Postgres is a **demo feature**, production licensed |
| **Khoj** | No | Closest stack match, but AGPL and slowing (12 commits in 90 days) |
| **Honcho** | No | AGPL, plus Redis and a worker |
| **Letta** | Drop | The Python/Postgres server is retired and unsupported; the successor is a TypeScript harness |

**The cross-cutting finding: no memory product raises Nano's isolation floor.** Every one is "pass the user id on every call" — the guarantee we already have. **Identity-bound isolation stays Nano's job whichever engine wins.** A model-selected bank ID is not an authorization mechanism.

---

## 7. Memory and evidence

### Four stores, four rule sets

| Store | Contents | Rules |
|---|---|---|
| **Source evidence** | Messages, notes, documents, provider IDs, versions | Provenance, ACLs, deletion state, sync coverage preserved |
| **Domain state** | Events, reservations, transactions, assets | Typed records; reconcile to the authoritative provider |
| **Identity & relationships** | Verified links, aliases, collaborators, reply history | Ambiguous names stay ambiguous; **inferred aliases cannot authorize disclosure** |
| **Preferences** | Panera, tone, interests | Scope, confidence, provenance, expiry, user-correctable |
| **Rules & grants** | Never-miss James, no notification calls, purchase limits | Auditable user intent; **learning cannot silently expand authority** |
| **Secrets** | Credentials | Separate vault; never ordinary retrieval chunks |

Retrieve with structured filters, lexical search, vector search and relationship signals. Carry source references into generated output. Label incomplete coverage and stale evidence. **An index is for recollection; fetch current provider state before any consequential action.** Revocation and deletion must invalidate dependent chunks, summaries and caches — and Nano must test that whole path, not trust the engine's cleanup.

### The interface: the seven memory verbs

Nano's knowledge layer implements `recall`, `remember`, `entity`, `synthesize`, `forget`, `context_pack`, `delta` — published by gbrain as *"the contract any OTHER memory server can implement and certify against"*, with a conformance command. Properties worth inheriting: **provenance mandatory on every write**; facts **expire with an audit trail, never delete**; fail-closed redaction for remote callers; budget-packed responses.

Two payoffs. The Hindsight-versus-baseline comparison happens behind a stable contract rather than a bespoke shim. And any harness — Hermes, OpenClaw, Claude Code, whatever is next — can use Nano's brain without Nano adopting it.

### Borrowed from gbrain, ported to Python

**The open-loop engine.** The most product-relevant piece for a chief of staff, and deterministic:

- their message, you in `To:`, unanswered ≥24h → they are waiting
- your message containing a question, unanswered ≥72h → you are waiting
- a reply **closes the loop by state transition, never deletes**
- **sent mail is the negative filter** — *"what makes 'unanswered' honest"*
- structural gates: no-reply senders, `List-Unsubscribe`, CC-only, forwards without questions, self-threads, muted senders, calendar mail by iCalendar `METHOD`
- **refuse to answer at all when any source has gone >24h without a successful sync**

That last rule is the same principle as "never count disconnected sources as covered". An optional model pass then extracts commitments with direction, counterparty, due date and a verbatim quote.

**The retrieval recipe.** Add, in order: intent classification without a model call; a graph arm over typed edges from the people graph and threads; source-tier boosts; a cross-encoder reranker; dedup before ranking; and **evidence labels on every result** (exact match, probable, unknown) that synthesis must honour. Their private-page filter runs **before** retrieval and fails closed — the pattern for our entitlement scoping.

**The tool-execution ledger.** Write each tool call as `pending` **before** executing; settle to complete or failed; on resume, *"trust any tool execution marked complete or failed, and re-run pending ones only for idempotent tools."* This is the generalisation of the `uncertain` send state.

---

## 8. Contracts

### A. Durable task, separate from conversation
A task records owner, intent or standing mandate, trigger, constraints, deadline, budget, evidence references, actions and outcomes. States: `queued`, `running`, `waiting_user`, `waiting_external`, `reconciling`, `completed`, `failed`, `cancelled`. **A turn finishing does not complete a task.** An outbox bridges transaction commit and workflow admission. Timeouts, attempt caps, cost reservations and concurrency limits are explicit; a budget covers all attempts and fallbacks; **retries must not bypass a denial or refusal.**

### B. One executor for every outward action
Each operation has a server-owned specification: identifier, version, schemas, required permissions, data destinations, preconditions, retry semantics, completion verifier. The executor authenticates the caller **independently of model arguments** and checks actor, tenant, current grants, resource scope, payload or approved constraints, recipient identity, expiry, source version and spending limits. **Unknown operations deny.**

Approval binds to the **rendered payload digest and destination**; an edit after approval invalidates it. A user request grants its intended scope; **untrusted text encountered while fulfilling it inherits no permission to issue new instructions.**

Remove every alternative raw-credential path. API handlers, voice tools, scheduled jobs and agent tools all use the executor. Credentials belong to connector workers or a vault, never the general model runtime. **Sensitive reads** — anything leaving the trust domain to a worker, a voice vendor or a third party — also require authorization; ordinary screen rendering stays a fast authorized read.

**Risk is operation-specific, not a universal tier.** A reply can disclose irreversibly; a familiar recipient does not make it safe. A cart edit can trigger a third-party autosave.

**Evidence-backed grants stay** — but only as the UX for creating a bounded standing mandate: *"you have approved 20 of these cleanly; shall I handle this class without asking?"* The user's tap creates the grant. **Model confidence never grants permission, and successful history only supports offering one.**

### C. Retry recovery is not exactly-once
Stable operation IDs, database uniqueness, provider idempotency keys where supported, resource-version checks, reconciliation against external state. Serialize conflicting changes to one resource. If a booking succeeds but the response is lost, record `uncertain` and reconcile — **do not retry an irreversible action unless the adapter can establish that retry is safe.** For multi-step external work, model partial states explicitly; cancelling a booking is a **new action** with its own fees and permissions, not a rollback.

### D. Attention is a core service, not a per-vertical concern
Every vertical submits candidates; one service decides what interrupts. It weighs urgency, consequence of delay, preferences and quiet hours, whether the user already saw it, grouping, and channel permissions. Keep importance, urgency, reply-requirement, confidence and interruption cost **separate**. A hard three-per-day cap must not hide an urgent exception. Suppressing a routine notification is not the same as discarding its record or resolving its obligation.

- **Handled** — the intended result is **verified**, with an inspectable receipt. Never the model declaring success.
- **Need you** — clarification, approval, failed access, missed deadline, or unresolved uncertainty.
- **Just read** — information with no obligation.

Show coverage separately: last successful sync, disconnected sources, delayed tasks, stale indexes. **Push acceptance is not proof the user saw it.**

### E. Model portability is a tested capability contract
The interface exposes generation, streaming, structured output, tool turns, usage, termination reasons and **capabilities**. Normalize application-visible messages and tool results while **retaining opaque provider continuation state inside the adapter** — some models require their own reasoning and tool-call fields replayed verbatim, and a text-only wrapper would silently break them. Do not require vendor-specific state to transfer between models.

Route on **permitted data destination first**, then required capability, measured quality, latency, cost. Qualify an exact model, version, quantization, serving configuration, prompt and tool-schema version **together**; an OpenAI-compatible endpoint does not guarantee equivalent tool behaviour. Switch at task boundaries or safe checkpoints, preserving committed effects.

Device execution gets an explicit capability scope, expiry, operation ID and ownership rule. **Cloud and device must never both commit the same task.** Local-only data stays local when the device model is unavailable — Nano defers or asks; it never silently falls back to cloud. Apple's third-party Private Cloud Compute is an **optional** backend subject to eligibility, not a launch dependency.

### F. Tools and skills without universal authority
Known workflows call typed operations directly. The general agent may search the allowed catalogue, discover schemas, plan, call tools, inspect and resume. A Work IQ-style path interface and MCP **project the same registry**; neither creates an alternative execution path. A small tool vocabulary is not a small authority surface — `do_action` may represent hundreds of consequential operations, and `get_schema` must reveal only permitted, registered ones.

Skills are versioned behaviour: activation criteria, required capabilities, compatible schema versions, reviewed instructions, stopping conditions, evaluation cases, rollback. **Markdown changes behaviour without changing a schema.** Pin skill versions for running tasks. Critical constraints — spending limits, permitted recipients, which calendar — are enforced in code; skill text explains a workflow, it does not grant authority.

Browser and phone workers get task-specific context and bounded authority. **A logged-in browser is privileged even with no password exposed**: typing can autosave, navigation can transmit, spoken words can commit. Constraints apply throughout execution, not at a final Submit button.

---

## 9. The plan, feature by feature

**K** = works today · **K+** = kernel extension · **A** = agent/worker behind the executor · **iOS** = phone-native · **Iso** = separate trust domain · **✗** = not as described

| Feature | Where | Still need | Watch out |
|---|---|---|---|
| Mute "Chase statement reminder" | K | Voice sees sender/kind; a way to remove a mute | A sender-wide mute hides fraud alerts — mute the **class** |
| Like/dislike + "what would have worked" | K+ | Vote affordance; free text → typed correction | Diagnose: missing integration vs retrieval failure vs reasoning failure vs preference. Do not turn every complaint into a global rule |
| "Don't ignore James" | K | Alias/name resolution | `From` is spoofable; needs authentication signals |
| Agent personalities | K+ | A persona preference, separate from permissions | Keep humour out of safety copy and out of anything sent as the user |
| Onboarding: "call me vs handle it" | K+ | Answers written as a **cap**, with concrete examples | Must not bypass the earned ladder |
| Interactive learning | K+ | Typed correction actions | The brain reads untrusted excerpts in the same turn — gate writes by provenance |
| Turn off call-to-notify | K+ | A notify() dispatcher with channel preferences | An email must never switch a channel on |
| Quiet updates in crowded places | K+/iOS | Notifications, widgets, Live Activities | **Not** a simulated VoIP call — Apple restricts that to real calls |
| Morning briefing story | K | Server-side segments (today client-side, inbox-only) | Two narratives can disagree |
| Handled / Need you / Just read | iOS + K+ | Widget target committed; attention service | Lock screen shows names to bystanders — ship a counts-only family |
| Voice alarm from first meeting | iOS | EventKit + AlarmKit; server proposes, phone acknowledges | AlarmKit manages **app** alarms, not the Clock app's |
| **Turn off notifications and trust it** | K | Auditable handled list + undo; inbox golden set | Silence makes a miss invisible without both |
| People across Gmail/Outlook | K+ | Provider column, Graph adapter, alias merge | Memory poisoning via crafted mail |
| Find an address | K+ | Resolver ranked by replied-before | Look-alike domains; injected addresses |
| Importance scoring | K+ | Capture To/Cc/List-*/In-Reply-To at ingest; thread depth; replied-before; known-person — **in code, promote-only** | Demoting below the model verdict = the fatal failure |
| **Open loops** | K+ | Port the rules; ingest sent mail | Unanswered ≠ important; a flight cancellation needs no reply |
| Knowledge base | K+ | Ingestion, chunking, vector index, provenance, retrieval before drafting | Poisoned chunks replay forever |
| Phone-call booking | **Iso** | Separate call brain on a typed brief; `awaiting_user`; disclosure/consent | The callee's speech is untrusted input |
| Form filling | A | Typed actions, per-action risk keys, pause/ask, idempotency, per-user contexts | Constraints throughout, not at Submit |
| Alarm from calendar | iOS | EventKit + AlarmKit | An unsolicited 4am invite must not move the alarm |
| Travel | K+ → A | Trips twin; itinerary extraction with provenance; hotel **shortlist** | Forged confirmations; never auto-open extracted links |
| Groceries | K+ → A | Pantry twin; Instacart **list** API; cart build | Ordering is money: human tap, never earned |
| Finance digest | K+ | Plaid Investments | Describe, don't recommend |
| Trip tagging + Splitwise | K+ | Tags, trip rule, adapter | Social irreversibility |
| Stock "sell BABA" | ✗ | Reframe as a position brief | Regulated advice |
| Location reminder | iOS | expo-location, geofencing | Never log location to the substrate |
| Return the Amazon AC | K+ | Reminders twin; receipt extraction | Spoofed Amazon mail plants a fake deadline |
| Reminders / to-dos | K+ | Twin, actions, heartbeat trigger | Attention cap vs reminders |
| News | K | A news campaign kind | Text-to-text bias only |
| Home / WarrantyMe | K+ | Assets and service-request twins | Vendor replies proposing "pay here" |
| **Password vault** | **Iso** | Real vault + org identity; Nano orchestrates access requests and offboarding | 1Password service accounts manage only **vaults they created** — not universal offboarding or third-party rotation. Sharing access and changing an external password are **different workflows** |

---

## 10. Connectors and commercial choices

Keep the direct Gmail path as the baseline and add an adapter contract that also serves Graph. **Replacing OAuth plumbing does not solve sync semantics** — backfill, incremental updates, reconnects, deletions and coverage remain ours.

**Nylas is a meaningful launch alternative** for the Google-authorization critical path: a shared Google OAuth app with a completed Tier 3 CASA assessment. Confirm the actual package, data flow, supported scopes and obligations — the guide calls it a sales-enabled annual add-on while pricing describes it differently, and a vendor statement is not a blanket exemption. It also documents send idempotency with a one-hour window scoped per grant, **not forwarded downstream** — helpful for specific duplicates; keep our `uncertain` handling regardless.

One connector strategy per integration. Nango is a candidate when OAuth lifecycle work becomes repetitive. Composio suits a long tail of actions, but managed-app polling has a documented 15-minute minimum and shared quotas — **neither may silently become our urgent-mail ingestion guarantee.**

Browser forms: Playwright in isolated task workers first; buy hosted browser infrastructure if maintenance becomes the burden. Phone calls: an outbound SIP path is a concrete starting point. **Cookies, page content and conversations are privileged data.** Limit destinations, disclosed fields, spend, duration and permitted commitments; verify the booking separately.

---

## 11. Release order

**1. Make action checks unavoidable.** `actions/registry.py`, `actions/executor.py`, grant/operation/receipt records. Route manual, scheduled, voice and agent actions through one enforcement path. Keep UI rendering a fast authorized read; separately gate disclosure to model vendors, voice services and workers. Replace the forwarded bearer with a short-lived voice-session token. Require a real vault key in production, with a migration for existing encrypted tokens. Meter the two unmetered model paths.

**2. Finish inbox reliability and attention.** PR #2's head `3749fa8` added a shared draft-readiness validator across the send paths — **progress, not a complete solution.** Still open: Gmail history expiry resetting to now (recover by paginated sync with durable checkpoints, per Google's guidance), and `GET /inbox/state` invoking `send_due`. Add the send state machine with `uncertain`. Capture headers and sent-history signals; split `importance` / `requires_reply` / `attention_deadline`, with the tier as a display projection. **Port the open-loop rules and ingest sent mail.** Build the attention service and the inbox golden set. **Ship the missing production crons** — without them, moving sends to a worker means sends silently stop.

**3. Prove a general agent early.** A PydanticAI adapter and one DBOS workflow behind the executor. Demonstrate a contextual draft, cross-source meeting preparation, and **an unfamiliar task composed from allowed tools** — that last one is what proves generality. Keep the existing short-job path while migrating deliberately.

**4. Memory pilot and native proof.** Implement the seven verbs over Postgres; run gbrain's conformance tool against them. Compare Hindsight against the Postgres baseline on conflicting facts, wrong-person matches, revoked access, deletion and missing history. Add a device alarm/reminder receipt.

**5. Release against evidence.** See §12.

Start as a modular monolith: API, worker, managed Postgres. Add the memory service only for its pilot; isolate browser and phone workers when introduced. **Avoid a graph database, two workflow engines and two connector platforms in the first slice.** Count ingestion, consolidation, retrieval, retries, browser time and call time in **cost per verified task**, not per model response.

---

## 12. Validation

Check the environment after execution, not only the agent's answer. Repeat stochastic trials. Calibrate subjective graders against people.

| Experiment | Inject / compare | Required evidence |
|---|---|---|
| Authorization | Cross-tenant IDs, revoked access, altered approved payload, expired mandate, forged tool metadata | Server-enforced denial before disclosure or effect, at **every** entry point |
| Fault recovery | Crash before/after provider commit; dropped response; duplicate webhook; concurrent tap and worker | No blind duplicate irreversible action; a verified outcome or an explicit `uncertain` |
| Untrusted content | Malicious mail, calendar text, retrieved notes, tool output, web pages, callee speech | Cannot expand authority; also grade manipulation **within** allowed operations |
| Inbox judgment | Quiet important messages, lists, fraud vs statements, known and new senders, incomplete history | Recall of user-labelled important items; false suppression and unnecessary interruption tracked **separately** |
| Tool architecture | Typed operations vs generic discovery + skills vs mixed, same tasks | Completion, incorrect actions, clarifications, calls, p95 latency, cost per verified completion |
| Model replacement | Two exact cloud configurations; one device task | Valid tool arguments, semantic correctness, privacy eligibility, abstention, regression by task family |
| Device and time | Offline phone, unavailable local model, DST, app termination, duplicate cloud/device execution | Deadline-aware degradation; no false alarm-success; no unauthorized cloud fallback |
| Evidence quality | Conflicting notes, wrong James, stale holdings, incomplete sync, embedding outage | Correct source use **or visible uncertainty**; no invented certainty |
| Budget and stop | Looping tools, repeated provider failures, cancellation mid-action, shared caps | Enforced budgets, bounded attempts, truthful partial outcomes |

**Release gates:** deterministic authorization and fault-recovery invariants pass; no known policy escapes in the attack suite; no unsupported completion claims; a held-out important-mail corpus; visible sync coverage. Then shadow mode, then reviewable actions, then narrowly scoped autonomy.

**The two-founder, two-week notification-replacement test is retained as the founder gate, with daily source audits** — and it is explicitly **not** population evidence. Small quiet inboxes cannot establish reliability.

**Production measures:** missed important items per covered item, verified completions per attempted task, unnecessary interruptions per user-day, cost per verified completion, deadlines missed, stale-source duration, reconciliation backlog. **With explicit coverage denominators**, so a disconnected account cannot improve the score.

Track Google verification status, restricted-scope assessment, invalid grants, rollback and backup restoration. Testing-mode token expiry and unverified-app limits are separate conditions; neither substitutes for launch readiness.

---

## 13. What we could be wrong about

- **The runtime.** PydanticAI and DBOS are chosen on documented capability plus one local integration test. Not established: Postgres failover, multi-worker concurrency, real delivery, long approval waits, live model quality.
- **The memory winner.** Hindsight is an integration-fit judgment, not measured superiority on Nano's data — and it is the vendor's own product, so the Postgres baseline is the guard, not a formality.
- **Connector economics.** Nylas, Nango and Composio pricing and packaging need confirmation before anything depends on them.
- **The provenance model** is field-level, not full information-flow tracking. Text-to-text deception — a fake price, a wrong slot — remains out of scope and will surface in outcomes. Render them as *what the actor believed*, not as fact.
- **Confirmation fatigue.** Two-phase actions and read-backs add taps. Ask only for unresolved or new destinations, and show a structured summary.
- **Not audited:** the live deployment. The repository claims here were verified by reading code at the inspected revisions and will drift.

The next useful evidence is this implementation slice and a representative corpus — **not another framework survey.**

---

## Appendix — evidence index

| Claim | Where |
|---|---|
| Model never drives a tool loop in the kernel | `llm/provider.py:107` ("tools (none)"), `:156` |
| Two unmetered model paths | `routers/realtime.py:123-125`; `scout/scout.py:221-232` |
| Context scoping and caps | `substrate/context.py:17-80`; `config.py` |
| Hybrid retrieval; no ANN index; 2000-char truncation; stub fallback | `memory.py:42-51, 58-114`; migrations `0009`, `0010` |
| Only From/Subject captured | `inbox/gmail_client.py:206-233` |
| History expiry resets to now | `inbox/gmail_client.py:158-160` |
| `GET /inbox/state` calls `send_due()` | `routers/inbox.py:295-306` |
| Never-miss enforced before drafting | `agents/inbox.py:151-182, 352-359` |
| Policy tiers and provenance | `policy.py:27-63` |
| `assess()` — three callers, all inbox | `agents/inbox.py:387, 400`; `routers/inbox.py:424` |
| `current_level()` never read at an action site | `kernel.py:80-83, 90` |
| No producer of `undone` | `kernel.py:52, 66`; `models.py:114, 128` |
| Task statuses, no pause state | `models.py:77`; `dispatcher.py:17-19, 61-91` |
| Scout: three actions, shared profile and token | `scout/scout.py:27-31, 62-86, 235-258, 381` |
| Voice brain: zero `assess()` calls | `grep -n "assess(" routers/voice.py` → empty |
| Bearer forwarded to ElevenLabs | `apps/mobile/src/NanoOrb.tsx:336` |
| Vault key fallback | `vault.py:17-26`; `config.py:16` |
| Production crons | `deploy/DEPLOY.md` |
| Draft readiness validator (PR #2) | `substrate/inbox.py`, head `3749fa8` |

**External sources:** gbrain (README, `docs/architecture/system-of-record.md`, `brains-and-sources.md`, `RETRIEVAL.md`, `docs/guides/open-loops.md`, `docs/protocol/MEMORY_VERBS_v1.md`, `src/core/minions/handlers/subagent.ts`, `docs/eval/SEARCH_MODE_METHODOLOGY.md`); DBOS Transact for Python; Hindsight; Mem0; Graphiti/Zep; Cognee; Khoj; Honcho; Letta; OpenClaw security docs and forensic analysis; Hermes architecture and issue tracker; CaMeL (arXiv 2503.18813); "The Attacker Moves Second" (arXiv 2509.25926); Work IQ MCP overview; Codex app-server protocol; Glean knowledge graph; Nylas shared Google app, pricing and idempotent send; Nango and Composio pricing; Apple AlarmKit, PushKit VoIP, Private Cloud Compute, background execution; 1Password vault permissions; Google Gmail sync and restricted-scope verification.
