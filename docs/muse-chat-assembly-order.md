# Muse's chat-role assembly order

The one thing the extracted archive never contained: which blocks build the
chat prompt, in what order. Muse stated it directly on 2026-09-09 when asked
about its system prompt. This is the recipe Phase 1 item P1.6 adapts from.

V2's `roles.yaml` was a reconstruction made without this; it has most of the
same blocks in a materially different order (tools, payments and security
before date/time and writing style, where Muse puts them after; discretion
and alignment 29th, where Muse puts it 5th).

| # | Section, as Muse named it | Archive block(s) (`aria/prompt-blocks/blocks/`) | Note |
|---|---|---|---|
| 1 | who_you_are | `chat/who_you_are.md` | |
| 2 | values (truth, beauty, respect, fun, connection, curiosity) | inside `chat/who_you_are.md` | not a separate file |
| 3 | who_built_you | `shared/who_built_you.md` | rename Muse/Meta to Nano |
| 4 | who_you_work_for | `chat/who_you_work_for.md` | |
| 5 | discretion and alignment | `shared/discretion.md`, `chat/discretion_alignment.md` | early, not in the security cluster |
| 6 | how_you_work | `chat/how_you_work.md` | mentions muse.ai and the Muse app; rename |
| 7 | initiative | `chat/initiative.md` | |
| 8 | how_you_evolve | recovered by V2 from a glued file | verify the V2 copy |
| 9 | runtime files | `$standing_files` computed section | our six files |
| 10 | personalization | recovered by V2 from a glued file | verify the V2 copy |
| 11 | memory | `shared/memory_recall_doctrine.md` (+ V2 `chat/memory_recall.md`) | map muse.memory_search/get to ours |
| 12 | relationships | recovered by V2 from a glued file | verify the V2 copy |
| 13 | date/time and location awareness | `chat/date_validation_opener.md`, `shared/temporal_guidance_*`, `chat/current_location_*`, `chat/timezones_save.md` | clock moves out of the cached prefix (row 5) |
| 14 | context management | `chat/managing_context_opener.md`, `chat/managing_context_retention.md` (+ V2 `shared/managing_context_body.md`) | server-side compaction changes what this needs to say (row 2) |
| 15 | writing style | `chat/writing_style.md`, `chat/response_formatting.md` | |
| 16 | task acknowledgment | `chat/cron_created_acknowledgement.md` | V2 omitted it |
| 17 | tool routing | `shared/tools_intro.md`, `shared/tools_runtime_pointer.md`, `chat/grounding.md`, `chat/identifier_validation.md` (+ V2 `chat/tool_rules.md`) | map the 25 muse.* names or drop |
| 18 | credentials | `chat/safety_credentials.md`, `shared/security_secrets.md` | |
| 19 | payments | `chat/purchasing_flow.md`, `chat/payments_wallet.md` | wallet does not exist for us; tier-3 confirm card instead |
| 20 | safety | `chat/safety_oversight.md`, `shared/safety_core_conversational.md`, `shared/safety_sensitive_attributes.md`, `shared/safety_self_modification.md` | |
| 21 | security policy | `chat/security_authority.md`, `chat/security_sensitive_actions.md`, `chat/security_social_engineering.md`, `shared/security_content_markers.md` | |
| 22 | environment | `chat/filesystem.md`, `chat/workspace_files.md`, `shared/environment/*` (+ V2 `chat/your_environment.md`) | |
| 23 | docs index | computed listing of `~/docs/*.md` | we have no ~/docs; drop |

Muse also confirmed the `_worker` / `_detached` / `_task` variants are the
trimmed versions for subagents and scheduled workers; the archive has them
(`safety_credentials_detached_worker`, `security_authority_detached_worker`,
`discretion_alignment_task`, ...). Those seed the subagent and
scheduler_worker roles.

Muse's own description of its subagents ("child versions of me with my full
context") contradicts the replication kit's spec ("they start with no
inherited transcript; brief them fully"). Our design (row 17) briefs them and
makes them strictly weaker than the parent; which context they inherit is
decided in P3.5, not here.
