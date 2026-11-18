#!/usr/bin/env python3
"""P7-01 model-process credential isolation (rev 1).

The model runs in a separate OS process with NO credential. It holds
no token, no board client, no DB handle, and no executor socket — only
a narrow suggestion channel (stdin/stdout JSON).

Revision 1 changes (Claude audit R1/R2):
  - the P7_FAKE_MODEL_* hooks are GONE from the production path, so
    this test now asserts they do NOT reach the child even when the
    parent env sets them (v1 asserted the opposite);
  - spawn uses subprocess.Popen + a bounded read, so the recording
    wrapper patches Popen, not run;
  - the fake model is the test-only script (file side-channel),
    selected by monkeypatching bl.P7_SUGGEST_SCRIPT.

Checks (all against the real patched server + real subprocess):
  (a) the child is a separate OS process (distinct PID);
  (b) the child's environment is STRICT — exactly PATH, HOME,
      PYTHONPATH — no token-like key or value survives, and none of
      the P7_FAKE_MODEL_* hooks is present (verified by capturing
      the real spawn env);
  (c) the only channel is stdin/stdout (no pass_fds, no sockets);
  (d) the production subprocess source contains no board/DB/
      credential access (no Bearer, no urllib, no sqlite3, no
      surrogate helper) and no P7_FAKE_MODEL hook.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness, FAKE_MODEL_FILE

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import bounded_loop as bl

FAKE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fake_reasoning_suggest.py")

PORT = 18901


def fake_suggestion(job_id):
    return {"chosen_job_id": job_id, "declined_job_id": None,
            "decline_reason": "",
            "ranking": [{"job_id": job_id, "score": 0.9,
                         "reason": "matches host tag"}],
            "goals": [{"text": "Claim the job", "ref": job_id}],
            "uncertainty": [],
            "evidence": {"wake_ids": [], "memory_seqs": [],
                         "job_ids": [job_id]},
            "confidence": 0.9, "alternatives": []}


def main():
    h = Harness("p7_01", PORT).start()
    try:
        h.clear_rates()
        job = h.make_job("isolation quest", tags=["host", "quest"])
        # Poison the parent env: if any of this reaches the child,
        # the test fails. The three P7_FAKE_MODEL_* hooks are the
        # point of the revision: they must NOT be copied through.
        os.environ["EMBER_TOKEN"] = h.tokens["ember"]
        os.environ["P7_FAKE_MODEL_JSON"] = json.dumps(
            fake_suggestion(job["id"]))
        os.environ["P7_FAKE_MODEL_RAW"] = "should-not-leak"
        os.environ["P7_FAKE_MODEL_SLEEP"] = "999"
        os.environ["P7_MODEL_TIMEOUT_S"] = "999"
        os.environ["HEARTH_API_BASE"] = h.root
        os.environ["FAKE_BOARD_CLIENT"] = "should-not-leak"
        h.set_fake_model(suggestion=fake_suggestion(job["id"]))
        captured = {}

        real_popen = subprocess.Popen

        def recording_popen(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return real_popen(*args, **kwargs)

        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = FAKE_SCRIPT
        bl.subprocess.Popen = recording_popen
        try:
            suggestion, code, units, latency = bl.spawn_model_suggestion(
                {"resident_id": "ember", "wake": [], "memory": [],
                 "candidates": [job], "lessons": []})
        finally:
            bl.subprocess.Popen = real_popen
            bl.P7_SUGGEST_SCRIPT = old_script
        assert code is None, f"unexpected reason code {code}"
        assert suggestion["chosen_job_id"] == job["id"]
        assert isinstance(units, int) and units >= 0
        # (b) strict env: exactly PATH, HOME, PYTHONPATH
        env = captured["kwargs"].get("env", {})
        assert isinstance(env, dict), "spawn did not pass an explicit env"
        assert set(env) == {"PATH", "HOME", "PYTHONPATH"}, \
            f"child env is not the strict set: {sorted(env)}"
        bad_keys = [k for k in env
                    if any(t in k.upper() for t in
                           ("TOKEN", "SECRET", "KEY", "CONNECTOR", "BASE",
                            "API", "BEARER", "AUTH"))]
        assert not bad_keys, f"token-like keys in child env: {bad_keys}"
        for k, v in env.items():
            assert h.tokens["ember"] not in str(v), \
                f"ember token leaked into child env key {k}"
            assert h.root not in str(v), \
                f"API base leaked into child env key {k}"
        # (b2) revision 1: the fake-model hooks must NOT be present,
        # even though the parent env sets all three (plus the
        # timeout override).
        for hook in ("P7_FAKE_MODEL_JSON", "P7_FAKE_MODEL_RAW",
                     "P7_FAKE_MODEL_SLEEP", "P7_MODEL_TIMEOUT_S"):
            assert hook not in env, f"test hook {hook} reached the child"
        # (c) stdin/stdout only (Popen: no timeout kwarg — the
        # timeout is enforced by the reader thread, not by Popen)
        kwargs = captured["kwargs"]
        assert kwargs.get("pass_fds") in (None, ()), "fds passed to child"
        assert kwargs.get("stdin") == subprocess.PIPE, "stdin is not a pipe"
        assert kwargs.get("stdout") == subprocess.PIPE, "stdout not a pipe"
        assert "timeout" not in kwargs, "Popen must not take a timeout"
        assert captured["args"][0][1] == FAKE_SCRIPT, \
            "spawn did not invoke the (monkeypatched) suggest script"
        # (a) separate OS process, direct proof via the fake script
        proc = subprocess.Popen(
            [sys.executable, FAKE_SCRIPT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
        out, _err = proc.communicate(
            json.dumps({"resident_id": "ember"}).encode(), timeout=30)
        assert proc.pid != os.getpid(), "child is not a separate process"
        assert proc.returncode == 0, f"child exit {proc.returncode}"
        result = json.loads(out.decode())
        assert result["suggestion"]["chosen_job_id"] == job["id"]
        # (d) the PRODUCTION subprocess source has no board/DB/
        # credential access and no fake-model hook
        src = open(old_script).read()
        for marker in ("Bearer", "urllib", "sqlite3", "add_surrogate",
                       "requests", "http.client", "P7_FAKE_MODEL"):
            assert marker not in src, f"subprocess source contains {marker}"
        assert "Reasoner" in src, "subprocess must construct the model"
        assert "deliberate" in src, "subprocess must call deliberate()"
        print("P7-01 model-process credential isolation: PASS "
              "(separate PID, strict env, stdin/stdout only, no "
              "board/DB/credential code and no fake hook in the "
              "production subprocess)")
        return 0
    finally:
        for k in ("EMBER_TOKEN", "P7_FAKE_MODEL_JSON", "P7_FAKE_MODEL_RAW",
                  "P7_FAKE_MODEL_SLEEP", "P7_MODEL_TIMEOUT_S",
                  "HEARTH_API_BASE", "FAKE_BOARD_CLIENT"):
            os.environ.pop(k, None)
        h.clear_fake_model()
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
