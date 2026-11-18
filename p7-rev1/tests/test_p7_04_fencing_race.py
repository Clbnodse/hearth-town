#!/usr/bin/env python3
"""P7-04 fencing race.

Two REAL OS processes: a worker subprocess holds run 1 (fencing 1)
and finishes it; the main process then issues run 2 (fencing 2).
The stale worker then attempts to append/commit with its old
fencing token and old executor token — every attempt must fail,
including an /action attempt after action_started, and run 2 must
be untouched.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness

PORT = 18904
SYNC = "/tmp/p7-04-sync"

WORKER = '''#!/usr/bin/env python3
import json, os, sys, time, urllib.request, urllib.error

base, ember_tok, nimbus_tok, job_id, sync = sys.argv[1:6]

def call(method, path, body=None, token="", headers=None):
    h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

# create run 1 + drive to ACTION_AUTHORIZED + claim + complete
s, run = call("POST", "/v1/residents/ember/runs",
              {"idempotency_key": "race-1", "mode": "live", "lease_seconds": 600,
               "policy_version": "p7-policy-1"},
              token=ember_tok)
assert s == 201, (s, run)
rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
for etype in ("memory_loaded", "goal_proposed", "goal_accepted",
              "plan_proposed", "plan_accepted", "action_authorized"):
    s, b = call("POST", f"/v1/residents/ember/runs/{rid}/events",
                {"event_type": etype, "fencing_token": ft, "payload": {}},
                token=ember_tok, headers={"X-Run-Token": et})
    assert s == 201, (etype, s, b)
s, b = call("POST", f"/v1/residents/ember/runs/{rid}/action",
            {"action": {"type": "claim_job", "job_id": job_id,
                        "idempotency_key": "race-claim"},
             "fencing_token": ft, "adapter_output_units": 0},
            token=ember_tok, headers={"X-Run-Token": et})
assert s == 200, (s, b)
s, b = call("POST", f"/v1/residents/ember/runs/{rid}/events",
            {"event_type": "evaluation_recorded", "fencing_token": ft,
             "payload": {"outcome": "executed"}},
            token=ember_tok, headers={"X-Run-Token": et})
assert s == 201, (s, b)
s, b = call("POST", f"/v1/residents/ember/runs/{rid}/complete",
            {"reconciled": False}, token=ember_tok)
assert s == 200, (s, b)
with open(os.path.join(sync, "run1.json"), "w") as f:
    json.dump({"run_id": rid, "fencing": ft, "token": et}, f)

# wait for the main process to issue run 2
run2_path = os.path.join(sync, "run2.json")
for _ in range(50):
    if os.path.exists(run2_path):
        break
    time.sleep(0.2)
with open(run2_path) as f:
    run2 = json.load(f)
rid2, ft2 = run2["run_id"], run2["fencing_token"]

results = {}
# stale append to finished run 1
s, b = call("POST", f"/v1/residents/ember/runs/{rid}/events",
            {"event_type": "evaluation_recorded", "fencing_token": ft,
             "payload": {}}, token=ember_tok, headers={"X-Run-Token": et})
results["stale_append_run1"] = (s, b.get("error"))
# stale /action on finished run 1 (after action_started)
s, b = call("POST", f"/v1/residents/ember/runs/{rid}/action",
            {"action": {"type": "noop"}, "fencing_token": ft,
             "adapter_output_units": 0}, token=ember_tok,
            headers={"X-Run-Token": et})
results["stale_action_run1"] = (s, b.get("error"))
# stale fencing token against run 2 (old token + old fencing)
s, b = call("POST", f"/v1/residents/ember/runs/{rid2}/events",
            {"event_type": "memory_loaded", "fencing_token": ft,
             "payload": {}}, token=ember_tok, headers={"X-Run-Token": et})
results["stale_append_run2"] = (s, b.get("error"))
s, b = call("POST", f"/v1/residents/ember/runs/{rid2}/action",
            {"action": {"type": "noop"}, "fencing_token": ft,
             "adapter_output_units": 0}, token=ember_tok,
            headers={"X-Run-Token": et})
results["stale_action_run2"] = (s, b.get("error"))
# right fencing token, wrong executor token, and a Bearer that is
# not bound to ember: neither credential authorizes run 2.
s, b = call("POST", f"/v1/residents/ember/runs/{rid2}/events",
            {"event_type": "memory_loaded", "fencing_token": ft2,
             "payload": {}}, token=nimbus_tok, headers={"X-Run-Token": et})
results["wrong_token_append_run2"] = (s, b.get("error"))
with open(os.path.join(sync, "worker_results.json"), "w") as f:
    json.dump(results, f)
print(json.dumps(results))
'''


def main():
    h = Harness("p7_04", PORT).start()
    try:
        h.clear_rates()
        # Rev 1 (S5): run 2 is created seconds after run 1's action,
        # so the policy minimum cooldown is 0 for this test.
        s, b = h.set_run_policy("ember", {"min_cooldown_ms": 0})
        assert s == 200, (s, b)
        job = h.make_job("fencing race quest", tags=["host", "quest"])
        os.makedirs(SYNC, exist_ok=True)
        for f in ("run1.json", "run2.json", "worker_results.json"):
            p = os.path.join(SYNC, f)
            if os.path.exists(p):
                os.remove(p)
        worker_path = "/tmp/p7_04_worker.py"
        with open(worker_path, "w") as f:
            f.write(WORKER)
        proc = subprocess.Popen(
            [sys.executable, worker_path, h.root, h.tokens["ember"],
             h.tokens["nimbus"], job["id"], SYNC],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Wait for the worker to finish run 1 (separate OS process).
        run1_path = os.path.join(SYNC, "run1.json")
        for _ in range(50):
            if os.path.exists(run1_path):
                break
            time.sleep(0.2)
        assert os.path.exists(run1_path), "worker did not finish run 1"
        with open(run1_path) as f:
            run1 = json.load(f)
        assert run1["fencing"] == 1, run1
        assert proc.poll() is None, "worker exited early"
        # Main process issues run 2 (fencing 2).
        s, run2 = h.create_run("ember", mode="live", idem="race-2")
        assert s == 201, (s, run2)
        assert run2["fencing_token"] == 2, run2
        assert run2["id"] != run1["run_id"]
        with open(os.path.join(SYNC, "run2.json"), "w") as f:
            json.dump({"run_id": run2["id"],
                       "fencing_token": run2["fencing_token"]}, f)
        out, err = proc.communicate(timeout=60)
        assert proc.returncode == 0, f"worker failed: {err}\n{out}"
        with open(os.path.join(SYNC, "worker_results.json")) as f:
            res = json.load(f)
        print("  worker (PID separate) stale attempts:", res)
        for key, (status, error) in res.items():
            assert status in (403, 409), f"{key} unexpectedly {status}: {error}"
        assert res["stale_append_run1"][1] == "invalid_run_transition", res
        assert res["stale_action_run1"][1] == "invalid_run_transition", res
        assert res["stale_append_run2"][1] == "fencing_stale", res
        assert res["stale_action_run2"][1] == "executor_token_invalid", res
        assert res["wrong_token_append_run2"][1] == "token_not_bound_to_resident", res
        # Run 2 is untouched: still LEASED, and its trace holds only
        # the two creation events (run_created, lease_claimed) — no
        # event from the stale worker.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{run2['id']}/events",
                      token=h.tokens["ember"])
        assert s == 200 and b["count"] == 2, (s, b)
        assert [e["event_type"] for e in b["events"]] == [
            "run_created", "lease_claimed"], b
        s, b = h.call("GET", f"/v1/residents/ember/runs/{run2['id']}",
                      token=h.tokens["ember"])
        assert b["status"] == "LEASED", b
        print("P7-04 fencing race: PASS (stale worker blocked on all "
              "four attempts; run 2 untouched)")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
