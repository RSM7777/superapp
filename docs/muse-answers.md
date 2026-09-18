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
