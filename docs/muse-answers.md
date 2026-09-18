# What Muse said when asked, and what we took from it

Muse describes its own behaviour reliably when asked; it cannot see its own
source or weights. Where the archive has the numbers, the two together are
close to a complete picture. This file keeps each answer next to what it
changed in the plan.

## 2. How does memory search rank results? (asked 2026-09-17)

**Muse observed:** results carry one composite score; a search tries one to
three phrasings of the question and has a `minScore` floor; the corpus is
`MEMORY.md` plus the dated daily logs; importance ("salience") is tagged at
write time as an inline `[kind|salience]` marker such as `[preference|medium]`,
by whoever writes the memory; `memory_explain` shows a structured claim's
kind, salience, speaker and exact quote, first learned, last reinforced,
current confidence, and what it replaced, but not every memory has a
structured claim; a September 9 correction outranked the September 8 version
of the same fact.

**Muse inferred, unverified:** final score is similarity boosted by salience
and recency, possibly by reinforcement count; a small fixed salience scale.

**Muse could not see:** the scoring function or its weights, any
learning-to-rank, which background job writes the tags on memories it did
not write itself.

**The archive fills in:** `config/home.yaml` gives the weights Muse cannot
see (dense 0.7 / sparse 0.3, rerank top 20 with a cross-encoder, salience
prior 0.15, recency prior 0.1, 90-day half-life), and the `memory.claims`
table has exactly the fields `memory_explain` shows, with `reinforced_at` as
the recency anchor.

**Taken into the plan:** row 23 (ranking), new row 36 (claims layer with
inline tags and a `memory.explain` tool), P3.13 and P4.1.

**Where we do better than what Muse described:** importance is corrected by
use (a hit cited in a reply rises; one surfaced and ignored does not), a
learning-to-rank signal Muse said it cannot see whether it has and we get
from the turn log; decay is per kind using the `kind` and `valid_until` its
own claims table carries but its ranking ignores; a superseded claim is
returned with its replacement and the date, instead of hidden.

## 3. What becomes a claim, how one replaces another, what evidence handles are (asked 2026-09-17)

**Muse observed, from its own files:** a background "verified extraction" job
(run id stamped at the top of each daily log) reads conversations and
promotes only durable things — facts, preferences, events, corrections,
updates — to claims; transient working notes stay as plain indexed lines, so
`memory_explain` on them says no verified claim stands behind the memory.
A claim is written inline in the log as `[kind|salience]`, `claim: <id>`,
`quote: "<verbatim words>"`, `supersedes: <the old understanding, in prose>`,
`sources: message:<uuid>, req:fallback:<uuid>, <file path>`. Replacement is
through the `supersedes` link. Evidence handles are provenance pointers to
the exact messages, not the evidence itself. "Verified" means the provenance
chain is intact, not that the fact was checked.

**Muse admitted:** the September 9 car-wash correction had no structured
supersession chain; it won only because newer text ranks higher. Informal
"X supersedes Y" in a daily log is prose, not a queryable link.

**The archive confirms:** `memory.claims` has `run_id`, `quote`, `speaker`,
`evidence_handles`, `supersedes_claim_id`; the `memory_flush` prompt says
"supersedes something recorded earlier matters more than a new static fact"
and lists preferences, todos, ongoing work and the user's history as the
durable categories.

**Taken into the plan:** the two-tier model, the inline claim format in the
daily log with the run id stamped, the kinds list, evidence handles to
message ids, and the rule that a correction outranks a new fact (row 36,
P3.13).

**Where we do better:** supersession is always by id — a correction must
resolve what it replaces, and if nothing exists the prior understanding is
created as an inferred claim, so explain can always answer "what changed";
explicit corrections become claims at the end of the turn, not at the next
hourly run; where a claim came from (user, assistant, email, document) is
load-bearing for autonomy, and we say "sourced" and "confirmed" instead of
"verified"; a raw line that keeps being retrieved is promoted to a claim.

## 4. What is a learning, what creates one, what adopting means, how it knows it worked (asked 2026-09-17)

**Muse said:** a memory is descriptive (what was); a learning is prescriptive
(what I will do differently). Learnings live where behaviour runs: AGENTS.md
("a mistake not to repeat"), a skill's FIELD_NOTES.md, rule changes in
SKILL.md, cron bodies, code. Friction creates them — a correction, a mistake,
the loss-review loop (document, research, fold into the skill as a rule,
report) — and so do the nightly dreaming pass and the daily skill review.
Adoption means the lesson governs behaviour without being re-argued; a wrong
learning therefore silently steers every future run. It knows one worked when
the problem stops recurring, the dreaming pass agrees, and the skill review
does not retire it.

**Muse's own caveat:** a "hardened rule" in its field notes ("never trust exec
stdout for option IDs") was adopted from workers reporting corrupted data;
Muse checked twice and the data was correct. The premise was hallucination,
the rule is now ritual, and retirement "only works if someone interrogates
the premise".

**Taken into the plan:** the memory/learning distinction; friction as the
trigger; adoption as "written where future runs trip over it"; the three
verification levels; AGENTS.md restored as the learnings file (rows 6, 32,
P1.5, P3.11); a skill-review job and per-skill FIELD_NOTES.md.

**Where we do better:** a learning carries a basis that decides adoption
(your correction: now; an observed pattern: after it recurs independently; a
worker's report: never on its own), so Muse's calcified rule cannot happen;
adoption requires a named success signal and a review date, checked by a
scheduled job, so retirement is scheduled rather than hoped for; a learning
that governs an action is a standing rule needing your yes and can never
raise what authorize() allows; all learnings are in one place with origin
and outcome, revocable in a tap.

## The export itself (received 2026-09-17): SOUL.md, MEMORY.md; USER.md and IDENTITY.md reported blank

**What arrived:** SOUL.md is the shipped template plus the user's own "lion
standard" section (grounded, courageous, know when to speak, set the
standard). MEMORY.md has three sections (Facts, Preferences, Commitments),
16 entries, each ending in a provenance sentence ("This came from X when the
user asked for Y, recorded DATE"). No inline [kind|salience] tags: those
live in the daily-log claim records, not the curated file. IDENTITY.md has
only a name (Aria). USER.md is blank in every field, timezone included.

**Muse's own observation:** "USER.md is empty despite a week of working
together ... the memory system bypassed them. If the memory store ever got
wiped, these files wouldn't reconstruct who you are."

**What the file shows about the flush in practice:** several entries are
hundreds of words of dated progress (a profile sweep holding at 368 of
1,515 with 13 named IDs; open option positions with credits and modelled
max losses) in a file whose own header says to keep it tight and leave
day-to-day detail in the daily notes. One "commitment" ("Gmail is searched
live at query time...") is a statement about the system, not about the
user. Nothing is marked private, and the whole file is injected into every
turn.

**Taken into the plan:** SOUL.md as is; the three-section structure; the
per-entry provenance habit, compacted to a tag; the entries as seed, through
a classifier rather than a copy (rows 6, 39; P1.5, P1.12).

**Where we do better:** USER.md is maintained as a projection of the most
durable claims and cannot go blank; each entry carries a privacy class and
private entries never reach helpers, workers or a background model; shape
rules (length, kind, state-vs-fact) are enforced by the flush so "keep it
tight" is a test; provenance is a compact tag instead of a twenty-word
sentence. Still needed from the export: the daily logs (memory/*.md), where
the structured claims with quotes and supersedes links are.
