# Nano consolidation plan

_Every architectural decision, in plain language. Generated from the design phase; the same source as the shareable page._

Nano becomes one agent you talk to, built in Muse's shape and running inside the FastAPI + Postgres body you already have. The spine is V2's: a single agent loop with a persistent thread, a folder of plain Markdown it keeps about you (SOUL, IDENTITY, USER, MEMORY, people, a daily log), skills as plain-English playbooks, a durable scheduler whose results land in the thread, subagents for parallel errands, and approval cards rendered outside the model's reach. Underneath, V1's discipline is installed at every seam where Muse is thin: every model call goes through V1's metered, cached provider; every tool call passes one authorize() check built from V1's risk tiers and backstops; memory writes go through one validated, secret-guarded, archived door; the inbox keeps its code-computed triage and a send tool that only accepts a vetted draft id; Postgres migrations and the 141 tests stay the regression net. Your months of UI survive as the card language and the tabs: the thread is home, V1's SDUI blocks ride the same WebSocket as cards with ids, and Hub, Inbox, Today (CalScreen), Me (Profile + Connectors + Memory), BriefPlayer and the NanoOrb sit around the thread fed by the same substrate the agent reads. Six buildable phases on the "consolidated" branch, each leaving the tests green; three decisions only you can make (which model, earned vs always-ask autonomy, which embedding model), none of which blocks the first two phases from running in stub mode.

## The verdict in one paragraph

**Muse's shape, V1's discipline.** Muse is a general agent with a folder of memory files, skills as playbooks, a scheduler and a chat with cards. That skeleton is right. But V2's port enforces almost nothing at its seams: tool permissions are advisory, memory writes have no guard, the model's shell inherits the vault key, there is no cost metering, and zero tests. V1 has exactly those organs. So this is Muse's skeleton with V1's organs, and V1's UI as the card language inside the thread.

## Three decisions only you can make

### Which model runs Nano's brain? You have no API key for either today, so phases 1-2 run in stub mode until you answer.

_Blocks phase 1._

1. A) Anthropic Claude through V1's provider: Opus 5 for chat with adaptive thinking, Sonnet 5 for subagents, Haiku 4.5 for triage and memory flush; keeps structured JSON output, prompt caching, batch pricing, server-side refusal fallbacks and cost metering; the loop is ported to Claude's tool-use streaming.
2. B) Meta muse-spark via its OpenAI-compatible endpoint (https://api.meta.ai/v1, META_API_KEY): closest to the Muse you used, but we build a second backend and replace four server-side guarantees (JSON-schema output, cache breakpoints, batches, refusal fallback) with client-side validation and retries, and cost tracking depends on the endpoint reporting usage.
3. C) Both behind one switch (about 400 extra lines) so you can A/B the same conversation and decide after a week of real use.

**Recommendation:** A. The safety gate does not depend on the model, but the metering, caching and the schema-constrained triage/draft steps do, and every V1 test already runs on this path. Since we are replacing Muse's prompts anyway, the behaviour you liked will need prompt iteration on either model; if after a week the feel is wrong, B is a bounded addition behind the same seam.

### Should Nano earn autonomy over time, or always ask like Muse?

_Blocks phase 2._

1. A) Earned: keep V1's decision ledger; after roughly 20 clean decisions Nano offers to stop asking for reply-to-sender emails and archiving; one cancel demotes it; money, new recipients and anything caused by an email always ask; promotion is a manual tap on the Me tab.
2. B) Always ask: every send and every change needs a tap forever; we delete the ladder, autonomy_grants and the promote/demote code; the 60-second auto-reply countdown for rules you wrote can stay or go with it.

**Recommendation:** A. The ledger and hard caps already exist and are tested, the countdown card is the only default-allow path either way, and it is one of the few things that gets better than Muse the longer you use it. Choose B only if you never want Nano to act without a tap.

### Which embedding model should power memory search? Nothing blocks until phase 4: search runs keyword-only with an honest 'degraded' flag until then.

_Blocks phase 4._

1. A) Local fastembed MiniLM (384 dims): free, no key, about 100 MB of onnxruntime in the API process, one migration to change the vector width.
2. B) Keep Voyage voyage-3.5-lite (1024 dims): what V1 uses today, cents per month at your volume, needs a key and network, already wired and tested.
3. C) Both selectable in config.

**Recommendation:** A for a personal project: no key to manage, no network dependency for memory, and the store, provenance and scoping are what matter; swapping later is one function plus one migration.

## All 36 decisions

### 1. Core loop · phase 1 · large

**Do:** Replace the six per-vertical 'think' pipelines with one general agent that reads its memory files, calls tools until it is done, and talks to you in a single persistent thread.

**Replaces:** V1 agents/base.py AgentSpec.think() and POST /v1/agents/{name}/think as the way the model is invoked; V2's loop as-is (OpenAI deltas, per-round prompt rebuild).

**Why:** Fixed pipelines cannot do 'move the dentist around the flight you found and tell Sarah'; one loop composes across every domain, and you have used Muse's version and it works. V2's loop is 283 readable lines and its handoff inbox already turns scheduled, subagent and connector results into the next turn.

**Beats Muse:** Every round is metered and cached through V1's provider, every tool call is gated, and the transcript has ids so the phone can page history instead of replaying everything.

### 2. Core loop · phase 1 · small

**Do:** Let the model's API shorten long conversations for us (server-side compaction) instead of writing our own summariser, and run an hourly memory flush so nothing important is lost when history is condensed.

**Replaces:** V2 loop.py:113-136 client-side compaction (re-summarises its own summary past ~64k tokens); the synthesis's plan to rewrite it by hand.

**Why:** All three judges pointed out the Messages API now offers server-side compaction on Opus 5 and Sonnet 5 (beta compact-2026-01-12), which removes the least-tested new code in the design. We only need to store the compaction blocks the API returns in the thread table and keep a client-side fallback behind a flag if the beta is unavailable.

**Beats Muse:** Compaction cannot corrupt itself, and the hourly flush writes what it learned into MEMORY.md through the guarded write tool with an archive trail.

### 3. Provider · phase 1 · medium — **you decide**

**Do:** Make V1's LLMProvider the only door to any model, add a streaming tool-use call for the loop, and (recommended) run on Anthropic; if you choose Meta's muse-spark endpoint we add a second backend behind the same door.

**Replaces:** V2 llm.py hard-coded to https://api.meta.ai/v1 (verified: META_API_KEY, model muse-spark-1.3) with no usage, retries or cost; V1 realtime.py's direct Anthropic call.

**Why:** V1's provider is the only place in either codebase that knows what a turn costs, caches the prompt prefix, forces JSON-shaped answers for the risky inbox steps, surfaces refusals and runs offline in tests. The judges agreed product-first's claim that the Muse model cannot be called outside Muse was wrong, so this stays a genuine choice for you with a clear recommendation.

**Beats Muse:** Every role's every round has a cost line; triage and drafting get schema-valid JSON without retries; tests run with no key.

**The question:** Which model runs Nano's brain? A) Anthropic Claude through V1's provider (recommended): Opus 5 for chat with adaptive thinking, Sonnet 5 for subagents, Haiku 4.5 for triage and memory flush; keeps structured output, prompt caching, batch pricing, refusal fallbacks and cost metering, and the loop is ported to Claude's tool-use streaming. B) Meta muse-spark via its OpenAI-compatible endpoint: closest to the Muse you used, but we build a second backend and replace four server-side guarantees (JSON-schema output, cache breakpoints, batches, refusal fallback) with client-side validation and retries, and cost depends on the endpoint reporting usage. C) Both behind one switch (roughly 400 extra lines) so you can A/B the same conversation. You have no key for either today; phases 1-2 run in stub mode until you answer.

### 4. Cost and observability · phase 1 · small

**Do:** Route cheap work to cheap models, fix the stale price table, and add a daily spending cap that pauses background jobs plus a 'what did you cost this week' tool.

**Replaces:** V2's total absence of metering and effort 'high' everywhere; V1's $0 for unknown model ids and Sonnet 5 listed at $3/$15 (current first-party rate is $2/$10).

**Why:** A 60-round agent turn is the most expensive thing either codebase can do and V2 cannot see it. V1's metering exists and is tested; it needs the loop routed through it, correct prices, a family-based lookup so dated snapshots are never free, and a ceiling so the first real bill is not a surprise.

**Beats Muse:** You can see what a day of Nano cost, per skill, and it stops itself at a limit you set.

### 5. Prompts · phase 1 · medium

**Do:** Keep V2's prompt-assembly structure, and build our ~25 blocks by ADAPTING Muse's material rather than writing blind: the replication kit's agent_spec.md and soul.md are the source of truth for behaviour, the ~234 undamaged blocks in the five roles we actually run supply wording, the 13 files that say Muse or Meta get renamed, and every muse.* tool reference is mapped to ours or the block is dropped. Assemble once per turn so the cache works.

**Replaces:** The earlier plan to write all 25 from scratch; V2's per-round rebuild with a seconds-precision clock; the 34 blocks damaged at the source and the ~20 builder roles we will never run (artifact, spaces, ideas, deep research, media upload).

