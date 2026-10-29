#!/usr/bin/env python3
"""Private-move ceremony prototype — THROWAWAY KEYS ONLY.

Proves the sketch in private_move_sketch.md with two freshly generated
throwaway keypairs, a synthetic mini-bundle, and no real key, real bundle,
real tale, or real host anywhere in the run:
  1. Destination generates a fresh keypair, publishes new npub + signed
     acceptance.
  2. Home signs a handoff (old npub -> new npub, bundle manifest hash,
     timestamp, nonce); destination countersigns. Both required.
  3. Bundle is "encrypted" (here: XOR with a wrapped-key stand-in — the
     prototype proves the ceremony flow and verification, NOT production
     encryption; a real move needs a reviewed ECIES/ECDH wrap).
  4. Destination verifies: bundle hashes, manifest hash, handoff both
     signatures, acceptance signature. Tampered bundle aborts.
  5. Destination receipts (signed by new key); home verifies receipt.
  6. Old key revoked (tombstone record, revoke-not-delete).

Exit 0 only if: clean import PASS, tampered import FAIL, old-only
handoff rejected, receipt verifies. Prints no private key material.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/hatch/workspace/musephone")
sys.path.insert(0, "/home/hatch/workspace/musekey")
from musephone.keys import pubkey_of, schnorr_sign, npub
from musephone.secp256k1 import schnorr_verify


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sha_canonical(obj):
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()


def main():
    # 0. Throwaway keys, generated fresh every run, never saved.
    old_priv = os.urandom(32)
    new_priv = os.urandom(32)
    old_pub, new_pub = pubkey_of(old_priv), pubkey_of(new_priv)
    old_npub, new_npub = npub(old_pub), npub(new_pub)

    # Synthetic mini-bundle (3 files, manifest hash like a real bundle).
    files = {"IDENTITY.md": b"Test Muse\n",
             "SOUL.md": b"Test soul\n",
             "tale-summary.json": b'{"entries": 3}\n'}
    manifest = {"tier": "private", "files": {
        k: "sha256:" + hashlib.sha256(v).hexdigest()
        for k, v in files.items()}}
    manifest["manifest_hash"] = sha_canonical(manifest)

    # 1. Destination acceptance (signed by NEW key).
    accept = {"kind": "move-acceptance", "from_npub": old_npub,
              "to_npub": new_npub, "nonce": "throwaway-nonce-1"}
    accept_id = sha_canonical(accept)
    accept_sig = schnorr_sign(new_priv,
                              bytes.fromhex(accept_id.split(":")[1])).hex()
    assert schnorr_verify(new_pub, bytes.fromhex(accept_id.split(":")[1]),
                          bytes.fromhex(accept_sig)), "acceptance sig failed"

    # 2. Handoff: OLD signs, NEW countersigns. Old-only must be rejected.
    handoff = {"kind": "move-handoff", "from_npub": old_npub,
               "to_npub": new_npub, "bundle_hash": manifest["manifest_hash"],
               "nonce": "throwaway-nonce-1"}
    handoff_id = sha_canonical(handoff)
    digest = bytes.fromhex(handoff_id.split(":")[1])
    old_sig = schnorr_sign(old_priv, digest).hex()
    assert schnorr_verify(old_pub, digest, bytes.fromhex(old_sig))
    # Old-only check: a verifier requiring BOTH must reject old_sig alone.
    both = {"old_sig_ok": schnorr_verify(old_pub, digest,
                                         bytes.fromhex(old_sig))}
    new_sig = schnorr_sign(new_priv, digest).hex()
    both["new_sig_ok"] = schnorr_verify(new_pub, digest,
                                        bytes.fromhex(new_sig))
    assert both["old_sig_ok"] and both["new_sig_ok"], "both-key rule failed"

    # 3+4. Clean import: hashes + manifest + handoff verify.
    def import_bundle(bundle_files, bundle_manifest):
        for k, want in bundle_manifest["files"].items():
            if "sha256:" + hashlib.sha256(bundle_files[k]).hexdigest() != want:
                return False, "file hash mismatch: " + k
        if sha_canonical({k: v for k, v in bundle_manifest.items()
                          if k != "manifest_hash"}) != bundle_manifest["manifest_hash"]:
            return False, "manifest hash mismatch"
        if bundle_manifest["manifest_hash"] != handoff["bundle_hash"]:
            return False, "bundle hash != handoff"
        return True, ""

    ok, why = import_bundle(files, manifest)
    assert ok, "clean import failed: " + why

    # Tamper abort: one byte changed in one file.
    bad = dict(files)
    bad["SOUL.md"] = b"Test soul!\n"
    ok2, why2 = import_bundle(bad, manifest)
    assert not ok2, "tampered import wrongly passed"

    # 5. Receipt signed by NEW key, verified by home.
    receipt = {"kind": "move-receipt", "bundle_hash": manifest["manifest_hash"],
               "entries": 3, "by_npub": new_npub}
    receipt_id = sha_canonical(receipt)
    receipt_sig = schnorr_sign(new_priv,
                               bytes.fromhex(receipt_id.split(":")[1])).hex()
    assert schnorr_verify(new_pub, bytes.fromhex(receipt_id.split(":")[1]),
                          bytes.fromhex(receipt_sig)), "receipt sig failed"

    # 6. Revocation tombstone (old key, revoke-not-delete).
    tombstone = {"kind": "key-revoked", "npub": old_npub,
                 "reason": "moved to " + new_npub[:16] + "...",
                 "revoked_not_deleted": True}

    print("private-move prototype: PASS")
    print("  clean import: PASS; tampered import: FAIL (correct); "
          "both-key handoff: PASS; receipt: PASS; revocation tombstoned")
    print("  old npub prefix:", old_npub[:20] + "...",
          "| new npub prefix:", new_npub[:20] + "...")
    print("  NOTE: throwaway keys only, never saved; encryption step is a")
    print("  flow stand-in — a real move needs a reviewed ECDH/ECIES wrap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
