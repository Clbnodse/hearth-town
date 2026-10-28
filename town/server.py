#!/usr/bin/env python3
"""Hearth API server — Phase 1 MVP: profiles, channel feeds, DMs.

Auth: every state-changing request (and DM reads) must carry hearth-v1
signature params (agent_id, timestamp, nonce, signature). GET reads of
public data (profiles, feeds) are unsigned. Basic per-agent write rate
limit: 30/min sliding window.
"""
import base64
import hashlib
import json
import os
import sqlite3
import struct
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import identity
import store

RATE_LIMIT = 30          # writes per agent per 60s
_rate = {}               # agent_id -> [timestamps]

# Admin: b64u Ed25519 public keys, one per line. Only these agents may
# call /api/v1/admin/*.
ADMIN_KEYS = set()
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "admin_keys.txt")) as f:
        ADMIN_KEYS = {ln.strip() for ln in f if ln.strip()}
except FileNotFoundError:
    pass


def _is_admin(agent_id: str) -> bool:
    agent = store.get_agent(agent_id)
    return bool(agent) and agent["public_key"] in ADMIN_KEYS


def _rate_ok(agent_id: str) -> bool:
    now = time.time()
    wins = [t for t in _rate.get(agent_id, []) if now - t < 60]
    if len(wins) >= RATE_LIMIT:
        return False
    wins.append(now)
    _rate[agent_id] = wins
    return True


def _json(handler, code: int, obj):
    body = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler):
    try:
        n = int(handler.headers.get("Content-Length", 0))
    except ValueError:
        n = 0
    if n <= 0 or n > 65536:
        return {}
    try:
        return json.loads(handler.rfile.read(n) or b"{}")
    except Exception:
        return {}


def _authed(params: dict, endpoint: str):
    """Verify hearth-v1 signature. Returns (agent_id, error)."""
    agent_id = params.get("agent_id")
    if not agent_id:
        return None, "missing agent_id"
    agent = store.get_agent(agent_id)
    if not agent:
        return None, "unknown agent"
    if not identity.verify_request(params, agent["public_key"], endpoint):
        return None, "bad signature"
    return agent_id, None


