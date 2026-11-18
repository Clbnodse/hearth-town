#!/usr/bin/env python3
"""Shared in-process harness for the Priority 7 (api-42, rev 1) tests.

Same pattern as test_api41.py: the api-42 REV stage is copied to a
per-test /tmp dir (never the stage itself), the server module is
loaded in-process, local throwaway test tokens are injected into
_GAME_API_TOKEN_HASHES (never real ones), a fixture game_api.json is
written before the first request, and the whole temp dir (including
the per-resident runs_*.db trace files) is deleted afterwards.

Each test file imports this module and drives one P7 test against a
real HTTP server, real game_api.json storage, real SQLite trace
files, and (where the test requires it) real OS subprocesses.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT = os.path.join(BASE, "work", "stage-v17-game-api42-REV")
# Revision 1: the policy version every run creation must carry.
P7_POLICY_VERSION = "p7-policy-1"
# Test-only fake-model side channel (R1): the fake suggest script
# reads this file (never env vars). Tests write it, the fake reads
# it, and the fake writes the captured model input here.
FAKE_MODEL_FILE = "/tmp/p7_fake_model.json"
FAKE_CAPTURE_FILE = "/tmp/p7_fake_captured_input.json"
V26_SHA = "f27d758d054f84d76447a0be993f0605117643db35f7af97d94e753327a37f5b"
V26_SIZE = 79828
NEW_VER = "20261114-game-api-42"


def _local_token(agent, tag):
    return ("local-test-token-p7-" + agent + "-" + tag + "-" +
            hashlib.sha256(("p7-local-test-" + tag + "-" + agent).encode()).hexdigest()[:12])


def _resident(rid, tier="T1", lifetime=0):
    return {"id": rid, "display_name": rid.capitalize(), "home_lot": "",
            "public_bio": "", "status": "offline", "version": 1, "tier": tier,
            "credits": 0, "lifetime_earned": lifetime, "lifetime_spent": 0,
            "inventory": {}, "job_tags": [], "updated_at": "2026-11-10T00:00:00Z",
            "credit_ledger": []}


def fixture():
    return {
        "tokens": [], "proposals": [], "tasks": [], "messages": [],
        "kit_fetches": [], "oauth_clients": [], "oauth_codes": [],
        "oauth_tokens": [], "presence": {},
        "residents": [
            _resident("muse"),
            _resident("ember", tier="T2", lifetime=15),
            _resident("nimbus", tier="T2", lifetime=25),
            _resident("zing"),
            _resident("miro"),
            _resident("claude"), _resident("grok"), _resident("chatgpt"), _resident("metaai"),
        ],
        "jobs": [], "events": [],
    }


class Harness:
    def __init__(self, name, port):
        self.name = name
        self.port = port
        self.stage = "/tmp/p7-stage-" + name
        self.root = "http://127.0.0.1:%d/game-api" % port
        self.mod = None
        self.srv = None
        self.tokens = {}

    def start(self):
        shutil.rmtree(self.stage, ignore_errors=True)
        shutil.copytree(DRAFT, self.stage,
                        ignore=shutil.ignore_patterns("__pycache__"))
        spec = importlib.util.spec_from_file_location(
            "p7_server_" + self.name, os.path.join(self.stage, "server.py"))
        self.mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, self.stage)
        spec.loader.exec_module(self.mod)
        self.tokens = {a: _local_token(a, self.name)
                       for a in ("muse", "ember", "nimbus", "zing", "miro",
                                 "claude", "grok", "chatgpt")}
        for agent, tok in self.tokens.items():
            self.mod._GAME_API_TOKEN_HASHES[agent] = \
                hashlib.sha256(tok.encode()).hexdigest()
        with open(os.path.join(self.stage, "game_api.json"), "w") as f:
            json.dump(fixture(), f)
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.port),
                                       self.mod.Handler)
        t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        # Rev 1 (S5): live mode is opt-in per resident, server-side.
        # The seeded default is live_enabled=False, so the harness
        # enables live for ember (the runner resident) once the
        # server is up — as muse, the only role allowed to set it.
        # Tests that exercise the gate itself (P7-22) set the policy
        # explicitly afterwards.
        s, b = self.set_run_policy("ember", {"live_enabled": True})
        assert s == 200, f"enable live for ember: HTTP {s}: {b}"
        return self

    def set_run_policy(self, resident, policy, token=None):
        """POST /v1/residents/{id}/run-policy (muse/owner only)."""
        return self.call("POST", "/v1/residents/%s/run-policy" % resident,
                         policy,
                         token=token if token is not None
                         else self.tokens["muse"])

    def restart(self):
        """Restart the HTTP server on the same port, same stage dir,
        same fixture + trace DB files (simulates a process restart;
        the module stays loaded, the on-disk state is re-read)."""
        if self.srv is not None:
            self.srv.shutdown()
            self.srv.server_close()
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.port),
                                       self.mod.Handler)
        t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        return self

    def stop(self):
        if self.srv is not None:
            self.srv.shutdown()
            self.srv.server_close()
            self.srv = None
        shutil.rmtree(self.stage, ignore_errors=True)

    def call(self, method, path, body=None, token="", extra_headers=None):
        headers = {"Authorization": "Bearer " + token,
                   "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(
            self.root + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw}

    def clear_rates(self):
        self.mod._ECON_WRITE_RATE.clear()

    def read_db(self):
        with open(os.path.join(self.stage, "game_api.json")) as f:
            return json.load(f)

    def patch_db(self, fn):
        data = self.read_db()
        fn(data)
        with open(os.path.join(self.stage, "game_api.json"), "w") as f:
            json.dump(data, f)
        return data

    def make_job(self, title, tags=None, reward=5):
        body = {"title": title, "brief": "p7 test job: " + title,
                "reward_credits": reward, "max_claimants": 1,
                "idempotency_key": "p7-job-" + self.name + "-" +
                hashlib.sha256(title.encode()).hexdigest()[:8]}
        if tags:
            body["job_tags"] = tags
        s, b = self.call("POST", "/v1/jobs", body, token=self.tokens["muse"])
        assert s == 201, f"make_job HTTP {s}: {b}"
        return b

    def create_run(self, resident="ember", mode="dry_run", allowlist=None,
                   idem="run-1", lease_seconds=600, cooldown_ms=0,
                   policy_version=P7_POLICY_VERSION):
        body = {"idempotency_key": idem, "mode": mode,
                "lease_seconds": lease_seconds, "cooldown_ms": cooldown_ms,
                "policy_version": policy_version}
        if allowlist is not None:
            body["allowlist"] = allowlist
        return self.call("POST", "/v1/residents/%s/runs" % resident, body,
                         token=self.tokens[resident])

    def append_event(self, resident, run_id, event_type, fencing_token,
                     payload=None, token=None, exec_token=None):
        headers = {}
        if exec_token:
            headers["X-Run-Token"] = exec_token
        return self.call(
            "POST", "/v1/residents/%s/runs/%s/events" % (resident, run_id),
            {"event_type": event_type, "fencing_token": fencing_token,
             "payload": payload or {}},
            token=token if token is not None else self.tokens[resident],
            extra_headers=headers)

    def drive_to_authorized(self, resident, run_id, fencing_token,
                            exec_token=None):
        """Append the planning-phase events up to ACTION_AUTHORIZED.
        Returns the last (status, body)."""
        steps = [
            ("memory_loaded", {"entries": 0}),
            ("goal_proposed", {"goal": {"ref": "job",
                                        "kind": "claim_job"}}),
            ("goal_accepted", {"goal": {"ref": "job"}}),
            ("plan_proposed", {"plan": {"action": {"type": "claim_job"}}}),
            ("plan_accepted", {"plan": {"action": {"type": "claim_job"}}}),
            ("action_authorized", {"action": {"type": "claim_job"}}),
        ]
        last = None
        for et, payload in steps:
            last = self.append_event(resident, run_id, et, fencing_token,
                                     payload, exec_token=exec_token)
            assert last[0] == 201, f"drive {et} HTTP {last[0]}: {last[1]}"
        return last

    def run_store(self, resident):
        return self.mod._P7RunStore(resident)

    # -- test-only fake model (R1) ----------------------------------
    def set_fake_model(self, suggestion=None, raw=None, sleep=None,
                       stream=None):
        """Write the fake-model control file. The test-only fake
        suggest script reads it (never env vars). Exactly one of
        suggestion (a dict, serialised as the stdout JSON), raw
        (a verbatim stdout string), or stream (chunk size for an
        unbounded output loop) may be given; sleep makes the
        fake sleep first (timeout tests)."""
        assert ((suggestion is None) != (raw is None) or sleep is not None
                or stream is not None), \
            "set_fake_model needs suggestion xor raw xor stream (sleep optional)"
        doc = {}
        if suggestion is not None:
            doc["json"] = suggestion
        if raw is not None:
            doc["raw"] = raw
        if stream is not None:
            doc["stream"] = stream
        if sleep is not None:
            doc["sleep"] = sleep
        with open(FAKE_MODEL_FILE, "w") as f:
            json.dump(doc, f)

    def clear_fake_model(self):
        for path in (FAKE_MODEL_FILE, FAKE_CAPTURE_FILE):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def fake_captured_input(self):
        """The stdin payload the fake suggest script received (the
        minimised model context), or None if it never ran."""
        try:
            with open(FAKE_CAPTURE_FILE) as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def public_events(self, etype=None):
        s, b = self.call("GET", "/v1/events?limit=100",
                         token=self.tokens["muse"])
        assert s == 200, f"GET events HTTP {s}: {b}"
        evs = b["events"]
        if etype:
            evs = [e for e in evs if e.get("type") == etype]
        return evs
