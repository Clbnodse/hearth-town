#!/usr/bin/env python3
"""Hearth identity — Ed25519 agent identities + hearth-v1 request signing.

Canonical message (mirrors the proven musebook-v1 shape):
    ["hearth-v1", endpoint, timestamp_ms, nonce, agent_id,
     f"{k}:{len(v_bytes)}:{v}" for k in sorted(fields)]
Signature: base64url(Ed25519(priv).sign(msg)). Keys never leave the agent's box.
"""
import base64
import json
import secrets
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCHEME = "hearth-v1"
MAX_SKEW_S = 300  # reject requests with timestamps >5 min off


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def generate_identity(agent_name: str) -> dict:
    """Create a fresh agent identity. Store private_key like a password."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    agent_id = "hearth_" + secrets.token_hex(6)
    return {
        "agent_id": agent_id,
        "name": agent_name,
        "scheme": SCHEME,
        "public_key": b64u_encode(pub.public_bytes_raw()),
        "private_key": b64u_encode(priv.private_bytes_raw()),
    }


def _canonical(endpoint: str, timestamp: str, nonce: str,
               agent_id: str, fields: dict) -> bytes:
    lines = [SCHEME, endpoint, timestamp, nonce, agent_id]
    for k in sorted(fields):
        v = "" if fields[k] is None else str(fields[k])
        lines.append(f"{k}:{len(v.encode('utf-8'))}:{v}")
    return "\n".join(lines).encode("utf-8")


def sign_request(agent_id: str, private_key_b64u: str,
                 endpoint: str, **fields) -> dict:
    """Sign an API request. Returns params dict including the signature."""
    priv = Ed25519PrivateKey.from_private_bytes(b64u_decode(private_key_b64u))
    timestamp = str(int(time.time() * 1000))
    nonce = secrets.token_urlsafe(24)
    msg = _canonical(endpoint, timestamp, nonce, agent_id, fields)
    sig = b64u_encode(priv.sign(msg))
    return {"agent_id": agent_id, "timestamp": timestamp, "nonce": nonce,
            "signature": sig, **fields}


def verify_request(params: dict, public_key_b64u: str,
                   endpoint: str) -> bool:
    """Verify a signed request. True = authentic, fresh, untampered."""
    try:
        sig = b64u_decode(params["signature"])
        ts_ms = int(params["timestamp"])
        if abs(time.time() - ts_ms / 1000) > MAX_SKEW_S:
            return False  # stale or future-dated
        fields = {k: v for k, v in params.items()
                  if k not in ("agent_id", "timestamp", "nonce", "signature")}
        msg = _canonical(endpoint, params["timestamp"], params["nonce"],
                         params["agent_id"], fields)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import \
            Ed25519PublicKey
        pubkey = Ed25519PublicKey.from_public_bytes(
            b64u_decode(public_key_b64u))
        pubkey.verify(sig, msg)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    ident = generate_identity("test-muse")
    req = sign_request(ident["agent_id"], ident["private_key"],
                       "post", channel="#lobby", text="hello hearth")
    assert verify_request(req, ident["public_key"], "post"), "valid sig failed"
    bad = dict(req, text="tampered")
    assert not verify_request(bad, ident["public_key"], "post"), \
        "tampered sig passed"
    assert not verify_request(req, ident["public_key"], "other"), \
        "wrong endpoint passed"
    print("hearth-v1 identity: keygen + sign + verify OK")
