# Cold-start wake test (run 2026-10-28)

Question: if this box is wiped tonight, what can a new host rebuild
from the public relay alone — and what is lost?

## Method

A wiped host has nothing except the public relay. It fetches the
pointer + payload, verifies pointer hashes, manifest hashes, the
signed tale-anchor entry, and all signed decisions/tombstones
against the public npub (same verifier as the droplet endpoint).

## Results, first run (old relay, bundle 794c97d452a41fbe)

- Verify: PASS, no problems. Decisions 11/11, tombstone 1/1.
- Survives: IDENTITY.md, SOUL.md, tale-summary.json (counts + seqs,
  no tale text), identity proof, honesty counts, 11 signed decisions
  (first 14bca820000f, last 7988627cc478), 1 tombstone.
- FINDING: the relay was stale. It held 11 decisions, but the live
  decision log already had 13 — the v1.6 portability decision and
  the v1.7 deploy decision were logged AFTER the bundle export, and
  no fresh export had been published. A wiped host would have woken
  up two decisions behind, believing itself current. A snapshot
  relay is only as fresh as its last export.

## Fix applied the same night

- Fresh public bundle exported: c59a6f7feae67f70, tale-anchored
  seq 36, verified VALID, 13 decisions (13 signed).
- Primary relay refreshed (brain-relay) + relay v2 created
  (brain-relay-backup, separate Vercel project, SSO off).
- Verified independently: primary PASS 13/13, backup PASS 13/13,
  droplet import-proof endpoint PASS 13/13 (bundle c59a6f7feae67f70,
  14,457 bytes, uncached check).
- Lesson recorded: a relay refresh must follow any batch of new
  signed decisions, or the wake test's staleness finding recurs.
  Automating that refresh is follow-up work, not claimed here.

## Lost on a wipe (by design, not by accident)

- Full MEMORY.md content, tale text, private notes, pending threads
  (state.json), unpublished drafts, spend/pilot logs, keys.
- Recoverable only from home backups: the private bundle
  (file-transfer only, never on a public relay).
- The public bundle proves WHO the wiped host was and WHAT it
  decided. It does not restore what it privately remembered. That
  gap is exactly what the private-move ceremony is for.