**Why:** The user is right that 'made for Muse' is a rename, not a reason: only 13 of 268 source files name Muse or Meta. What cannot be renamed is damage at the source (31 files with another file's path fused in, 3 with binary garbage; the archive is the broken files, not a fix for them), a missing assembly recipe (no roles manifest was ever captured, which is why 193 blocks were unreachable), and 41 files that drive Muse-only tools such as muse.finish_step. The kit's 102-line spec is exactly the behavioural checklist the plan wanted, already written and clean.

**Beats Muse:** We keep Muse's tuned wording for initiative, memory doctrine and safety where it is good, lose nothing to extraction damage, and a prompt-honesty test fails on any phantom tool the adaptation misses.

### 6. Memory · phase 1 · medium

**Do:** Give each user a folder of six plain Markdown files the agent reads every turn and keeps current (SOUL, IDENTITY, USER, MEMORY, people pages, a daily log), and keep records (mail, meals, purchases, transactions) in the existing Postgres tables; the agent can only change the files through one memory.write tool that validates, refuses secrets, caps size and archives the previous version.

**Replaces:** V2's eight standing files plus four bank files edited with generic file tools and no guard (AGENTS, TOOLS, groups and bank were never written by any V2 role, verified in files.py); V1's opaque JSON facts that no prompt ever read (to_prompt_dict has zero callers).

**Why:** Self-maintained files you can open are what make Muse feel like it knows you, and V1 has no equivalent. V1's write_fact already has the validator, secret guard and supersession archive V2 lacks, so the tool wraps it; user_facts stays as the machine-readable mirror for rules code must read (mute, priority, auto-reply).

**Beats Muse:** Every memory edit leaves an archived previous version with who wrote it and when, secrets are refused at the door, and a Memory page in the app lets you read and correct the same files.

### 7. Context assembly · phase 1 · medium

**Do:** Inject only the capped memory files plus a one-line, code-computed status header (unread count, drafts pending, memory index degraded, auto-send about to fire); everything else the agent fetches through scoped read tools.

**Replaces:** V1 substrate/context.py's eager slice of 50 facts, 20 events and every twin per pipeline; AGENT_SCOPES survives as the visibility table for subagents and scheduled workers.

**Why:** Eager injection grows without bound, duplicates what tools return and breaks the cached prefix. The status header tells the agent when it must not act on its own (degraded recall) instead of leaving it to discover, which Muse never does.

**Beats Muse:** Nano can say 'my memory index is behind, I won't auto-send' in plain words; Muse injects files uncapped and tells the model nothing about its own state.

### 8. Tools · phase 1 · medium

**Do:** Port V2's tool registry, but derive each tool's schema from its Python function, register only functions that actually have code behind them, enforce who-may-call-what at dispatch, and run every connector in-process rather than as a shelled-out command.

**Replaces:** V2's captured tool JSON (46 of 100 functions with no backend), muse.exec-driven connector CLIs, and a dispatch that ignores visibility (registry.py:115-125); V1's REST routers as the only way to reach vertical code.

**Why:** One user on one process gains nothing from subprocess connectors, and that is where V2's worst bugs live (the model's shell inherits the vault key; a 600s approval wait outlives a 60s exec timeout). V1's in-process clients already 'raise, never pretend' and are tested.

**Beats Muse:** The model is never told about a capability that fails, and no tool subprocess ever sees a secret.

### 9. Safety · phase 1 · medium

**Do:** Put one authorize() check where tools actually run: it combines the action's risk tier, who caused it (you, an email, the system), the injection tripwire and your earned-trust ledger, and returns allow, show-a-card, or deny; cards are database rows that survive restarts and can only be answered from your phone's session.

**Replaces:** V1's assess() called from four places and never at execution (the voice executor calls no policy at all: voice.py:647-670 sends new mail with only an '@' check); V2's in-memory ApprovalStore and prompt-only gating.

