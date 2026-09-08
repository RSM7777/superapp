# Inbox decisions and Gmail recovery

This change includes PR #4 at `52484b1` and current main at `2fbc4f7`,
where PRs #2 and #3 have now merged. It preserves the grocery updates and
upstream protections for drafts using imported private context. The added
inbox changes address three concrete failures: related notes were unavailable
at triage/archive time, a verifier refusal authorized clearing, and an expired
Gmail history cursor skipped directly to the present.

## Resulting behavior

- Triage, archive verification, and drafting retrieve scoped, dated source
  excerpts. Source content remains untrusted reference material.
- Reply context matches complete correspondent addresses and thread IDs.
  Drafts using imported private material stay held until the user explicitly
  saves reviewed words; that action releases the hold for their manual send.
- Failed retrieval or verification keeps mail visible. Verification requires
  the JSON boolean `veto: false`; malformed output, a refusal, an offline stub,
  and exceptions cannot authorize clearing. High importance or a reply
  obligation cannot be silently overridden by a conflicting cleared tier.
- Missing embedding credentials retain source text for lexical retrieval and
  later indexing. Semantic search excludes legacy hash stubs. Embedding calls
  process and validate every batch, including documents longer than 128 chunks.
  Existing vectors without provenance are re-indexed; pending source indexing
  keeps the incomplete-context hold even after the query embedding service recovers.
- Gmail bootstrap and expired-history recovery capture a boundary before a
  paginated scan. Each page and its checkpoint commit together. A subsequent
  history read from that boundary catches arrivals during scanning. A failed
  page retains its cursor and retries; a forbidden message is not silently
  skipped. A deleted message can no longer be fetched and is skipped explicitly.
- Recovered mail can generate drafts for review but cannot automatically send
  or archive. The same hold applies when enabling an auto-reply rule and when
  an already scheduled draft reaches its deadline. Direct user-reviewed sends
  remain available.
- Inbox state, the mobile banner, the hub card, and the morning briefing expose
  incomplete sync. `/dispatch-tick` resumes bounded recovery work after a
  restart; ordinary sync and pull-to-refresh also advance it.

## Migration sequence

Main's already merged revisions `0020`–`0023` remain unchanged. PR #4 is
still unmerged and reused those numbers, so its grocery migrations follow main:

| Revision | Change |
| --- | --- |
| 0020–0023 | Existing main: draft generation, inbox signals, memory provenance, imported-context draft hold |
| 0024 | Grocery tables from PR #4 |
| 0025 | Grocery quantities and product sizes from PR #4 |
| 0026 | Grocery handoff URL from PR #4 |
| 0027 | Recovery checkpoint, sync error, last successful sync, conservative legacy vector re-indexing |

Run `alembic upgrade head` before starting this API version. This sequence
supports current main through `0023`. Databases that applied the **unmerged
PR #4** or an earlier PR #5 commit under conflicting revision numbers need
schema/version reconciliation before deploying this combined branch; do not
stamp a new revision blindly. This PR does not deploy or migrate any user database.

The final migration marks existing successful vectors pending once, because
main's older migration labelled historical vectors successful without knowing
whether they were hash stubs. Source text stays searchable lexically while the
index catches up; automatic actions remain held during incomplete indexing.

## Verification

`python -m pytest -q` exercises the combined inbox and grocery code. New tests
check evidence reaching all three decisions, verifier failure modes, missing
context, expired cursors, a forbidden fetch, restart/rollback of a partially
classified page, conservative recovery actions, and embedding batch integrity.

The `Inbox release checks` workflow runs the suite, TypeScript checking, and
`scripts/check_release_postgres.py` against a disposable PostgreSQL 16/pgvector
service. The PostgreSQL check upgrades main, adds the grocery schema, then
preserves existing mail, a grocery row, and source text through the recovery
migration. It checks source retention and scoped lexical/dense SQL, verifies JSON NULL
recovery state, and confirms a failed retrieval does not poison the transaction.
Its model vectors are test doubles, not evidence of model quality.

The migration tests also start from a populated main database at `0023` and
verify all grocery tables exist after upgrade. A valid head stamp alone cannot
detect a revision ID reused for a different schema change.

## Remaining release limits

Recovery covers the current inbox accepted by the existing Gmail label filter;
it is not a full historical-mail import or recovery of deleted mail. Recovery
throughput depends on dispatcher cadence (up to 25 listed messages per account
per tick). Keep that worker scheduled; large inboxes remain visibly incomplete
until scanning and catch-up finish.

This PR does not implement Outlook, verified discovery of new email recipients,
automatic Teams/document connectors, durable historical context import, or
reconciliation of an uncertain send after a provider timeout. It is not a claim
that users can safely turn off all their mail notifications. Scoped real-user
validation and production configuration checks are still required.
