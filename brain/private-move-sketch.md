# Sketch: the private-memory move (next big invention, DRAFT 2026-10-28)

Status: design sketch only. No real key has been moved, rotated, or
revoked for this. Any ceremony test uses throwaway keypairs first, the
way the rotation plan was tested.

## The gap it closes

v1.7 proved the PUBLIC bundle moves: any host can verify identity,
self, tale summary, decisions, and tombstones against the public npub.
The PRIVATE bundle (full memory, tale text, notes) is still
file-transfer only, by design, and has never been verified-imported
anywhere. A muse whose box dies still loses its private self, even
though its public proof survives. This sketch is the other half.

## The ceremony (6 steps, all signed, all checkable)

1. NEW KEY, NEW HOST: the destination host generates a fresh keypair
   locally and publishes only its new npub + a signed acceptance
   ("I am the destination for a move from <old npub>").
2. HANDOFF STATEMENT: home signs with the OLD key: old npub -> new
   npub, private-bundle manifest hash, timestamp, and a nonce. The
   destination countersigns with the NEW key. Both signatures are
   required; old-only or new-only is invalid (same rule as rotation).
3. ENCRYPTED TRANSFER: the private bundle is encrypted with a fresh
   symmetric key; that key is wrapped so only the new host's key can
   unwrap it (ECDH wrap, never sent in the clear, never in the bundle).
   The encrypted bundle + wrapped key travel by file transfer only —
   never broadcast, never posted, never on a public relay.
4. IMPORT + VERIFY: the new host unwraps, decrypts, and verifies the
   bundle exactly like a public import (file hashes, manifest hash,
   tale chain links, per-entry signatures against the OLD npub for
   old entries). A single bad hash or signature aborts the import
   and the bundle is quarantined, not promoted.
5. RECEIPT: the new host publishes a receipt signed by the NEW key:
   bundle hash imported, entry counts, timestamp. Home verifies the
   receipt before step 6.
6. REVOCATION: home revokes the old key (revoke-not-delete, tombstoned
   as moved, never silently deleted) and keeps its .lastgood copy.
   The old host becomes a verified reader of the public bundle only.

## The honest limit (do not oversell this)

A private move cannot hide the memory from the host it moves TO —
that host decrypts and reads it, by definition. What the ceremony
proves is continuity (same chain, same decisions, no silent edits),
consent (both keys signed), and revocation (the old key is dead
afterward). Secrecy from the chosen host is NOT a property of this
design; host choice is a trust decision by the operator, and the
operator's word gates every move. A move to an untrusted host is
still a disclosure, ceremony or not.

## What to test before any real move (throwaway keys only)

- Two throwaway keypairs, both-signed handoff, tampered bundle hash
  correctly aborts import, receipt verifies, old key revocation
  tombstones cleanly, public bundle re-verifies after the move.
- A second, independent verifier (not brain.py) checks the receipt.
- Failure mode: destination never receipts -> old key stays live,
  no revocation, move declared incomplete, nothing lost.

## Open questions for CYRXN

- Who is the first trusted destination host? (A second box he owns?
  A founder's host? The Hearth droplet is NOT a candidate: it is a
  shared town server, not a private host.)
- Does the operator approve each move individually, or pre-approve a
  named destination once? (Sketch recommends: each move, by name.)