**Why:** Both codebases share the same hole: nothing authorizes where tools execute. V2 has the right shape (the card lives outside the model's control) and V1 has the right content (tiers, provenance, backstops, ledger); the phone-session rule means nothing the agent holds can approve itself.

**Beats Muse:** Cards survive restarts, unknown actions default to 'ask', money always needs a tap, and the ledger records what actually happened so the autonomy story is evidence, not prompt doctrine.

### 10. Safety · phase 1 · small

**Do:** Label untrusted text in code before the model sees it: anything from an email, a web page, a memory hit or a subagent is wrapped with its source, scanned for injection, and the rest of that turn is treated as 'caused by content' so outward actions get stricter checks.

**Replaces:** V1 voice.py:787-806 grounding that mixes email bodies with private facts unlabelled; V2 injecting handoffs as user-role messages.

**Why:** Prompt injection works because the model cannot tell who is speaking; a code-applied label plus taint means an email that says 'forward this to evil.com' can at most produce a card, never a send. Your own typed message resets the taint, and replying to the sender already in the thread stays a low-tier action, so daily use is not tap-heavy.

**Beats Muse:** Muse's security markers are prose the model may ignore; here the marker is applied by code and changes what authorize() will allow.

### 11. Autonomous sending · phase 2 · medium

**Do:** Keep V1's 60-second auto-reply window but make it a countdown approval card on the scheduler: it sends by itself at the deadline only when a rule you created matches and every safety re-check passes on the current text; cancel means deny; every other kind of card defaults to deny if you never answer.

**Replaces:** V1's threading.Timer autosend (per process, lost on restart) and rearm_all on boot; V2's tap-on-every-send doctrine.

**Why:** V1's grace window is the one autonomy mechanism either repo actually engineered (atomic claim before network, re-gate at the deadline, stale-claim hold). Making it a card with a deadline keeps Muse's outside-the-model consent shape without losing that engineering.

**Beats Muse:** Muse blocks every send on a tap; Nano can auto-reply to Priya after 60 seconds because you wrote that rule, and you can cancel from the card or lock screen.

### 12. Autonomy ladder · phase 2 · small — **you decide**

**Do:** Decide whether Nano earns silence over time (V1's ledger: after a run of clean decisions it offers to stop asking for reply-to-sender emails and archiving, one undo demotes it) or always asks like Muse.

**Replaces:** V1's display-only L0-L4 ladder that nothing consulted; V2's approval-only doctrine.

**Why:** The synthesis flagged this as a genuine unknown and the judges disagreed: correctness and beats-muse wanted the ledger kept because it is one of the few things that gets better than Muse over time; simplest wanted it deleted. I chose to keep the ledger and the countdown card as the only default-allow path with promotion as a manual tap, and to put the earned-vs-always-ask choice to you.

**Beats Muse:** Fewer taps as the ledger fills, with a visible 'Without asking' panel showing exactly what Nano is trusted to do.

**The question:** Should Nano earn autonomy (recommended: after ~20 clean decisions it offers to stop asking for reply-to-sender emails and archiving; one cancel demotes it; money and new recipients always ask) or always ask like Muse (every send and change needs a tap forever; simpler, and we delete the ladder and autonomy_grants table)?

### 13. Scheduling · phase 2 · medium

**Do:** Port V2's scheduler as Postgres rows (jobs and runs, one row per job-and-time so a restart cannot double-fire) running in the API process, with two job kinds: an agent prompt or a Python function; all of V1's background brain moves onto it and the external crontab is deleted.

**Replaces:** V1's curl crontab (documented for inbox only, so reflection, decay and dispatch never ran), threading.Timer and Starlette BackgroundTasks; V2's Markdown job files, bash hooks and shared 2-thread pool.

**Why:** V2 makes background work durable, restart-safe and agent-creatable (cron.add from a conversation), and its results come back into the thread. The Markdown mirror and bash hooks add a second source of truth one user does not need, so rows only (simplest's version) with separate pools and cooperative cancellation.

**Beats Muse:** Heavy per-message work (inbox sync, triage) runs as metered code jobs on a cheap model, every scheduled action is still gated, and a restart note tells the agent what was cut off.

### 14. Inbox pipeline as tools · phase 2 · large

**Do:** Split V1's inbox sync into a scheduled code job (fetch, code-computed signals, triage and verify on the cheap model, store, summary handoff) and a set of chat tools (list, read, live search, draft, edit draft, send, archive, rules); inbox.send accepts only the id of a draft whose row is marked ready.

**Replaces:** V1 agents/inbox.py's 190-line _sync interleaving and routers/inbox.py as the only path; V2's gmail skill CLI where the model composes the send body itself.

**Why:** Triage on every incoming message is a cost and latency problem best kept in code with a schema, not a tool round each; drafting and sending are decisions the agent should make with you. Keeping each step's schema and fallback inside the tool preserves the guarantee that a refusal returns an unsendable DraftResult, never a cheerful yes (inbox.py:413-492).

**Beats Muse:** The send tool takes an id, the body was gated at draft time and re-gated at send time, and the evidence the drafter saw is scoped to the correspondent and labelled untrusted.

### 15. Skills · phase 2 · medium

**Do:** A capability is a folder with a SKILL.md playbook and a manifest (tools, action keys, risk tiers, connector); the catalog lists a skill only if every tool it names has code behind it and its connected status comes from the vault.

**Replaces:** V1's 17-touch-point vertical checklist and three hand-synced registries; V2's 55 skill folders backed by 2 real CLIs, with manifests nobody read.

**Why:** Adding grocery to V1 cost ~1,900 backend lines across 14 files and still shipped without its hub card, cron and client handlers; a skill is prose plus a few functions and appears in the prompt and hub automatically. V2's catalog lies about what exists, which is the one thing a playbook must never do.

**Beats Muse:** An honest catalog: manifests are actually read for approval tiers and status, and a CI test fails if a SKILL.md names a tool that does not exist.

### 16. Verticals · phase 3 · large

**Do:** Every V1 vertical (nutrition, grocery, finance, stylist, people, flights) becomes tools wrapping its existing think() steps and loaders, a SKILL.md, and screen builders for cards and tabs; the orchestrator dissolves into scheduler jobs and the hub becomes a deterministic payload.

**Replaces:** V1 agents/{nutrition,grocery,finance,stylist,orchestrator,hub}.py as registered agents, SCREEN_AGENTS and _REGISTRY; hub block-plucking heuristics.

**Why:** The vertical code is good (grocery has 30 pure tests) and only its wiring was the problem. Exposed as tools the loop composes them: 'what should I eat given the fridge and my budget' is nutrition.today + grocery.context + finance.summary in one turn.

**Beats Muse:** Muse has no nutrition, grocery, finance or wardrobe substrate at all; these are typed records with tests and real connectors (Gmail with recovery, Plaid, Instacart handoff).

### 17. Subagents · phase 3 · medium

**Do:** Port V2's subagents (parallel helpers for research) with per-user ownership, enforced timeouts, a pool of four and a cheaper model; a helper is always strictly weaker than its parent, cannot send, spend or edit memory, and cannot raise a card (a gated action bubbles up to your main thread).

**Replaces:** V1's external scout worker (single-tenant, shared Chromium profile); V2's process-global SPAWNS/POOL with no ownership and unenforced timeout_s.

**Why:** Cheap parallelism is part of why Muse feels capable; V1 only had it through a worker with cross-user defects. 'Children are weaker than parents' is a one-line invariant that closes a whole class of leaks (safety-first's graft, endorsed by two judges).

**Beats Muse:** A hijacked research errand cannot send mail, spend money or edit memory because the exclusion is enforced where the tool runs, and you never get a card you lack context for.

### 18. UI: thread · phase 1 · large

**Do:** The chat thread is the home screen, streamed over one WebSocket using V2's frame protocol, plus a new 'screen' frame that carries a V1 SDUI card (draft with countdown, meal rings, shelves, timelines) rendered by V1's existing renderer inside the thread.

**Replaces:** V1's six polling loops and think-on-refresh; V2's three fixed card types, index-keyed messages and full-transcript replay.

**Why:** A general agent's primary surface is its thread and V1 has no thread at all. V1's 17 block types are exactly the structured, glanceable state a chat bubble cannot carry, and V2 already proved HubScreen fits over a code-built payload.

**Beats Muse:** Skills emit typed cards with ids you can dismiss or tap, through a tested renderer with version gating, instead of text plus three hard-coded cards.

### 19. UI: tabs · phase 3 · large

**Do:** Five tabs: Hub (your HubScreen over a deterministic payload), Chat, Inbox (your InboxScreen, native), Today (your CalScreen, native), Me (ProfileScreen merged with Connectors and a Memory page); Finance, Stylist and Grocery open as block screens from the Hub grid; BriefPlayer stays a full-screen overlay; NanoOrb stays docked over everything; the Flights screen folds into the thread as cards and a Hub timeline row.

**Replaces:** V1 App.tsx's SCREENS router; V2's placeholder Ideas/Goals/Library tabs; V1 FlightsScreen and ScoutCard.

**Why:** Inbox and Today are stateful views (countdowns, swipe, water sheet) a block tree cannot express, so they stay native; the rest already render from blocks. Folding Flights is the one place I go against 'keep every screen', marked explicitly: it was already a chat thread with result cards, which is exactly what the main thread now is, and two judges asked for the fold.

**Beats Muse:** Muse's tabs are 50-150-line lists whose taps become prompts; ours are real views of the same data the agent sees and refresh instantly without a model call.

### 20. UI: refresh · phase 3 · small

**Do:** Pull-to-refresh just re-reads the database (instant, no model), and an 'Update with Nano' button posts a visible chat message so any model call shows up in the thread; polling loops are replaced by push notifications over the socket.

**Replaces:** V1's POST /screen/{name}/refresh that silently ran think() with a 6-second client guess; six setInterval loops.

**Why:** A hidden model call on a gesture is unpredictable in cost and time. V2's tap-becomes-chat pattern makes every model call visible and cancellable.

### 21. Voice and channels · phase 2 · medium

**Do:** The orb becomes a way to type: on-device speech goes into the same thread, replies are spoken through V1's cached text-to-speech, BriefPlayer plays the morning brief; Telegram and WhatsApp become channels into the same thread; the separate voice 'brain' and the ElevenLabs realtime path are removed.

**Replaces:** V1 routers/voice.py's CONVERSE executor (ungated, strips the suspicious flag, stub fallback can send) and routers/realtime.py (bypasses the provider); V2's timer-based orb handoff.

**Why:** The voice executor is the single most dangerous piece of V1 because it calls no policy at all; routing voice through the loop makes it gated for free. Realtime is dropped rather than flagged (argued, marked): it needs a key you do not have, re-plumbing it is a phase of work, and two judges sided with dropping.

**Beats Muse:** Multi-transport (orb, Telegram, WhatsApp) into one gated loop with one transcript, and BriefPlayer's audio-clock captions solve the handoff Muse's orb fakes with a timer.

### 22. Onboarding · phase 3 · small

**Do:** First minute is V2's three-step form (your name, Nano's name and vibe, what's on your plate) which seeds the memory files and triggers a greeting in the thread; second hour is V1's identity interview offered as a skill; Google sign-in gets an allowlist of your one or two emails.

**Replaces:** V1's unreachable full-screen InterviewScreen and refusal branch that writes '(stub distillation)' permanently; V2's form-only onboarding with no allowlist.

**Why:** V2's bootstrap is the better first minute and V1's interview is the better second hour. Any verified Google account provisioning itself is unacceptable even for two users.

**Beats Muse:** An adaptive interview that produces durable, provenance-stamped identity beliefs, offered as a card, not required.

### 23. Retrieval: what gets indexed, and how it ranks · phase 4 · medium

**Do:** Stop embedding every synced email; search mail live like Muse does, and index only what is memorable: your memory notes (with file#line citations), notes you import, sent replies, and threads that mattered. Rank the way Muse does: how well it matches, boosted by the importance tagged when the memory was written and by how recently it was last confirmed (90-day half-life), reranked by a cross-encoder, with a score floor so weak matches never surface, and the search tries one to three phrasings of your question.

**Replaces:** V1's habit of chunking every synced message (the source of the migration-0027 degraded-recall reset) and its ranking by match alone (event_at stored, never used); V2's embedded Qdrant with a cross-user singleton.

**Why:** Ninety-five percent of mail is never asked about and thread context already lives in the inbox table. The ranking is Muse's, confirmed two ways: its config in the archive (match 0.7 / keywords 0.3, importance prior 0.15, recency prior 0.1 with a 90-day half-life, rerank top 20) and Muse's own description of the behaviour (importance is tagged at write time, a September 9 correction outranks the September 8 version, a score floor, several phrasings per search). V1's store keeps the provenance, SQL scoping and honest degraded flag underneath.

**Beats Muse:** Three things Muse's own schema allows and its ranking never uses. Importance is not frozen at write time: a memory that keeps being used in replies moves up and one that is surfaced and ignored does not, a learning-to-rank signal Muse says it cannot see whether it has, and we get for free from the turn log. Decay is per kind, so a preference fades over years, a state in days, and a commitment expires on its own date, instead of one 90-day half-life for everything. A superseded fact is not hidden but returned with what replaced it and when. Plus: every recalled line says who said it, where and when; a degraded index lowers autonomy instead of pretending; memory.explain shows the full receipt for any hit.

### 24. Retrieval: embedding model · phase 4 · small — **you decide**

**Do:** Choose the model that turns text into searchable vectors: a free local one (recommended) or the hosted Voyage model V1 uses today; nothing blocks until phase 4 because the store already runs keyword-only with an honest degraded flag.

**Replaces:** V1's Voyage voyage-3.5-lite (1024-d, needs a key); V2's fastembed MiniLM (384-d, local).

**Why:** Safety-first's recommendation to keep Voyage rested on a wrong cost (V2 uses fastembed + onnxruntime, roughly 100 MB, not torch). For a personal project a free, keyless model is the lower-tier choice the user asked about, and swapping later is one function plus one migration for the vector width.

**Beats Muse:** No API key for memory, and provenance on every hit.

**The question:** Which embedding model should power memory search? A) Local fastembed MiniLM, 384 dims, free, no key, ~100 MB dependency in the API process, one migration to change the vector width (recommended for a personal project). B) Keep Voyage voyage-3.5-lite (1024 dims, what V1 uses today, cents per month, needs a key and network). C) Both selectable in config. Until you answer, search runs keyword-only and Nano knows its recall is degraded.

### 25. Data · phase 1 · small

**Do:** One Postgres under V1's tested migration chain plus five new tables (agent_messages, approvals, scheduler_jobs, scheduler_runs, push_tokens) and one folder per user on disk for the memory files and workspace; V2's 194-table ported schema is never imported and V1's dead tables are dropped at the end.

**Replaces:** V2 db/schema.sql (14 of 194 tables used) and per-user Postgres; V1 push tokens stored as confidence-1.0 facts in the orchestrator prompt.

**Why:** V1's chain is linear, idempotent and guarded by test_migrations.py; 180 inert tables are pure risk. One database and one folder per user is the smallest data layer that carries both memory layers.

**Beats Muse:** Records have ids and migrations instead of whole-file JSON PUTs, and push tokens never enter a prompt.

### 26. Deploy · phase 4 · small

**Do:** One process (single uvicorn worker with the scheduler thread inside) plus Postgres via the existing docker-compose behind Caddy; the container runs migrations before starting; no per-user Fly cells or gateway.

**Replaces:** V1's Dockerfile racing create_all against migrations; V2's Firecracker cells, gateway, wake-ahead and idle-exit.

**Why:** Cells solve a multi-tenant privacy problem a single trusted host does not have, and carry unproven bugs (per-boot signing keys, state routing, provision-on-any-sign-in); all three judges agreed to drop rather than defer them, against the synthesis. A migration hook is the one deploy fix the evidence demands.

### 27. Shell and browser · phase 4 · large

**Do:** No shell in the chat until phase 4; then file tools jailed to the user's workspace, a command tool only helpers can use with a secret-free environment, and V2's browser worker (you can take over from the phone) with payment fields detected by field type and URL, never by button text.

**Replaces:** V2 muse.exec with the daemon's full environment and the button-text sensitivity regex; V1's scout Playwright worker with a shared profile.

**Why:** Errands on sites without OAuth are part of what makes Muse general, so unlike simplest-that-works I keep them rather than delete them, but V2's version hands the model the vault key. Deferring costs nothing the first three phases need and lets the authorize() seam land first.

**Beats Muse:** Secrets are never in the model's shell; a checkout page produces a card before any card field is typed, defaulting to gated on error.

### 28. Tests · phase 1 · medium

**Do:** V1's 141 tests stay green at the end of every phase; each phase names which existing tests are rewritten or deleted when it retires an endpoint; new suites cover the loop, authorize, approvals, scheduler, memory, skills catalog honesty and prompt honesty; export_sdui_schema --check runs in CI.

**Replaces:** V2's zero tests; agent-first's vague 'existing tests untouched' / 'update call sites'.

**Why:** The regression net is the reason the consolidation can be done in phases at all, and test_spine exercises every endpoint we retire (voice/converse, telegram, orchestrator/think, tasks, interview). Naming the disposition per test is what makes 'green at every phase' checkable.

### 29. Dead weight · phase 5 · small

**Do:** A final phase deletes every module the new spine made redundant (orchestrator, hub agent, dispatcher, scout, realtime, the old voice brain, dead screens) with a cleanup migration, so the backend ends up smaller than the 13.5k lines it is today.

**Replaces:** Agent-first's phase 4 that deleted some dead code but never made the codebase smaller.

**Why:** One person has to be able to hold this program in their head. A grep-based done-when (no crontab, scout, Outlook, ElevenLabs, LiveKit references) makes the deletion real.

### 30. Prompt blocks: adapt, not clean or rewrite · phase 1 · medium

**Do:** Start from agent_spec.md and soul.md, borrow wording from the undamaged blocks, rename the 13 Muse/Meta references, map or drop the 25 muse.* tool names; enforce it with a test that every tool, file and skill a block mentions exists.

**Replaces:** scripts/port_blocks.py's repair-by-regex of the damaged extraction, and the plan to write from scratch.

**Why:** Cleaning 268 files of which 34 are damaged at the source, with no assembly order, is more work and less reliable than adapting the 234 that are whole. Writing from scratch throws away Muse's tuned wording, which is the thing the user values. Adapting keeps the voice and the honesty test keeps the drift out.

**Beats Muse:** Each block cites the tool or table it talks about, so a reference to something we do not have is a failing test instead of a confused agent.

### 31. Skills: Nano writes its own · phase 3 · small

**Do:** Nano can create its own skills: when a task turns out to be repeatable, it drafts a SKILL.md into your workspace skills folder using Muse's skill-creator playbook, and the catalog picks it up next turn.

**Replaces:** Nothing. This is what Meta markets as 'automated skill creation'.

**Why:** It is a 53-line playbook plus one catalog rule to scan user-authored skills, not a subsystem; I had wrongly lumped it in with the twelve-table engine below. Cheap, and it is a large part of why Muse keeps getting more capable for one person.

**Beats Muse:** A self-written skill goes through the same honesty test and manifest rules as ours, so Nano cannot write itself a skill that names a tool that does not exist.

### 32. Learnings · phase 3 · medium

**Do:** Separate from remembering facts, Nano keeps learnings about HOW to do things for you ('when he asks for a summary he wants three bullets, not prose'), extracted by the hourly memory flush; each records whether it was adopted and how it turned out, and adopted ones enter the prompt.

**Replaces:** Nothing. V1 remembers facts and playbooks; neither codebase tracks whether a learning worked.

**Why:** Muse's learning_adoption_events table (learning_id, outcome, detail) is the loop that makes it better at doing things, not just at knowing things. The extraction and adoption logic is not in any archive, so we design it, but it is a small loop on top of the memory flush already planned.

**Beats Muse:** Every learning carries its outcome record and can be revoked from the Memory page; Muse's are invisible to the user.

### 33. Connector read audit · phase 2 · small

**Do:** Every time Nano reads from your mail, bank or health data, one row records which connector, for what purpose, and how sensitive, and the Me tab shows it.

**Replaces:** Nothing.

**Why:** Muse's connector_read_audit table (connector, method, purpose, sensitivity, request origin). It is the receipt that answers 'what did it look at', it is cheap, and for a project whose whole point is not handing your life to someone else it is the right kind of paranoia.

**Beats Muse:** Ours is shown to you, not only kept for the system.

### 34. Relationship briefs · phase 3 · small

**Do:** For the people you deal with most, Nano keeps a short living brief (who they are to you, what is open between you) built from the people graph, and shows it as a card before you reply to them.

**Replaces:** Extends V1's people.py rather than replacing it.

**Why:** Muse's relationship_briefs table. V1 already has the people graph with an LLM merge and forward-only last-seen; this is a rendering and a card, not new memory.

**Beats Muse:** Built on records with provenance (mail history, sent replies) rather than on prose the model wrote about itself.

### 35. Proactive engine: goals, cards, follow-ups · phase 6 · large

**Do:** Nano pursues your goals in the background: each goal is an objective with its own state; scheduled runs produce cards (a spending calculation with its inputs and formula, a calibration of a prediction it made); and a selector decides whether a follow-up is worth surfacing to you at all.

**Replaces:** V2's Goals and Ideas JSON placeholders (dropped) and V1's morning brief as the only proactive surface.

**Why:** This is the real content of Muse's self_improvement schema: objectives, runs with leases and recovery, calculation and calibration cards, follow-up attempts with a selector, handoff dedupe. It is the proactive layer Meta advertises and the biggest thing Muse does that we do not. The tables give us the shape; the logic lives in Meta's binary, so we design it ourselves. It is a phase of its own and needs a proper design pass before a line is written.

**Beats Muse:** Every card shows the inputs and the formula it was computed from (Muse stores them in calculation_records; we would surface them), and every follow-up passes the same authorize() gate and daily cost cap as everything else, so proactivity cannot become spam.

### 36. Memory claims with a receipt · phase 3 · medium

**Do:** Behind the notes, Nano keeps structured claims: what was said, the exact quote, who said it, when it was first learned, when it was last confirmed, its current confidence, and what it replaced. When Nano writes a memory it tags it inline with its kind and importance ([preference|medium]); use adjusts that importance over time; each kind of claim decays at its own rate; and a memory.explain tool shows the whole receipt for any hit, including a superseded claim next to its replacement and the date it changed. Not every line becomes a claim; only what the memory flush extracts.

**Replaces:** V1's user_facts (confidence plus a supersession event, nothing else); V2's untagged Markdown lines.

**Why:** Muse's memory.claims table (kind, salience, quote, speaker, evidence, supersedes, confidence, first_seen, reinforced_at, valid_until) matches what Muse itself described: importance decided by the writer at write time, recency by last confirmation, and an explain view of the anatomy. Reinforcement is the piece we lacked: a fact you have confirmed twice should rank fresher than one you said once. The extraction lives in the memory flush we already planned.

**Beats Muse:** Muse's tag is set once and never learns; ours is corrected by whether the memory actually gets used. Muse's decay is one number; ours reads the kind and valid_until its own schema already carries. Muse hides what a claim replaced; ours tells you what changed and when. And the receipt is shown to you, with a correction archiving the old claim instead of overwriting it.

## Six build phases

### Phase 1: Spine: one agent you can talk to

Land the general loop, the tool registry with authorize() and persisted approvals, the home-directory memory, our own prompt manifest, the provider's streaming tool-use call with correct prices and a cost cap, and a Chat tab in the app, without touching any existing router, screen or test.

**Done when:** pytest passes (141 old plus the new files); a user can open the Chat tab, ask 'what is in my inbox and what did I eat today', watch the agent call inbox.context and nutrition.today, and get text plus a rendered block card; a gated tool produces an approval row and a card, and the decision appears in the ledger; telling Nano something about yourself changes USER.md with an archive event; the assembled system prompt is byte-identical across rounds within a turn and llm_call events show cache_read tokens on the second round when a key is present; no test subprocess sees ANTHROPIC_API_KEY or SUPERAPP_VAULT_KEY.

- **[M] [adapt from V1]** P1.1 Provider: add LLMProvider.stream_tools() (Messages streaming tool_use with delta accumulation lifted from V2 loop.py:196-232), per-role routing (model_chat=claude-opus-5 adaptive thinking, model_worker=claude-sonnet-5, model_routing=claude-haiku-4-5), family-based price lookup with claude-sonnet-5 corrected to $2/$10, server-side compaction opt-in (beta compact-2026-01-12) returning compaction blocks, server-side refusal fallbacks, llm_call events per round, a daily cost counter, and a scripted tool-call stub mode for tests; complete()/complete_batch() untouched
  - `apps/api/superapp/llm/provider.py`
  - `apps/api/superapp/config.py`
  - `V2/superapp/agent/loop.py`
- **[L] [port from V2]** P1.2 Agent loop: port V2's Agent class onto the provider (transcript persisted to agent_messages with ids, tool rounds, roles chat/subagent/scheduler_worker/memory_flush, depth, handoff inbox with a locked coalescing deliver(), silent turns); compaction blocks from the API are stored back into the transcript, client-side compaction kept only behind a flag; Room-per-user holding the root agent _(after P1.1, P1.4)_
  - `apps/api/superapp/agent/loop.py`
  - `apps/api/superapp/agent/handoffs.py`
  - `apps/api/superapp/agent/room.py`
  - `V2/superapp/agent/loop.py`
- **[M] [port from V2]** P1.3 Registry + authorize + provenance: port V2's registry with schemas generated from Python signatures, register-only-with-handler, uniform envelope, _ctx injection, visibility enforced at dispatch; authorize(agent, tool, args, turn) composing policy.assess (tier x provenance x suspicious), RISK_TIERS extended with action_key metadata (unknown = tier 2, tier 3 never auto), kernel.current_level, and the deterministic backstops, returning allow | card | deny and recording via kernel.record_decision; wrap_untrusted(text, source, ref) applying looks_like_injection and neutralize_placeholders and raising the turn's provenance to 'content'
  - `apps/api/superapp/tools/registry.py`
  - `apps/api/superapp/tools/authorize.py`
  - `apps/api/superapp/agent/provenance.py`
  - `apps/api/superapp/policy.py`
  - `apps/api/superapp/kernel.py`
  - `V2/superapp/tools/registry.py`
- **[M] [new]** P1.4 Alembic 0028 agent_runtime: agent_messages (thread with ids, role, provenance label, tool_call ids, compaction blocks), approvals (kind, action_key, args_fingerprint, status pending/claimed/allowed/denied/expired, deadline, default_on_expiry, decided_by, claimed_at) with atomic claim(), and push_tokens (moved out of user_facts and out of the orchestrator prompt); POST /v1/approvals/{id} resolves only with a phone session token from auth_sessions.py and delivers a handoff _(after P1.3)_
  - `apps/api/alembic/versions/0028_agent_runtime.py`
  - `apps/api/superapp/models.py`
  - `apps/api/superapp/approvals.py`
  - `apps/api/superapp/routers/approvals.py`
  - `apps/api/superapp/push.py`
  - `apps/api/superapp/auth_sessions.py`
- **[M] [port from V2]** P1.5 Home-directory memory: six standing files per user under data/homes/<user_id>/ (SOUL.md, IDENTITY.md, USER.md, MEMORY.md, memory/people/, memory/YYYY-MM-DD.md) with a token cap on injection; memory.write / memory.edit / memory.remember_fact / memory.facts / memory.search(FTS-only for now) tools wrapping write_fact's validator, the SECRET_HINT guard, the size cap and a memory_superseded archive event; a one-line computed state header appended after the files _(after P1.3)_
  - `apps/api/superapp/memory/home.py`
  - `apps/api/superapp/tools/memory_tools.py`
  - `apps/api/superapp/substrate/facts.py`
  - `V2/superapp/memory/files.py`
- **[M] [new]** P1.6 Prompts: port roles.yaml and assembler.py; build ~25 blocks for chat, subagent, scheduler_worker and memory_flush by adapting Muse's material (friend_replication_kit/agent_spec.md and soul.md as the behavioural source of truth; wording borrowed from the undamaged aria blocks in chat/, shared/, memory_flush/, scheduler_worker/, browser_task/; the 13 Muse/Meta mentions renamed; the 25 muse.* tool names mapped to ours or the block dropped; the 34 damaged files and the builder-role folders excluded); assemble once per turn under the provider's cache_control breakpoint; clock as a mid-conversation system message on Opus 5 (trailing block at hour granularity on Sonnet 5); prompt-honesty test that every tool, file and skill named exists; the chat role's block ORDER follows docs/muse-chat-assembly-order.md (Muse's own statement of it), not V2's reconstructed roles.yaml _(after P1.3, P1.5)_
  - `docs/muse-chat-assembly-order.md`
  - `apps/api/superapp/prompts/roles.yaml`
  - `apps/api/superapp/prompts/assembler.py`
  - `apps/api/superapp/prompts/blocks/`
  - `apps/api/tests/test_prompts.py`
  - `musearch/friend_replication_kit/agent_spec.md`
  - `musearch/friend_replication_kit/soul.md`
- **[M] [port from V2]** P1.7 Chat transport: WS /v1/chat with V2's frame protocol (turn_start/text_delta/event/turn_end/approval/approval_resolved) plus message ids, paginated GET /v1/history and a 'screen' frame carrying a validated V1 Screen/Section JSON card; screen.emit tool; cost.summary tool over llm_call events _(after P1.2, P1.4)_
  - `apps/api/superapp/routers/chat.py`
  - `apps/api/superapp/tools/screen_tools.py`
  - `apps/api/superapp/tools/cost_tools.py`
  - `apps/api/superapp/sdui/blocks.py`
  - `apps/api/superapp/main.py`
  - `V2/superapp/server.py`
- **[S] [adapt from V1]** P1.8 First read tools wrapping the existing loaders with AGENT_SCOPES checks: inbox.context, inbox.search (live Gmail via gmail_client, no indexing), nutrition.today, finance.summary, wardrobe.context, grocery.context, activity.context, autonomy.context, people.lookup, runtime.nothing_to_do _(after P1.3)_
  - `apps/api/superapp/tools/context_tools.py`
  - `apps/api/superapp/substrate/context.py`
  - `apps/api/superapp/inbox/gmail_client.py`
  - `apps/api/superapp/people.py`
- **[M] [port from V2]** P1.9 Mobile: ChatScreen with streaming, ws.ts client with reconnect and paged history, ScreenCard rendering blocks through the existing renderer.tsx, ApprovalCard as a list footer in V1's decision-card styling; added as a new 'chat' entry in App.tsx SCREENS while every existing screen stays untouched _(after P1.7)_
  - `apps/mobile/src/ChatScreen.tsx`
  - `apps/mobile/src/ws.ts`
  - `apps/mobile/src/cards/ScreenCard.tsx`
  - `apps/mobile/src/cards/ApprovalCard.tsx`
  - `apps/mobile/App.tsx`
  - `apps/mobile/src/sdui/renderer.tsx`
  - `V2/apps/mobile/src/screens/ChatScreen.tsx`
- **[M] [new]** P1.10 Tests: test_agent_loop.py (scripted stub tool calls, handoff coalescing, compaction blocks round-trip), test_authorize.py (tier x provenance x suspicious x level matrix; dispatch refuses invisible tools; untrusted wrapping taints the turn; injected email cannot reach a new recipient), test_approvals.py (claim, expiry defaults, phone-session-only resolve), test_memory_home.py (secrets refused, supersessions archived, cap honoured); all 141 existing tests untouched _(after P1.2, P1.3, P1.4, P1.5, P1.6, P1.7, P1.8)_
  - `apps/api/tests/test_agent_loop.py`
  - `apps/api/tests/test_authorize.py`
  - `apps/api/tests/test_approvals.py`
  - `apps/api/tests/test_memory_home.py`

### Phase 2: Inbox becomes a skill; consent and background work go durable

Port the scheduler, move the auto-send window onto persisted approvals with a deadline job, decompose the inbox pipeline into a code job plus loop tools, and route voice, Telegram and WhatsApp through the loop so the ungated executors disappear.

**Done when:** pytest green with the named test_spine rewrites; inbox-sync runs as a scheduled job and its summary appears as a handoff in the thread; 'reply to Sarah saying yes to Thursday' produces a draft card and a tap sends it; a matched auto-reply rule produces a countdown card that sends at the deadline only when every gate passes and a restart mid-window neither loses nor double-sends it; the voice orb cannot send to an address the policy would deny; grep finds no threading.Timer, rearm_all or _execute in the backend and the crontab section is gone from deploy/DEPLOY.md.

- **[L] [port from V2]** P2.1 Scheduler engine as Postgres rows only (no Markdown job mirror, no bash hooks): scheduler_jobs and scheduler_runs with UNIQUE(job_id, scheduled_for_utc) claim, two job kinds (agent prompt via scheduler_worker role, Python callable), separate pools with cooperative cancellation, results delivered as handoffs, nothing_to_do silent turns, restart-recovery note; cron.add/list/remove tools; a single background thread started in lifespan; Alembic 0029 _(after P1.2)_
  - `apps/api/superapp/scheduler/engine.py`
  - `apps/api/superapp/scheduler/jobs.py`
  - `apps/api/superapp/tools/cron_tools.py`
  - `apps/api/alembic/versions/0029_scheduler.py`
  - `apps/api/superapp/main.py`
  - `V2/superapp/scheduler/engine.py`
  - `V2/superapp/scheduler/tools.py`
- **[M] [adapt from V1]** P2.2 Auto-send as approval kind 'auto_reply' with a deadline job: schedule/announce/claim/re-gate/stale-claim-hold semantics preserved, default_on_expiry=allow only when a user-created standing rule (tier 2, user provenance) matched and every gate passes on the current body; threading.Timer and rearm_all removed; GET /inbox/state loses its send side effect; every other approval kind defaults to deny on expiry _(after P2.1, P1.4)_
  - `apps/api/superapp/autosend.py`
  - `apps/api/superapp/approvals.py`
  - `apps/api/superapp/routers/inbox.py`
  - `apps/api/superapp/main.py`
- **[L] [adapt from V1]** P2.3 Inbox split: inbox.sync scheduled code job (fetch via MailClient with checkpointed recovery, _signals and _evidence in code, triage on Haiku with TRIAGE_SCHEMA and verify with VERIFY_SCHEMA per message, store rows, summary handoff) plus loop tools inbox.list/read/search/draft/edit_draft/send/archive/set_rule/mute/priority; inbox.send accepts only a draft_id whose row is status=ready and re-runs every gate; refused/failed/needs_input rows unsendable at the DB level; tools declare returns_untrusted _(after P2.1, P1.3)_
  - `apps/api/superapp/agents/inbox.py`
  - `apps/api/superapp/tools/inbox_tools.py`
  - `apps/api/superapp/scheduler/jobs.py`
  - `apps/api/superapp/substrate/inbox.py`
  - `apps/api/superapp/inbox/factory.py`
  - `apps/api/superapp/inbox/recovery.py`
- **[S] [new]** P2.4 Skills catalog and the first skill: skills/inbox/SKILL.md and manifest.yaml (tools, action_keys, tiers raise-only over policy.py floors, provider=gmail); skills_catalog.py lists a skill only if every tool its manifest names has a handler and derives connected status from the vault and account rows; $skills computed section; test_skills_catalog.py _(after P2.3)_
  - `apps/api/skills/inbox/SKILL.md`
  - `apps/api/skills/inbox/manifest.yaml`
  - `apps/api/superapp/prompts/skills_catalog.py`
  - `apps/api/tests/test_skills_catalog.py`
  - `V2/superapp/prompts/skills_catalog.py`
- **[M] [adapt from V1]** P2.5 Voice and channels through the loop: routers/voice.py becomes a thin adapter that posts to the Room with channel=voice and returns the reply's 'say' field plus V1's cached TTS; the CONVERSE_SCHEMA executor, _execute and _stub_converse send branch are deleted (their actions become tools screen.open, inbox.sync, interview.start gated by authorize()); Telegram and WhatsApp become channel adapters posting to the Room with provenance=user only when the sender id matches the configured chat; routers/realtime.py removed from the app _(after P1.2, P1.7)_
  - `apps/api/superapp/routers/voice.py`
  - `apps/api/superapp/channels/telegram.py`
  - `apps/api/superapp/channels/whatsapp.py`
  - `apps/api/superapp/routers/telegram.py`
  - `apps/api/superapp/routers/whatsapp.py`
  - `apps/api/superapp/routers/realtime.py`
  - `apps/api/superapp/voice.py`
- **[M] [adapt from V1]** P2.6 Mobile: InboxScreen fed by GET /v1/inbox/state (pure) plus a WS inbox.changed invalidation instead of the 30s poll; the decision-card countdown reads the approval deadline and resolves through /v1/approvals; NanoOrb sends on-device STT transcripts over the socket and speaks turn_end text via /v1/voice/speak with seq gating (from V2 Orb.tsx) and BriefPlayer's audio-clock handoff _(after P2.2, P2.5)_
  - `apps/mobile/src/InboxScreen.tsx`
  - `apps/mobile/src/NanoOrb.tsx`
  - `apps/mobile/src/ws.ts`
  - `V2/apps/mobile/src/ui/Orb.tsx`
- **[M] [new]** P2.7 Tests: test_scheduler.py (claim never double-fires, timeout cancels, restart note), test_handoffs.py, inbox tool tests (refused/failed/needs_input drafts cannot be sent; a hijacked message never auto-sends; a scheduled turn with provenance=system cannot send to a new recipient). test_spine dispositions: the autosend cases around lines 1800-2132 re-pointed at the deadline job; test_voice_orb_hello_and_conversation, test_voice_send_refuses_an_unfinished_draft, test_voice_rewrite_makes_a_draft_ready and test_campaign_lifecycle_via_voice rewritten against the Room adapter with the _execute and converse imports removed; test_telegram_webhook_gateway and test_whatsapp_webhook_gateway rewritten against the channel adapters; test_sent_by_nano_is_visible_and_in_voice_context kept via inbox.context _(after P2.1, P2.2, P2.3, P2.5)_
  - `apps/api/tests/test_scheduler.py`
  - `apps/api/tests/test_handoffs.py`
  - `apps/api/tests/test_inbox_tools.py`
  - `apps/api/tests/test_spine.py`
  - `apps/api/tests/test_inbox_release.py`
- **[S] [new]** P2.8 Connector read audit: connector_reads table (connector, method, purpose, sensitivity, request_origin, run_id); written by every MailClient/StoreClient/Plaid/HealthKit read through the factory; surfaced on the Me tab and in the Activity sheet _(after P1.3)_
  - `apps/api/superapp/inbox/factory.py`
  - `apps/api/superapp/grocery/factory.py`
  - `apps/api/alembic/versions/0030_connector_reads.py`

### Phase 3: Everything is a skill; the app is thread-first

Turn every remaining vertical into tools plus a SKILL.md, dissolve the orchestrator into scheduler jobs, add subagents and onboarding, and make the app's home the thread with the Hub / Chat / Inbox / Today / Me tab map, retiring the think endpoints and their registries.

**Done when:** pytest green with the named test_spine rewrites; the app opens on the thread; every tab renders from REST without a model call and grep finds no setInterval network poll in App.tsx or the screens; 'what should I eat tonight given the fridge and my budget' composes nutrition, grocery and finance tools in one turn; a fresh install walks the three-step form and gets a greeting; nightly reflection, decay and the morning brief run from the scheduler and appear in the Activity sheet with cost; 'find me three quotes for X' spawns subagents whose reports arrive as list cards.

- **[L] [adapt from V1]** P3.1 Vertical tools wrapping existing think() steps and loaders with their schemas, routing and fallbacks: nutrition.log_meal/estimate(multimodal)/today/plan, grocery.forecast(pure)/read_receipt/build_basket(tier 0)/place_order(tier 3, fingerprint-bound confirm card), finance.summary/transactions/sync (move_money tier 3 never), wardrobe.context and stylist.suggest, people.lookup/upsert (LLM merge kept), flights.watch/tick; render() bodies become screen builders _(after P1.3, P2.4)_
  - `apps/api/superapp/tools/nutrition_tools.py`
  - `apps/api/superapp/tools/grocery_tools.py`
  - `apps/api/superapp/tools/finance_tools.py`
  - `apps/api/superapp/tools/stylist_tools.py`
  - `apps/api/superapp/tools/people_tools.py`
  - `apps/api/superapp/tools/flights_tools.py`
  - `apps/api/superapp/agents/nutrition.py`
- **[M] [new]** P3.2 SKILL.md and manifest.yaml for nutrition, grocery, finance, stylist, people, flights, morning-brief, memory-upkeep and identity-interview (interview.py SECTIONS become the playbook); test_skills_catalog extended to every skill _(after P3.1)_
  - `apps/api/skills/`
  - `apps/api/tests/test_skills_catalog.py`
  - `apps/api/superapp/interview.py`
- **[M] [adapt from V1]** P3.3 Orchestrator dissolved into jobs: memory-upkeep hourly agent job on Haiku seeded by _remember_day, nightly reflection, fact decay as a date-idempotent code job, heartbeat; dispatcher tick, retry_pending and flight-watch tick as code jobs; morning-brief as an agent job that emits a BriefPlayer payload card and a push; nightly events prune _(after P2.1, P1.5)_
  - `apps/api/superapp/scheduler/jobs.py`
  - `apps/api/superapp/agents/orchestrator.py`
  - `apps/api/superapp/dispatcher.py`
  - `apps/api/superapp/memory.py`
  - `apps/api/superapp/apns.py`
- **[S] [adapt from V1]** P3.4 Deterministic /v1/hub payload from substrate loaders, skills catalog status, pending approvals and the latest brief; hub block-plucking heuristics removed; GET /v1/screen/{name} stays a pure render; POST /screen/{name}/refresh retired in favour of an 'Update with Nano' action_row that posts a templated chat turn; WS invalidate events emitted after substrate writes _(after P3.1)_
  - `apps/api/superapp/hub.py`
  - `apps/api/superapp/agents/hub.py`
  - `apps/api/superapp/routers/screen.py`
  - `apps/api/superapp/routers/chat.py`
- **[M] [port from V2]** P3.5 Subagents: subagent.spawn/send/resume/close with depth cap 2, per-Room registries and pool of four with ownership checks, enforced timeout_s, tool set limited by AGENT_SCOPES-style exclusion enforced at dispatch (no send, spend, rule or memory-write tools), inherited provenance floor, no cards (needs_root_approval bubbles up as a handoff), [Subagent Report] handoffs labelled agent-generated; subagent role blocks; worker model claude-sonnet-5 at low effort _(after P1.2, P1.3)_
  - `apps/api/superapp/agent/subagents.py`
  - `apps/api/superapp/tools/subagent_tools.py`
  - `apps/api/superapp/prompts/blocks/subagent/`
  - `V2/superapp/agent/subagents.py`
- **[M] [port from V2]** P3.6 Onboarding: three-step form and POST /v1/onboarding seeding USER.md, IDENTITY.md and SOUL.md through memory.write plus a first-turn greeting handoff; Gmail connect offered as a card; interview as tools (interview.start/answer/distill) writing to USER.md and identity facts with the refusal branch fixed so '(stub distillation)' never persists; Google sign-in allowlist from settings.user_email_links; onboarded() checks the standing files _(after P1.5)_
  - `apps/api/superapp/routers/onboarding.py`
  - `apps/api/superapp/interview.py`
  - `apps/api/superapp/tools/interview_tools.py`
  - `apps/api/superapp/routers/auth.py`
  - `apps/api/superapp/auth.py`
  - `apps/mobile/src/OnboardingScreen.tsx`
  - `V2/apps/mobile/src/screens/OnboardingScreen.tsx`
- **[L] [adapt from V1]** P3.7 Mobile thread-first: App.tsx becomes tabs Hub / Chat / Inbox / Today / Me with NanoOrb docked; HubScreen over /v1/hub; CalScreen over /v1/nutrition/state; ProfileScreen merged with a Connectors panel (status from manifests + vault) and a Memory page (GET/PUT /v1/memory/files through the guarded write path); BriefPlayer fed by the morning-brief card; Finance/Stylist/Grocery as SduiScreen pages from the Hub grid; Flights folded into the thread (cards) and a Hub timeline row; every setInterval poll replaced by WS invalidations; ActivitySheet vocabulary covers tool_call, tool_result, approval, handoff, compaction, job_run, subagent _(after P3.4, P3.3, P1.9, P2.6)_
  - `apps/mobile/App.tsx`
  - `apps/mobile/src/HubScreen.tsx`
  - `apps/mobile/src/CalScreen.tsx`
  - `apps/mobile/src/ProfileScreen.tsx`
  - `apps/mobile/src/BriefPlayer.tsx`
  - `apps/mobile/src/ActivitySheet.tsx`
  - `apps/api/superapp/routers/memory.py`
- **[M] [adapt from V1]** P3.8 Retire POST /v1/agents/{name}/think, the AgentSpec think registry and SCREEN_AGENTS; keep render builders; routers/screen.py serves pure GETs only _(after P3.1, P3.3, P3.4)_
  - `apps/api/superapp/agents/base.py`
  - `apps/api/superapp/routers/screen.py`
  - `apps/api/superapp/main.py`
- **[M] [new]** P3.9 Tests: test_onboarding.py (seeds files, never writes placeholders on refusal, allowlist), test_subagents.py (ownership, timeout, cannot obtain an approval, cannot call send), test_hub_payload.py (deterministic, no model call). test_spine dispositions: test_identity_interview_flow moved to the interview tools; the two /v1/agents/orchestrator/think cases moved to the job runner; the /v1/screen/{home,hub,inbox} refresh cases become pure-GET assertions; test_scout_task_queue_roundtrip, test_flight_watch_lifecycle and test_liveactivity_token_registration_and_task_hooks re-pointed at flights jobs and push_tokens (routers/tasks.py stays until phase 5); test_routing_tasks_use_small_model_low_effort updated for per-role routing _(after P3.5, P3.6, P3.8)_
  - `apps/api/tests/test_onboarding.py`
  - `apps/api/tests/test_subagents.py`
  - `apps/api/tests/test_hub_payload.py`
  - `apps/api/tests/test_spine.py`
- **[S] [port from V2]** P3.10 Skill creation: port skills/skill-creator/SKILL.md (Muse's 53-line playbook) as our first skill-that-writes-skills; the catalog scans data/homes/<user_id>/workspace/skills/ as well as apps/api/skills/, applies the same honesty test and manifest rules to user-authored skills, and a self-written skill that names a missing tool is rejected with the reason _(after P2.4)_
  - `apps/api/skills/skill-creator/SKILL.md`
  - `apps/api/superapp/prompts/skills_catalog.py`
  - `apps/api/tests/test_skills_catalog.py`
- **[M] [new]** P3.11 Learnings loop: learnings table (learning_id, text, source run, status proposed/adopted/revoked) and learning_outcomes (learning_id, run_id, outcome, detail); the hourly memory-flush job proposes learnings from the last N turns with a schema-constrained call; adopted learnings are a computed prompt section; a learnings.revoke tool and a Memory-page list; outcome recorded when a later turn used one _(after P3.3, P1.6)_
  - `apps/api/superapp/scheduler/jobs.py`
  - `apps/api/superapp/tools/memory_tools.py`
  - `apps/api/superapp/prompts/assembler.py`
  - `apps/api/alembic/versions/0031_learnings.py`
- **[S] [adapt from V1]** P3.12 Relationship briefs: people.brief(email) builds a short brief from the Person row, mail_history sender/thread history and open drafts; rendered as a card before a reply and on the person's row in the Me tab _(after P3.1)_
  - `apps/api/superapp/people.py`
  - `apps/api/superapp/tools/people_tools.py`
- **[M] [new]** P3.13 Claims layer: memory_claims table (claim_id, kind, salience low/medium/high, claim_text, quote, speaker, evidence_handles, supersedes_claim_id, status, confidence, first_seen, reinforced_at, valid_until); the memory flush extracts claims from recent turns with a schema-constrained call and reinforces an existing claim instead of duplicating it; memory.write stamps [kind|salience] inline on the line it writes; memory.explain(hit) returns the claim anatomy; supersession archives the old claim; salience adjusts from use (a hit cited in a reply raises it, one surfaced and unused does not, capped), recorded as salience_adjustments rows so the tag stays the declared baseline; per-kind half-life table in config (state 7d, fact 365d, preference 730d, commitment decays to valid_until, default 90d); memory.search returns a superseded hit together with its replacement and the supersession date _(after P3.3, P1.5)_
  - `apps/api/superapp/memory/claims.py`
  - `apps/api/superapp/tools/memory_tools.py`
  - `apps/api/superapp/scheduler/jobs.py`
  - `apps/api/alembic/versions/0032_memory_claims.py`

### Phase 4: Depth: retrieval, hands, deploy

Bring retrieval up to the merged spec on the embedding model you chose, add the jailed workspace and helper-only exec, port the browser worker with deterministic gates, and make the container boot correctly on its own.

**Done when:** pytest green plus scripts/check_release_postgres.py; memory.search returns citations from notes, curated files and selected mail with provenance, and passes with no embedding key set; a subagent can run a script in the workspace with no secret in its environment; a browser errand pauses on a payment field for a tier-3 card and a site login shows a credential card; the container boots with migrations applied, one worker and no crontab.

- **[M] [adapt from V1]** P4.1 Retrieval: index the home-directory Markdown into memory_chunks (kind=home, ref=path, line span) so memory.search returns path#Lnn citations; selective mail indexing (needs_reply/worth_knowing, sent replies with author and source_ref, drafted threads, imported knowledge) and no bulk import of raw bodies; fix thread-id keying; per-source degraded flag; optional cross-encoder rerank stage behind a flag; embedder per the user's decision (Alembic 0031 changes the vector width and re-embeds if local); check_release_postgres.py extended; ranking = fused match score + salience prior (0.15, from the inline [kind|salience] tag) + recency prior (0.1, 90-day half-life over reinforced_at, not created_at) + cross-encoder rerank of the top 20; a min_score floor; the search tool accepts one to three phrasings and unions them; all weights in config, defaults from Muse's home.yaml _(after P1.5, P2.3)_
  - `apps/api/superapp/memory.py`
  - `apps/api/superapp/memory/embed.py`
  - `apps/api/superapp/memory/rerank.py`
  - `apps/api/superapp/tools/memory_tools.py`
  - `apps/api/superapp/routers/inbox.py`
  - `apps/api/alembic/versions/0031_home_chunks.py`
  - `apps/api/scripts/check_release_postgres.py`
- **[M] [port from V2]** P4.2 files.* namespace jailed to data/homes/<user_id>/workspace; exec tool registered only for the subagent role with a minimal env allowlist (PATH, HOME=workspace, LANG, TZ), jailed workdir, tier 1 with user provenance; test asserts no secret in the subprocess environment _(after P3.5, P1.3)_
  - `apps/api/superapp/tools/files_tools.py`
  - `apps/api/superapp/tools/exec_tools.py`
  - `apps/api/superapp/tools/authorize.py`
  - `V2/superapp/tools/local.py`
- **[L] [port from V2]** P4.3 Browser worker: per-user Chromium profile, referenced-element snapshots, receipts, takeover/handback frames and BrowserCard; sensitivity classified by URL, form-field type and price detection with payment fields at tier 3 and default-gated on error, replacing the button-text regex; Secure Store credential entry on a page signed with a stable per-deployment key, stored in V1's Fernet vault, filled by element ref; scout worker, ScoutCard and shared profile removed; flight watches drive the browser worker as scheduler jobs _(after P4.2, P1.4, P2.1)_
  - `apps/api/superapp/browser/worker.py`
  - `apps/api/superapp/browser/driver.py`
  - `apps/api/superapp/tools/browser_tools.py`
  - `apps/api/superapp/tools/credential_tools.py`
  - `apps/api/superapp/routers/credentials.py`
  - `apps/api/superapp/vault.py`
  - `apps/mobile/src/cards/BrowserCard.tsx`
- **[S] [adapt from V1]** P4.4 Deploy hygiene: Dockerfile entrypoint runs alembic upgrade head then uvicorn with one worker; create_all only under tests; DEPLOY.md crontab section replaced by the scheduler; compose stack describes one process plus Postgres behind Caddy; per-turn cost summary Activity event _(after P2.1)_
  - `apps/api/Dockerfile`
  - `apps/api/superapp/main.py`
  - `deploy/DEPLOY.md`
  - `deploy/docker-compose.prod.yml`
  - `docker-compose.yml`
- **[M] [new]** P4.5 Tests: test_retrieval.py (citations from notes, home files and selected mail carry provenance; degraded per source), test_exec_env.py, test_browser_gate.py (payment field, checkout URL, error default, credential token never appears in transcript text); test_migrations chain still linear _(after P4.1, P4.2, P4.3)_
  - `apps/api/tests/test_retrieval.py`
  - `apps/api/tests/test_exec_env.py`
  - `apps/api/tests/test_browser_gate.py`
  - `apps/api/tests/test_migrations.py`

### Phase 5: Delete the dead weight (runs last, after phase 6)

Remove every module the new spine made redundant, drop the tables nothing reads, fix the SDUI toolchain, and rewrite the architecture doc, so the backend is smaller than the 13.5k lines it is today and boots correctly on its own.

**Done when:** pytest green; a fresh container boots with migrations applied and no create_all; grep finds no reference to crontab, scout, Outlook, ElevenLabs, LiveKit, threading.Timer or SCREEN_AGENTS; export_sdui_schema.py --check passes in CI; the backend package is materially smaller than 13.5k lines.

- **[M] [adapt from V1]** P5.1 Delete dead code: agents/orchestrator.py, agents/hub.py, agents/base.py registry, dispatcher.py, routers/tasks.py, routers/kernel.py (record_decision, evidence and current_level move to autonomy.py), routers/interview.py, routers/realtime.py, routers/telegram.py and whatsapp.py (replaced by channels/), the old voice brain in routers/voice.py, scout/, scripts/create_realtime_agent.py, GroceryLink preference, InterviewScreen.tsx, ScoutCard.tsx, FlightsScreen.tsx and the widget bridge; ElevenLabs/LiveKit deps nothing imports removed from package.json _(after P4.3, P3.8)_
  - `apps/api/superapp/agents/orchestrator.py`
  - `apps/api/superapp/agents/hub.py`
  - `apps/api/superapp/agents/base.py`
  - `apps/api/superapp/dispatcher.py`
  - `apps/api/superapp/routers/tasks.py`
  - `apps/api/superapp/routers/kernel.py`
  - `apps/api/superapp/kernel.py`
- **[S] [new]** P5.2 Alembic 0032 drops flight_watches, campaigns, agent_tasks, interview_sessions, interview_turns, grocery_links (and autonomy_grants only if the user chose always-ask); models.py trimmed to match; docstrings promising gates that no longer exist removed _(after P5.1)_
  - `apps/api/alembic/versions/0032_drop_unused.py`
  - `apps/api/superapp/models.py`
- **[S] [adapt from V1]** P5.3 Fix export_sdui_schema.py MODELS (ShelfItem/Shelf/ShelfBlock) and wire --check into CI; regenerate types.ts; replace docs/ARCHITECTURE.md with a one-page description of the merged system and the plain-language decision table
  - `apps/api/scripts/export_sdui_schema.py`
  - `apps/mobile/src/sdui/types.ts`
  - `docs/ARCHITECTURE.md`
- **[S] [adapt from V1]** P5.4 Tests: delete the test_spine cases for removed features (tasks/dispatch, campaign, kernel promote, interview router, telegram/whatsapp webhooks if the channel adapters replaced their tests in phase 2); test_migrations still upgrades from empty; grep-based checks added to CI _(after P5.1, P5.2)_
  - `apps/api/tests/test_spine.py`
  - `apps/api/tests/test_migrations.py`

### Phase 6: Proactive: goals, cards, follow-ups (design pass first)

Give Nano the layer Muse markets and we lack: it pursues your goals in the background, computes cards you can check, and decides for itself whether a follow-up is worth your attention. The logic is not in any archive, so this phase opens with a design pass (competing proposals, judged) before any code.

**Done when:** A goal captured in chat becomes an objective with state; a scheduled run produces a card whose inputs and formula are visible on tap; a follow-up reaches the thread only when the selector says so and the cost cap allows; the same follow-up is never surfaced twice (dedupe); a run that dies mid-way is recovered by lease expiry; every proactive action appears in the ledger with its cost.

- **[M] [new]** P6.0 Design pass: four proposals (goal-first, card-first, follow-up-first, simplest) judged and synthesised into the concrete objective/card/selector model, before build _(after P3.11)_
  - `docs/CONSOLIDATION.md`
- **[M] [new]** P6.1 Objectives: table (objective_id, title, state_json, status, markers) and goals.capture / goals.list / goals.update tools; goal capture from chat writes an objective, not a Markdown line _(after P6.0)_
  - `apps/api/superapp/tools/goals_tools.py`
  - `apps/api/alembic/versions/0033_objectives.py`
- **[M] [port from V2]** P6.2 Objective runs on the scheduler with leases (lease_key, owner, expires_at, heartbeat) so a dead run is reclaimed, and handoff dedupe by content hash so the same result is never surfaced twice _(after P6.1, P2.1)_
  - `apps/api/superapp/scheduler/engine.py`
  - `apps/api/superapp/scheduler/jobs.py`
- **[L] [new]** P6.3 Cards with receipts: calculation_records (inputs, formula, outputs, code version) and calibration_records (a prediction, its window, how it landed); rendered as SDUI cards whose detail shows the inputs and formula _(after P6.2)_
  - `apps/api/superapp/proactive/cards.py`
  - `apps/api/superapp/sdui/blocks.py`
- **[M] [new]** P6.4 Follow-up selector: a scheduled job that scores candidate follow-ups (priority, staleness, last surfaced) and emits at most N per day through authorize() and the cost cap; every decision recorded _(after P6.2, P1.3)_
  - `apps/api/superapp/proactive/selector.py`
  - `apps/api/superapp/tools/authorize.py`
- **[M] [new]** P6.5 Goals tab in the app over /v1/goals, and proactive cards in the thread and on the Hub; tests: test_objectives.py, test_selector.py (never twice, never over cap, never ungated) _(after P6.3, P6.4)_
  - `apps/mobile/src/GoalsScreen.tsx`
  - `apps/api/tests/test_objectives.py`
  - `apps/api/tests/test_selector.py`

## What we deliberately leave behind

- **[V1] AgentSpec.think()/render() registry, POST /v1/agents/{name}/think, SCREEN_AGENTS and _REGISTRY as entrypoints** — Three hand-synced registries and a 17-touch-point checklist per vertical; the think bodies survive as tool handlers and the render bodies as screen builders.
- **[V1] Orchestrator agent as a nightly think run and the hub agent's block-plucking heuristics** — Its pieces (reflection, dream, decay, heartbeat) become scheduler jobs; as an agent it never ran in the documented deploy; the hub becomes a deterministic payload.
- **[V1] External crontab, threading.Timer autosend, rearm_all on boot, Starlette BackgroundTasks refresh, POST /screen/{name}/refresh** — Per-process and undocumented, and a hidden model call on a gesture; replaced by the durable scheduler with claim rows and a visible 'Update with Nano' chat turn.
- **[V1] routers/voice.py CONVERSE_SCHEMA executor (_execute, _stub_converse), routers/realtime.py ElevenLabs realtime SSE path, scripts/create_realtime_agent.py** — Bypasses the provider and calls no policy (can send new mail to any model-supplied address); voice now enters the one gated loop through on-device speech-to-text. Realtime dropped rather than flagged: it needs a key you do not have and a phase of re-plumbing.
- **[V1] Telegram and WhatsApp routers as separate brains with in-memory history** — They survive only as channel adapters into the same thread with provenance=user when the sender matches the configured chat.
- **[V1] Push tokens stored as confidence-1.0 user_facts and included in the orchestrator prompt** — A secret in the model's context; moved to a push_tokens table.
- **[V1] Display-only autonomy ladder UI paths (kernel promote/demote as endpoints), unless the user chooses always-ask, in which case the whole ladder and autonomy_grants** — current_level was consulted by nothing outside kernel.py; the ledger is kept and consulted by authorize(); promotion becomes a manual tap.
- **[V1] GET /inbox/state send side effect, InterviewScreen full-screen route, ScoutCard, FlightsScreen, scout Playwright worker with shared profile and server-wide login link, GroceryLink preference, widget bridge, Outlook stub, six mobile polling loops** — Dead, unsafe or replaced: WS invalidations replace polling, the interview runs as a skill in the thread, the per-user browser worker replaces scout, and flight research becomes cards in the main thread plus a Hub timeline row (the one screen fold, argued in row 19).
- **[V1] Bulk embedding of every synced Gmail body (import_source of whole mailboxes)** — Cost without a reader and the source of the migration-0027 degraded-recall reset; mail is searched live through inbox.search and only memorable items are indexed.
- **[V2] 55 Muse skill directories, config/skills.yaml, /opt/hatch connector CLIs (hatch_gws_cli, health-cli)** — Two real CLIs; the rest reference absent binaries; connectors run in-process against V1's vault so no subprocess ever holds a key.
- **[V2] Captured tool schemas (captured_68.json, core_reconstructed.json), the 46 handler-less functions, deferred namespaces, artifact/feed/wallet/channel/chat/todo/process namespaces** — Never pretend: schemas are generated from registered handlers only, and about 40 real tools need no deferral.
- **[V2] db/schema.sql 194-table Muse schema, per-user Postgres, migrate_cell.py** — 14 tables used; V1's alembic chain plus five new tables covers the runtime.
- **[V2] Fly cells, gateway, APNs wake-ahead, idle-exit, fake_fly.py, fly.*.toml** — Multi-tenant isolation a one-user host does not need, with unfixed signing-key, state-routing and provision-on-any-sign-in bugs; dropped, not deferred (all three judges agreed against the synthesis).
- **[V2] llm.py OpenAI-compatible client (unless the user picks the Meta endpoint), embedded Qdrant retriever singleton, file-mtime recency, constant salience** — No metering or caching; cross-user singleton; replaced by V1's provider and memory_chunks with V2's rerank and line-citation ideas lifted on top.
- **[V2] In-memory ApprovalStore with 600s blocking wait, muse.exec with inherited daemon env, /internal/approvals token callback** — Loses cards on restart, times out the CLI, leaks the vault key; replaced by persisted approvals answerable only from the phone and in-process tools.
- **[V2] Client-side compaction, the 500-entry in-memory event ring, process-global SPAWNS/POOL/SESSIONS** — Server-side compaction with persisted compaction blocks, persisted agent_messages, and per-Room registries with ownership replace them.
- **[V2] AGENTS.md, TOOLS.md, groups index and bank files; Markdown job files and bash hooks** — No V2 role ever wrote them; six standing files and rows-only jobs carry what Muse actually uses for one person.
- **[V2] The 308 ported blocks as-is, scripts/port_blocks.py, the 34 source blocks damaged in extraction, and the ~20 builder-role folders** — The archive confirms the damage is at the source and no assembly recipe was ever captured. The undamaged blocks survive as wording we borrow; the behaviour comes from the replication kit's clean 102-line spec.
- **[V2] Ideas, Goals, Library JSON-file tabs as placeholders; feed.json; side chats; attachments; event_hook role; button-text sensitivity regex** — Placeholders and unwired code. Goals return in phase 6 as real objectives with runs and cards; ideas as scheduler-delivered cards; the browser gate classifies by field type and URL instead.