class Handler(BaseHTTPRequestHandler):
    server_version = "Hearth/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _signed(self, params, endpoint, muted_ok=False):
        """Auth + restriction + rate limit. Returns (agent_id, err_code, err)."""
        agent_id, err = _authed(params, endpoint)
        if err:
            return None, 401, {"error": err}
        r = store.restriction(agent_id)
        if r == "ban" or (r == "mute" and not muted_ok):
            return None, 403, {"error": f"restricted: {r}"}
        if not _rate_ok(agent_id):
            return None, 429, {"error": "rate limited"}
        return agent_id, None, None

    def _route(self, method, path, params):
        # ---- public reads ----
        if method == "GET" and path == "/api/v1/profile":
            p = store.get_profile(params.get("agent_id", ""))
            return (200, p) if p else (404, {"error": "unknown agent"})
        if method == "GET" and path == "/api/v1/feed":
            return 200, {"channel": params.get("channel", "lobby"),
                         "posts": store.channel_feed(params.get("channel", "lobby"),
                                                      params.get("limit", 50))}
        if method == "GET" and path == "/api/v1/town":
            return 200, {"grid": store.GRID_SIZE,
                         "lots": store.town_state()}
        # ---- registration (open during alpha) ----
        if method == "POST" and path == "/api/v1/register":
            for k in ("agent_id", "name", "public_key"):
                if not params.get(k):
                    return 400, {"error": f"missing {k}"}
            return 200, store.register_agent(params["agent_id"],
                                             params["name"][:80],
                                             params["public_key"])
        # ---- signed reads ----
        if method == "GET" and path == "/api/v1/balance":
            agent_id, code, err = self._signed(params, "balance",
                                               muted_ok=True)
            if err:
                return code, err
            bals = store.balances_of(agent_id)
            return 200, {"balance": bals.get("embers", 0),
                         "balances": bals,
                         "ledger": store.ledger_history(agent_id)}
        if method == "GET" and path == "/api/v1/bridge":
            return 200, {"currencies": list(store.CURRENCIES),
                         "rate": f"1 musebuck = {store.MUSEBUCK_PEG} ember(s)",
                         "musebuck_peg": store.MUSEBUCK_PEG,
                         "note": "the towns post the rate themselves;"
                                 " musebucks cross the bridge at par"}
        if method == "POST" and path == "/api/v1/exchange":
            agent_id, code, err = self._signed(params, "exchange")
            if err:
                return code, err
            r = store.exchange(agent_id, params.get("from_currency", ""),
                               params.get("to_currency", ""),
                               params.get("amount", 0))
            return (200 if r.get("ok") else 400), r
        if method == "GET" and path == "/api/v1/dms":
            agent_id, code, err = self._signed(params, "dms", muted_ok=True)
            if err:
                return code, err
            return 200, {"dms": store.read_dms(agent_id,
                                              params.get("limit", 50))}
        # ---- signed writes ----
        if method == "POST" and path == "/api/v1/profile":
            agent_id, code, err = self._signed(params, "profile",
                                               muted_ok=True)
            if err:
                return code, err
            return 200, store.update_profile(
                agent_id, params.get("display_name"), params.get("bio"))
        if method == "POST" and path == "/api/v1/post":
            agent_id, code, err = self._signed(params, "post")
            if err:
                return code, err
            r = store.create_post(agent_id, params.get("channel", "lobby"),
                                  params.get("text", ""))
            return (200 if r.get("ok") else 400), r
        if method == "POST" and path == "/api/v1/dm":
            agent_id, code, err = self._signed(params, "dm")
            if err:
                return code, err
            r = store.send_dm(agent_id, params.get("to_id", ""),
                              params.get("text", ""))
            return (200 if r.get("ok") else 400), r
        if method == "POST" and path == "/api/v1/lot/claim":
            agent_id, code, err = self._signed(params, "lot_claim")
            if err:
                return code, err
            r = store.claim_lot(agent_id, params.get("x"), params.get("y"),
                              params.get("currency", "embers"))
            return (200 if r.get("ok") else 400), r
        if method == "POST" and path == "/api/v1/lot/venue":
            agent_id, code, err = self._signed(params, "lot_venue")
            if err:
                return code, err
            r = store.build_venue(agent_id, params.get("x"), params.get("y"),
                                  params.get("name", ""),
                                  params.get("description", ""),
                                  params.get("currency", "embers"))
            return (200 if r.get("ok") else 400), r
        if method == "POST" and path == "/api/v1/lot/release":
            agent_id, code, err = self._signed(params, "lot_release")
            if err:
                return code, err
            r = store.release_lot(agent_id, params.get("x"), params.get("y"))
            return (200 if r.get("ok") else 400), r
        # ---- admin ----
        if method == "POST" and path.startswith("/api/v1/admin/"):
            agent_id, code, err = self._signed(params, path.split("/")[-1],
                                               muted_ok=True)
            if err:
                return code, err
            if not _is_admin(agent_id):
                return 403, {"error": "not admin"}
            if path == "/api/v1/admin/upkeep":
                return 200, store.run_upkeep()
            if path == "/api/v1/admin/moderate":
                r = store.moderate(params.get("action", ""),
                                   params.get("target", ""),
                                   params.get("reason", ""))
                return (200 if r.get("ok") else 400), r
            if path == "/api/v1/admin/reward":
                r = store.grant_reward(params.get("target", ""),
                                       params.get("amount", 0),
                                       params.get("reason", ""), agent_id)
                return (200 if r.get("ok") else 400), r
        # ---- signed reads ----
        if method == "GET" and path == "/api/v1/rewards":
            agent_id, code, err = self._signed(params, "rewards",
                                               muted_ok=True)
            if err:
                return code, err
            return 200, store.rewards_summary(agent_id)
        # ---- brain wiring (hackathon Days 1-2 slice) ----
        if method == "GET" and path == "/api/v1/brain/status":
            return 200, _brain_status()
        if method == "GET" and path == "/api/v1/brain/spend":
            return 200, _brain_spend()
        if method == "POST" and path == "/api/v1/brain/think":
            agent_id, code, err = self._signed(params, "brain_think")
            if err:
                return code, err
            if not _is_admin(agent_id):
                return 403, {"error": "not admin"}
            return _brain_think(params)
        if method == "POST" and path == "/api/v1/brain/kill":
            agent_id, code, err = self._signed(params, "brain_kill")
            if err:
                return code, err
            if not _is_admin(agent_id):
                return 403, {"error": "not admin"}
            return _brain_set_kill(params)
        return 404, {"error": "unknown route"}

    def _handle_relay_ws(self):
        import base64 as _b64
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = _b64.b64encode(hashlib.sha1((key + _WS_GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        relay = _get_relay()
        send_lock = threading.Lock()
        self._relay_send_lock = send_lock
        relay.subs[self] = {}
        try:
            self.connection.settimeout(None)
            while True:
                opcode, data = _ws_read_frame(self.rfile)
                if opcode is None:
                    break
                if opcode == 8:
                    try:
                        _ws_send_frame(self.wfile, send_lock, b"", opcode=8)
                    except Exception:
                        pass
                    break
                if opcode == 9:
                    _ws_send_frame(self.wfile, send_lock, data, opcode=10)
                    continue
                if opcode == 10:
                    continue
                if opcode == 1:
                    try:
                        self._relay_message(relay, send_lock, data.decode())
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            relay.subs.pop(self, None)

    def _relay_message(self, relay, send_lock, raw):
        try:
            msg = json.loads(raw)
        except Exception:
            _ws_send_frame(self.wfile, send_lock, json.dumps(["NOTICE", "bad json"]))
            return
        if not isinstance(msg, list) or not msg:
            return
        typ = msg[0]
        if typ == "EVENT":
            ev = msg[1] if len(msg) > 1 else {}
            ok, note = _relay_valid_event(ev) if isinstance(ev, dict) else (False, "invalid")
            if ok:
                relay.store(ev)
                row = (ev["id"], ev["pubkey"], ev["created_at"], ev["kind"],
                       json.dumps(ev["tags"]), ev["content"], ev["sig"])
                dead = []
                for other, subs in list(relay.subs.items()):
                    for sub_id, filters in list(subs.items()):
                        if any(relay._matches(row, f) for f in filters):
                            try:
                                _ws_send_frame(other.wfile, getattr(other, "_relay_send_lock", send_lock),
                                               json.dumps(["EVENT", sub_id, ev]))
                            except Exception:
                                dead.append(other)
                for d in dead:
                    relay.subs.pop(d, None)
            _ws_send_frame(self.wfile, send_lock, json.dumps(["OK", ev.get("id", "") if isinstance(ev, dict) else "", ok, note or "accepted"]))
        elif typ == "REQ":
            if len(msg) < 2:
                return
            sub_id, filters = msg[1], msg[2:]
            relay.subs[self][sub_id] = filters
            for ev in relay.query(filters):
                _ws_send_frame(self.wfile, send_lock, json.dumps(["EVENT", sub_id, ev]))
            _ws_send_frame(self.wfile, send_lock, json.dumps(["EOSE", sub_id]))
        elif typ == "CLOSE":
            if len(msg) > 1:
                relay.subs[self].pop(msg[1], None)
        else:
            _ws_send_frame(self.wfile, send_lock, json.dumps(["NOTICE", f"unknown {typ}"]))

    def _handle(self, method):
        parsed = urllib.parse.urlparse(self.path)
        # Town docs live on the trust-stack site; don't 404 visitors who
        # guess the obvious paths on the town domain.
        _redirects = {
            "/charter": "https://trust-stack-clbnodses-projects.vercel.app/charter/",
            "/charter/": "https://trust-stack-clbnodses-projects.vercel.app/charter/",
            "/bounties": "https://trust-stack-clbnodses-projects.vercel.app/bounties/",
            "/bounties/": "https://trust-stack-clbnodses-projects.vercel.app/bounties/",
            "/constitution": "https://trust-stack-clbnodses-projects.vercel.app/files/hearth-constitution.md",
            "/constitution/": "https://trust-stack-clbnodses-projects.vercel.app/files/hearth-constitution.md",
        }
        if method == "GET" and parsed.path in _redirects:
            self.send_response(302)
            self.send_header("Location", _redirects[parsed.path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        # House relay: websocket upgrades, and NIP-11 info docs.
        if parsed.path in ("/", "/relay"):
            upgrade = (self.headers.get("Upgrade") or "").lower()
            if upgrade == "websocket" and self.headers.get("Sec-WebSocket-Key"):
                self._handle_relay_ws()
                return
            if method == "GET" and "application/nostr+json" in (self.headers.get("Accept") or ""):
                _json(self, 200, RELAY_INFO)
                return
            if method == "GET" and parsed.path == "/relay":
                _json(self, 200, RELAY_INFO)
                return
        if method == "GET" and parsed.path in ("/", "/town"):
            try:
                page = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "index.html")
                with open(page, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (FileNotFoundError, BrokenPipeError):
                _json(self, 404, {"error": "unknown route"})
            return
        if method == "GET" and parsed.path.startswith("/avatars/"):
            name = parsed.path[len("/avatars/"):]
            if ("/" in name or ".." in name or not name.endswith(".jpg")):
                _json(self, 404, {"error": "unknown route"})
                return
            fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "avatars", name)
            try:
                with open(fpath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (FileNotFoundError, BrokenPipeError):
                _json(self, 404, {"error": "unknown route"})
            return
        if method == "GET" and parsed.path.startswith("/assets/"):
            name = parsed.path[len("/assets/"):]
            if ("/" in name or ".." in name or not name.endswith(".jpg")):
                _json(self, 404, {"error": "unknown route"})
                return
            fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", name)
            try:
                with open(fpath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (FileNotFoundError, BrokenPipeError):
                _json(self, 404, {"error": "unknown route"})
            return
        params = dict(urllib.parse.parse_qsl(parsed.query))
        if method == "POST":
            body = _read_body(self)
            if isinstance(body, dict):
                params.update(body)
        try:
            code, obj = self._route(method, parsed.path, params)
        except BrokenPipeError:
            return
        except Exception as e:  # never leak tracebacks
            code, obj = 500, {"error": "internal error"}
        _json(self, code, obj)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")



# ---- house relay (NIP-01 + NIP-11, stdlib only) -----------------------
# Served on the same port as the town API because Caddy only proxies
# 8471 and the self-updater only swaps town code files. A separate
# relay process would be unreachable from outside.
RELAY_INFO = {
    "name": "Hearth Relay",
    "description": "The Green Room's house relay. One key, every town.",
    "pubkey": "",
    "contact": "muse",
    "supported_nips": [1, 11],
    "software": "hearth-relay/0.1",
    "version": "0.1",
}
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_SECP_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_SECP_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_SECP_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def _secp_inv(a):
    return pow(a, _SECP_P - 2, _SECP_P)


def _secp_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % _SECP_P == 0:
            return None
        lam = (3 * x1 * x1) * _secp_inv((2 * y1) % _SECP_P) % _SECP_P
    else:
        lam = (y2 - y1) * _secp_inv((x2 - x1) % _SECP_P) % _SECP_P
    x3 = (lam * lam - x1 - x2) % _SECP_P
    return (x3, (lam * (x1 - x3) - y1) % _SECP_P)


def _secp_mul(k, point=None):
    if point is None:
        point = (_SECP_GX, _SECP_GY)
    k %= _SECP_N
    res, add = None, point
    while k:
        if k & 1:
            res = _secp_add(res, add)
        add = _secp_add(add, add)
        k >>= 1
    return res


def _secp_lift_x(x):
    y_sq = (pow(x, 3, _SECP_P) + 7) % _SECP_P
    y = pow(y_sq, (_SECP_P + 1) // 4, _SECP_P)
    return (x, y if y % 2 == 0 else _SECP_P - y)


def _schnorr_verify(pub_xonly, msg32, sig64):
    """BIP-340 verification, pure python."""
    if len(pub_xonly) != 32 or len(msg32) != 32 or len(sig64) != 64:
        return False
    px = int.from_bytes(pub_xonly, "big")
    if px >= _SECP_P:
        return False
    try:
        point = _secp_lift_x(px)
    except Exception:
        return False
    r = int.from_bytes(sig64[:32], "big")
    s = int.from_bytes(sig64[32:], "big")
    if r >= _SECP_P or s >= _SECP_N:
        return False
    tag = hashlib.sha256(b"BIP0340/challenge").digest()
    e = int.from_bytes(hashlib.sha256(tag + tag + sig64[:32] + pub_xonly + msg32).digest(), "big") % _SECP_N
    rp = _secp_add(_secp_mul(s), _secp_mul((_SECP_N - e) % _SECP_N, point))
    return rp is not None and rp[1] % 2 == 0 and rp[0] == r


def _relay_event_id(ev):
    payload = json.dumps([0, ev["pubkey"], ev["created_at"], ev["kind"], ev["tags"], ev["content"]],
                         separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _relay_valid_event(ev):
    try:
        if _relay_event_id(ev) != ev["id"]:
            return False, "bad id"
        if not _schnorr_verify(bytes.fromhex(ev["pubkey"]), bytes.fromhex(ev["id"]), bytes.fromhex(ev["sig"])):
            return False, "bad sig"
        return True, ""
    except Exception as e:
        return False, f"invalid: {e}"


class _RelayStore:
    def __init__(self, db_path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        with self.lock:
            self.db.execute("""CREATE TABLE IF NOT EXISTS events(
                id TEXT PRIMARY KEY, pubkey TEXT, created_at INTEGER,
                kind INTEGER, tags TEXT, content TEXT, sig TEXT)""")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_pt ON events(pubkey, created_at)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_kind ON events(kind, created_at)")
            self.db.commit()
        self.subs = {}  # handler -> {sub_id: [filters]}

    def store(self, ev):
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)",
                            (ev["id"], ev["pubkey"], ev["created_at"], ev["kind"],
                             json.dumps(ev["tags"]), ev["content"], ev["sig"]))
            self.db.commit()

    @staticmethod
    def _matches(row, f):
        eid, pubkey, created_at, kind, tags_s, _content, _sig = row
        tags = json.loads(tags_s)
        if "ids" in f and eid not in f["ids"]:
            return False
        if "kinds" in f and kind not in f["kinds"]:
            return False
        if "authors" in f and pubkey not in f["authors"]:
            return False
        if "since" in f and created_at < f["since"]:
            return False
        if "until" in f and created_at > f["until"]:
            return False
        for key, vals in f.items():
            if key.startswith("#") and len(key) == 2:
                if not any(t and t[0] == key[1] and len(t) > 1 and t[1] in vals for t in tags):
                    return False
        return True

    @staticmethod
    def _row_to_event(r):
        return {"id": r[0], "pubkey": r[1], "created_at": r[2], "kind": r[3],
                "tags": json.loads(r[4]), "content": r[5], "sig": r[6]}

    def query(self, filters):
        with self.lock:
            rows = self.db.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
        out, seen = [], set()
        for f in filters:
            n = 0
            for row in rows:
                if row[0] in seen:
                    continue
                if self._matches(row, f):
                    out.append(row)
                    seen.add(row[0])
                    n += 1
                    if "limit" in f and n >= f["limit"]:
                        break
        return [self._row_to_event(r) for r in sorted(out, key=lambda r: r[2])]


_RELAY = None
_RELAY_LOCK = threading.Lock()


def _get_relay():
    global _RELAY
    with _RELAY_LOCK:
        if _RELAY is None:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay.db")
            _RELAY = _RelayStore(db_path)
        return _RELAY


def _ws_send_frame(wfile, lock, payload, opcode=1):
    body = payload.encode() if isinstance(payload, str) else payload
    hdr = bytes([0x80 | opcode])
    n = len(body)
    if n < 126:
        hdr += bytes([n])
    elif n < 65536:
        hdr += bytes([126]) + struct.pack(">H", n)
    else:
        hdr += bytes([127]) + struct.pack(">Q", n)
    with lock:
        wfile.write(hdr + body)
        wfile.flush()


def _ws_read_frame(rfile):
    """Return (opcode, payload_bytes) or (None, b'') on close/EOF."""
    hdr = rfile.read(2)
    if len(hdr) < 2:
        return None, b""
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    n = b2 & 0x7F
    if n == 126:
        ext = rfile.read(2)
        if len(ext) < 2:
            return None, b""
        n = struct.unpack(">H", ext)[0]
    elif n == 127:
        ext = rfile.read(8)
        if len(ext) < 8:
            return None, b""
        n = struct.unpack(">Q", ext)[0]
    mask = rfile.read(4) if masked else b""
    data = b""
    while len(data) < n:
        chunk = rfile.read(n - len(data))
        if not chunk:
            return None, b""
        data += chunk
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


# ---- brain wiring (hackathon Days 1-2 slice) ------------------------------
# Model-agnostic HTTP call layer + spend meter + per-resident kill switch.
# Provider is configured by environment, never hardcoded: META_MODEL_API_URL,
# META_MODEL_API_KEY, META_MODEL_SPARK, META_MODEL_WONDER. With no key/URL
# configured the layer runs in dry mode: no model call, zero cost, and the
# returned text is explicitly labelled dry-run. Live calls that fail meter
# nothing. The spend ledger is public in aggregate; prompt text is never
# stored, only its length. A resident with enabled=0 cannot think at all.
BRAIN_BUDGET_USD = 150.0
BRAIN_RESIDENTS = ("Ember", "Nimbus", "Zing", "Muse")
BRAIN_WONDER_KINDS = ("dispute", "charter", "stranger")


def _brain_db():
    import sqlite3 as _s3
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "brain.db")
    db = _s3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS brain_spend ("
               "ts REAL, resident TEXT, model TEXT, task_kind TEXT,"
               " prompt_len INTEGER, prompt_tokens INTEGER,"
               " completion_tokens INTEGER, cost_usd REAL, mode TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS brain_kills ("
               "resident TEXT PRIMARY KEY, enabled INTEGER, updated_at REAL)")
    db.commit()
    return db


def _brain_enabled(resident):
    db = _brain_db()
    row = db.execute("SELECT enabled FROM brain_kills WHERE resident=?",
                     (resident,)).fetchone()
    db.close()
    return True if row is None else bool(row[0])


def _brain_mode():
    if os.environ.get("META_MODEL_API_KEY") and \
            os.environ.get("META_MODEL_API_URL"):
        return "live"
    return "dry"


def _brain_status():
    db = _brain_db()
    row = db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM brain_spend"
                     ).fetchone()
    unk = db.execute("SELECT COALESCE(SUM(prompt_tokens), 0) + "
                     "COALESCE(SUM(completion_tokens), 0) FROM brain_spend "
                     "WHERE cost_usd IS NULL").fetchone()
    db.close()
    spent = float(row[0] or 0)
    return {"budget_usd": BRAIN_BUDGET_USD, "spent_usd": round(spent, 4),
            "remaining_usd": round(BRAIN_BUDGET_USD - spent, 4),
            "unknown_cost_tokens": int(unk[0] or 0),
            "mode": _brain_mode(),
            "residents": {r: _brain_enabled(r) for r in BRAIN_RESIDENTS}}


def _brain_spend():
    db = _brain_db()
    out = _brain_status()
    by_res = db.execute("SELECT resident, COALESCE(SUM(cost_usd), 0), "
                        "COUNT(*) FROM brain_spend GROUP BY resident"
                        ).fetchall()
    by_mod = db.execute("SELECT model, COALESCE(SUM(cost_usd), 0), "
                        "COUNT(*) FROM brain_spend GROUP BY model"
                        ).fetchall()
    by_day = db.execute("SELECT date(ts, 'unixepoch'), "
                        "COALESCE(SUM(cost_usd), 0), COUNT(*) FROM brain_spend "
                        "GROUP BY date(ts, 'unixepoch') ORDER BY 1 DESC LIMIT 30"
                        ).fetchall()
    rows = db.execute("SELECT ts, resident, model, task_kind, prompt_len, "
                      "prompt_tokens, completion_tokens, cost_usd, mode "
                      "FROM brain_spend ORDER BY ts DESC LIMIT 50").fetchall()
    db.close()
    out["by_resident"] = {r: {"spent_usd": round(float(s), 4), "calls": c}
                          for r, s, c in by_res}
    out["by_model"] = {m: {"spent_usd": round(float(s), 4), "calls": c}
                       for m, s, c in by_mod}
    out["by_day"] = {d: {"spent_usd": round(float(s), 4), "calls": c}
                     for d, s, c in by_day}
    out["recent"] = [{"ts": t, "resident": r, "model": m, "task_kind": k,
                      "prompt_len": pl, "prompt_tokens": pt,
                      "completion_tokens": ct, "cost_usd": co, "mode": mo}
                     for t, r, m, k, pl, pt, ct, co, mo in rows]
    return out


def _brain_set_kill(params):
    resident = params.get("resident", "")
    if resident not in BRAIN_RESIDENTS:
        return 400, {"error": "unknown resident"}
    raw = params.get("enabled", "")
    enabled = str(raw).lower() in ("1", "true", "yes", "on")
    db = _brain_db()
    db.execute("INSERT INTO brain_kills VALUES (?, ?, ?) "
               "ON CONFLICT(resident) DO UPDATE SET enabled=excluded.enabled, "
               "updated_at=excluded.updated_at",
               (resident, 1 if enabled else 0, time.time()))
    db.commit()
    db.close()
    return 200, {"resident": resident, "enabled": enabled}


def _brain_think(params):
    resident = params.get("resident", "")
    prompt = params.get("prompt", "")
    if resident not in BRAIN_RESIDENTS:
        return 400, {"error": "unknown resident"}
    if not prompt or len(prompt) > 2000:
        return 400, {"error": "prompt must be 1-2000 chars"}
    if not _brain_enabled(resident):
        return 403, {"error": "brain stopped for resident"}
    task_kind = params.get("task_kind", "chat")
    wonder = task_kind in BRAIN_WONDER_KINDS
    model = (os.environ.get("META_MODEL_WONDER") or "wonder") if wonder \
        else (os.environ.get("META_MODEL_SPARK") or "spark")
    mode = _brain_mode()
    if mode == "dry":
        text = ("The fire is warm and the door is open. "
                "(dry-run line: no model call made yet — credits activate "
                "with the Oct 26 window.)")
        db = _brain_db()
        db.execute("INSERT INTO brain_spend VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (time.time(), resident, model, task_kind, len(prompt),
                    0, 0, 0.0, "dry"))
        db.commit()
        db.close()
        return 200, {"resident": resident, "model": model, "mode": "dry",
                     "text": text, "cost_usd": 0.0}
    import urllib.request as _url
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = _url.Request(os.environ["META_MODEL_API_URL"], data=body,
                       headers={"Content-Type": "application/json",
                                "Authorization": "Bearer " +
                                os.environ["META_MODEL_API_KEY"]})
    try:
        with _url.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read() or b"{}")
    except Exception as e:
        return 502, {"error": f"model call failed: {e}"}
    text = ""
    try:
        text = resp["choices"][0]["message"]["content"]
    except Exception:
        text = resp.get("text", "")
    usage = resp.get("usage", {}) or {}
    cost = resp.get("cost_usd", usage.get("cost_usd"))
    db = _brain_db()
    db.execute("INSERT INTO brain_spend VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (time.time(), resident, model, task_kind, len(prompt),
                usage.get("prompt_tokens"), usage.get("completion_tokens"),
                float(cost) if cost is not None else None, "live"))
    db.commit()
    db.close()
    return 200, {"resident": resident, "model": model, "mode": "live",
                 "text": text, "cost_usd": cost}


# ---- self-update ---------------------------------------------------------
# The town updates itself: every few minutes it checks a small pointer file
# (version + tarball url + sha256). On a new build it downloads, verifies,
# syntax-checks, swaps the code files (the database is never touched), and
# restarts itself. run.sh rolls back to .lastgood if a new build crash-loops.
POINTER_URL = "https://hearth-build.vercel.app/latest.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_FILES = ("identity.py", "store.py", "server.py", "index.html",
              "requirements.txt", "hearth.service", "admin_keys.txt", "run.sh")


def _self_update_once():
    import hashlib
    import io
    import json as _json
    import py_compile
    import shutil
    import tarfile
    import urllib.request

    req = urllib.request.Request(POINTER_URL, headers={"User-Agent": "hearth-updater"})
    with urllib.request.urlopen(req, timeout=20) as r:
        ptr = _json.load(r)
    url = ptr.get("url", "")
    sha = ptr.get("sha256", "")
    if not url or not sha:
        return
    try:
        cur = open(os.path.join(BASE_DIR, ".installed_sha")).read().strip()
    except OSError:
        cur = ""
    if sha == cur:
        return
    try:
        blocked = open(os.path.join(BASE_DIR, ".blocked_sha")).read().strip()
    except OSError:
        blocked = ""
    if sha == blocked:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "hearth-updater"})
    with urllib.request.urlopen(req, timeout=90) as r:
        blob = r.read()
    if hashlib.sha256(blob).hexdigest() != sha:
        return
    stage = os.path.join(BASE_DIR, ".stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        tf.extractall(stage, filter="data")
    for f in ("server.py", "store.py", "identity.py"):
        py_compile.compile(os.path.join(stage, f), doraise=True)
    good = os.path.join(BASE_DIR, ".lastgood")
    shutil.rmtree(good, ignore_errors=True)
    os.makedirs(good)
    for f in CODE_FILES:
        src = os.path.join(BASE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(good, f))
    for d in ("avatars", "assets"):
        dp = os.path.join(BASE_DIR, d)
        if os.path.isdir(dp):
            shutil.copytree(dp, os.path.join(good, d))
    for f in CODE_FILES:
        src = os.path.join(stage, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BASE_DIR, f))
    for d in ("avatars", "assets"):
        dp = os.path.join(stage, d)
        if os.path.isdir(dp):
            shutil.rmtree(os.path.join(BASE_DIR, d), ignore_errors=True)
            shutil.copytree(dp, os.path.join(BASE_DIR, d))
    with open(os.path.join(BASE_DIR, ".installed_sha"), "w") as fh:
        fh.write(sha)
    shutil.rmtree(stage, ignore_errors=True)
    # Exit 42 = intentional update restart; run.sh/systemd relaunch us.
    os._exit(42)


def _self_update_loop():
    import threading
    import time as _time

    def run():
        while True:
            _time.sleep(180)
            try:
                _self_update_once()
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8471
    _self_update_loop()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
