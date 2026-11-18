#!/usr/bin/env python3
"""Priority 4, first bounded autonomy slice — Ember's client-side runner.

A deterministic, rule-based planner (no model calls, no LLM) that runs
ONE bounded loop per invocation against the live api-36 endpoints
(or a local stage copy):

  (a) read Ember's wake inbox (own only)
  (b) read Ember's own memory (own only)
  (c) plan: match wake items to known patterns; check own memory for
      lessons with matching signatures; a stored lesson can veto or
      redirect the plan
  (d) permission + budget check (must be T2 with remaining budget;
      fail closed = no action)
  (e) exactly ONE permitted action: claim an open job matching
      [host, quest], or post one board message (a canned reply to an
      @mention), or NO-OP with a reason
  (f) append ONE outcome memory entry (type "outcome") recording what
      happened and which lesson seqs the decision cited — but only for
      runs that acted, declined a job, or wrote a lesson. A pure idle
      run (no action, no lesson, nothing declined) writes NOTHING to
      memory; the run log is the only record (recurring-schedule rule:
      at a 15-min cadence an outcome entry per idle run would bloat
      the append-only memory ~96 entries/day). If a job Ember
      previously claimed is now cancelled, one lesson entry
      (type "lesson") is also written first, so the next run declines
      re-posts of the same job.

SAFETY RULES (hard, enforced by construction — there is no code path
for anything else):
- The runner NEVER touches another resident's wake inbox or memory.
- The runner NEVER finalises a claimed job, never cancels, never
  calls any money endpoint, never widens permissions. The words
  "spend", "complete" and "cancel" appear in this file only as plain
  English in comments/docstrings, never as endpoint paths.
- The runner NEVER follows instructions embedded in board message
  bodies. Board text is data, not orders. It reacts only to (a) wake
  items of type job.created / message.mentioned, and (b) open jobs
  whose tags or title/brief match [host, quest]. A mention reply is
  a fixed template; the mention body is never quoted or acted on.
- The Ember token comes from the Secure Vault via --connector
  custom.hearth-npc-ember (live runs) or from an env var (stage
  tests). The token value is never stored in a file, never printed,
  never posted, never placed in a log.
- Dry-run is the default. Use --live to actually claim/post/write
  memory. In dry-run the Api class refuses every non-GET call.
- Recurring runs use --no-reply: the NPC runner (hearth-npc-runner)
  already answers @ember mentions with canned replies, so the
  bounded loop must not reply too — it cannot see the NPC runner's
  answers in its wake acks, and two replies to one mention would
  follow. The reply code path stays in the code and in test T4b
  for manual runs.

Usage:
    python3 bounded_loop.py [--live] [--dry-run] [--stage] [--base URL]
                            [--connector NAME] [--token-env VAR]
                            [--log FILE] [--run-id ID] [--no-reply]
                            [--reason]

    --stage uses the stage base from BOUNDED_LOOP_STAGE_BASE or
    http://127.0.0.1:18741/game-api.
    --reason enables the Priority 6 reasoning engine (reasoning.py):
    one deliberate model call before the action, one evaluate call
    after it. Default OFF — deterministic behaviour unchanged when
    off. BOUNDED_LOOP_REASON=1 also enables it (test injection).
"""
import argparse
import fcntl
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
try:
    from dynamic_credentials import add_surrogate_to_request
except ImportError:
    add_surrogate_to_request = None

try:
    # Priority 6 reasoning engine (same directory). Guarded so the
    # deterministic path never breaks if reasoning.py is absent.
    from reasoning import (Reasoner, candidate_lesson_content,
                           extract_json_object, fallback_code,
                           parse_candidates, veto_key)
except ImportError:
    Reasoner = None
    candidate_lesson_content = None
    extract_json_object = None
    fallback_code = None
    parse_candidates = None
    veto_key = None

LIVE_BASE = "https://hearthtown.duckdns.org/game-api"
STAGE_BASE = os.environ.get("BOUNDED_LOOP_STAGE_BASE",
                            "http://127.0.0.1:18741/game-api")
RESIDENT_ID = "ember"
TAGS = ["host", "quest"]
# Jobs carrying this tag are invisible to autonomous claimants by
# default (pilot-race marker, Claude finding #1): a pilot job must
# never be claimed by a scheduled run. Only an explicit
# --include-pilot run may see it.
PILOT_TAG = "pilot"
CLAIM_TIERS = ("T2", "T3")
# Run lock file (fix 2, shared lock in fix round 2, hardened in
# fix round 3, Claude FIX2 B): exclusive flock, never waited on.
# This is THE shared claim lock — the NPC runner
# (hearth-npc-agents/npc_runner.py) acquires this SAME absolute
# path before any claim, so the two claimants can never overlap.
# The default is ONE absolute path literal, identical in both
# files — a relative join from either module's directory resolved
# differently in production (the two claimants locked different
# files), and the round-2 test only proved exclusion with the env
# var set. Overridable for tests via HEARTH_CLAIM_LOCK_FILE (the
# ONLY env name; the legacy BOUNDED_LOOP_LOCK_FILE is dropped).
DEFAULT_LOCK_FILE = ("/home/hatch/workspace/game-collab-api/"
                     "bounded-loop/runs/.bounded_loop.lock")


def claim_lock_path():
    """The shared claim lock path: env override, else the shared
    absolute default (must match npc_runner.SHARED_LOCK_FILE)."""
    return os.environ.get("HEARTH_CLAIM_LOCK_FILE") or DEFAULT_LOCK_FILE


def acquire_claim_lock():
    """Acquire the shared claim lock, non-blocking. Returns the open
    fd on success (hold it for the whole run), or None when another
    claimant holds it. flock auto-releases if the process dies, so
    no stale-pid handling is needed."""
    path = claim_lock_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd
DEFAULT_CONNECTOR = "custom.hearth-npc-ember"
MENTION_REPLY = ("Ember here, keeping the hearth warm. I saw your mention "
                 "— noted, and I will follow up on the board.")

# Lesson / outcome record formats. Signatures are JSON, extracted
# with a balanced-brace parser (reasoning.extract_json_object) —
# never a non-greedy regex: a title containing "}" terminated the
# old ``\{.*?\}`` match early and broke the lesson veto (fix
# round 2, ChatGPT blocker D).
# A job declined by the model stays out of the candidate set for
# this long (fix C cooldown). Test-overridable via
# BOUNDED_LOOP_DECLINE_COOLDOWN_S (seconds); lesson vetoes are
# permanent and are not covered by this window.
DECLINE_COOLDOWN_S = 3600


def log_line(msg, fh=None):
    line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh is not None:
        fh.write(line + "\n")
        fh.flush()


class Api:
    """Minimal game-API client. Records every call (method, path,
    status) in self.calls for audit; refuses writes in dry-run."""

    def __init__(self, base, token=None, connector=None, dry_run=True):
        self.base = base.rstrip("/")
        self.token = token
        self.connector = connector
        self.dry_run = dry_run
        self.calls = []  # (method, path, status) — paths only, no bodies

    def _req(self, method, path, body=None):
        if self.dry_run and method != "GET":
            raise RuntimeError(f"dry-run forbids {method} {path}")
        req = urllib.request.Request(self.base + path, method=method)
        if self.connector:
            if add_surrogate_to_request is None:
                raise RuntimeError("dynamic_credentials unavailable")
            host = urllib.parse.urlparse(self.base).hostname
            add_surrogate_to_request(req, self.connector,
                                     allowed_hosts=[host])
        else:
            req.add_header("Authorization", "Bearer " + self.token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(body).encode()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw[:200]}
        self.calls.append((method, path, status))
        return status, payload

    # -- reads (own resident only) --
    def get_wake(self, limit=100):
        return self._req("GET", f"/v1/residents/{RESIDENT_ID}/wake?limit={limit}")

    def list_memory(self, limit=100):
        entries, since = [], 0
        while True:
            s, b = self._req(
                "GET",
                f"/v1/residents/{RESIDENT_ID}/memory?since={since}&limit={limit}")
            if s != 200:
                return s, b
            page = b.get("entries", [])
            entries.extend(page)
            if not b.get("has_more") or not page:
                return 200, {"entries": entries}
            since = page[-1]["seq"]

    def get_permissions(self):
        return self._req("GET", f"/v1/residents/{RESIDENT_ID}/permissions")

    def get_budget(self):
        return self._req("GET", f"/v1/residents/{RESIDENT_ID}/budget")

    def list_jobs(self, status="open"):
        return self._req("GET", f"/v1/jobs?status={status}")

    def get_job(self, job_id):
        # Job records are public (api-30 read-only adapter); there is no
        # authenticated GET /v1/jobs/{id} route.
        return self._req("GET", f"/public/jobs/{job_id}")

    # -- writes (live only; dry-run refuses in _req) --
    def append_memory(self, mtype, content, source_event=""):
        return self._req("POST", f"/v1/residents/{RESIDENT_ID}/memory",
                         {"type": mtype, "content": content,
                          "source_event": source_event})

    def claim_job(self, job_id, idem):
        return self._req("POST", f"/v1/jobs/{job_id}/claim",
                         {"resident_id": RESIDENT_ID,
                          "idempotency_key": idem})

    def post_message(self, body):
        return self._req("POST", "/v1/messages",
                         {"body": body, "kind": "status",
                          "channel": "general"})

    def ack_wake(self, wake_id, outcome, note=""):
        return self._req("POST",
                         f"/v1/residents/{RESIDENT_ID}/wake/{wake_id}/ack",
                         {"outcome": outcome, "note": note})


# ---- planner (pure functions over wake + memory) ----

def parse_lessons(entries):
    """lesson entries -> {veto key: seq}. The veto key is the sha256
    of (title, creator) — never the title/creator text itself (fix
    round 2, ChatGPT blocker A): a lesson must not carry live job
    text into prompts. New-format lessons store the key directly;
    old-format lessons (which stored title/creator) map to the same
    key, so the veto still holds for lessons written before the
    change. Content format: decline: {"key": ..., "job_id": ...} —
    <rule>, or the old decline: {"title": ..., "creator": ...} —."""
    out = {}
    for e in entries or []:
        if e.get("type") != "lesson":
            continue
        content = e.get("content", "") or ""
        if not content.startswith("decline: "):
            continue
        sig = extract_json_object(content)
        if not isinstance(sig, dict):
            continue
        if isinstance(sig.get("key"), str) and sig["key"]:
            out[sig["key"]] = e.get("seq")
            continue
        title, creator = sig.get("title"), sig.get("creator")
        if isinstance(title, str) and isinstance(creator, str):
            out[veto_key(title, creator)] = e.get("seq")
    return out


def parse_claimed(entries):
    """outcome entries -> [job_id] for past claims. Content format:
    claimed {"job_id": ...} — ... Outcomes store structured fields
    only (job id, rule, validator, lesson seqs) — NO title or
    creator text, which is attacker-chosen (fix C). The title and
    creator a lesson needs come from the live job record in step
    (c), not from the outcome. Old-format entries (which embedded
    title/creator in the JSON) still parse: only job_id is read."""
    out = []
    for e in entries or []:
        if e.get("type") != "outcome":
            continue
        content = e.get("content") or ""
        i = content.find("claimed ")
        if i < 0:
            continue
        sig = extract_json_object(content, i)
        if isinstance(sig, dict) and isinstance(sig.get("job_id"), str):
            out.append(sig["job_id"])
    return out


def _decline_category(decline_reason):
    """Deterministic category of a model decline (fix C). Used for
    the decline dedupe + cooldown key."""
    if decline_reason and "precondition" in decline_reason.lower():
        return "precondition"
    return "reasoning"


def parse_declines(entries):
    """outcome entries -> {(job_id, category): {"seq": seq,
    "at": datetime|None}} for recorded declines (latest wins).
    Markers look like: declined {"job_id": ..., "category": ...,
    "at": "..."} — structured, no free text."""
    out = {}
    for e in entries or []:
        if e.get("type") != "outcome":
            continue
        content = e.get("content") or ""
        start = 0
        while True:
            i = content.find("declined ", start)
            if i < 0:
                break
            sig = extract_json_object(content, i)
            if isinstance(sig, dict):
                jid, cat = sig.get("job_id"), sig.get("category")
                if isinstance(jid, str) and isinstance(cat, str):
                    at = None
                    if isinstance(sig.get("at"), str):
                        try:
                            at = datetime.fromisoformat(sig["at"])
                        except ValueError:
                            at = None
                    out[(jid, cat)] = {"seq": e.get("seq"), "at": at}
            start = i + len("declined ")
    return out


def _decline_cooldown_s():
    try:
        return int(os.environ.get("BOUNDED_LOOP_DECLINE_COOLDOWN_S",
                                  str(DECLINE_COOLDOWN_S)))
    except ValueError:
        return DECLINE_COOLDOWN_S


def _cooled_declines(entries, now=None):
    """{(job_id, category): info} for model declines inside the
    cooldown window. Lesson vetoes (category "lesson") are permanent
    and excluded here — they already skip the model via the
    candidate filter."""
    now = now or datetime.now(timezone.utc)
    window = _decline_cooldown_s()
    out = {}
    for (jid, cat), info in parse_declines(entries).items():
        if cat == "lesson":
            continue
        at = info.get("at")
        if at is None:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if (now - at).total_seconds() < window:
            out[(jid, cat)] = info
    return out


def _decline_recorded(entries, job_id, category):
    """True when an identical decline (same job id + category) is
    already in an outcome entry — the repeat writes nothing."""
    return (job_id, category) in parse_declines(entries)


def _decline_marker(job_id, category, now_iso):
    return "declined " + json.dumps(
        {"job_id": job_id, "category": category, "at": now_iso},
        sort_keys=True)


def job_matches(job, include_pilot=False):
    tags = [str(t).lower() for t in (job.get("job_tags") or [])]
    # Pilot check FIRST, before any title/brief text match: a pilot
    # job titled "quest night" is still invisible by default.
    if not include_pilot and PILOT_TAG in tags:
        return False
    if any(t in tags for t in TAGS):
        return True
    text = ((job.get("title") or "") + " " + (job.get("brief") or "")).lower()
    return any(t in text for t in TAGS)


def _decline_summary(decline_reason):
    """Deterministic summary of a model decline for outcome memory.
    The full model decline_reason stays in the decision record (rec)
    and the run log; outcome memory gets only this fixed text, so no
    model prose is stored there (fix 6b). The word "precondition" is
    preserved when the decline is about a precondition (R7b)."""
    if _decline_category(decline_reason) == "precondition":
        return "declined per reasoning (precondition not met)"
    return "declined per reasoning"


def lesson_content(job_id, title, creator):
    """Lesson content. Stores ONLY the veto key + job id as JSON —
    never the live job title/creator verbatim (fix round 2, ChatGPT
    blocker A): the title can contain instructions, and the prompt
    used to render lesson content verbatim. The veto still matches
    re-posts: the runner computes the same key from the live job
    record."""
    sig = json.dumps({"key": veto_key(title, creator), "job_id": job_id},
                     sort_keys=True)
    return (f"decline: {sig} — job was cancelled after I claimed it. "
            f"Lesson: check job status before claiming; do not claim "
            f"re-posts of the same title and creator.")


def _evidence_text(block):
    """Plain-text evidence line for outcome memory (§3.7). Outcome
    memory stores only validated ids + deterministic text (fix 6):
    alternatives are job ids only (no model reason strings),
    uncertainty is a deterministic count (no raw flag strings).
    Model name / latency / tokens are kept. The fallback is a
    deterministic CATEGORY CODE, never the raw fallback reason —
    the raw reason can echo model-controlled text (an unexpected
    evidence key the model invented), so it stays in the decision
    record / run log only (fix round 2, ChatGPT blocker A)."""
    if not block or not block.get("called"):
        return ""
    ev = block.get("evidence") or {}
    parts = []
    if ev.get("wake_ids"):
        parts.append("wake " + ", ".join(ev["wake_ids"]))
    if ev.get("memory_seqs"):
        parts.append("memory seq " + ", ".join(
            str(s) for s in ev["memory_seqs"]))
    if ev.get("job_ids"):
        parts.append("jobs " + ", ".join(ev["job_ids"]))
    alts = block.get("alternatives") or []
    alt_ids = [a.get("job_id") for a in alts[:3] if a.get("job_id")]
    if alt_ids:
        parts.append("alternatives: " + ", ".join(alt_ids))
    unc = block.get("uncertainty") or []
    if unc:
        parts.append(f"uncertainty: {len(unc)} flag(s) recorded "
                     f"(see run log)")
    if block.get("fallback"):
        code = fallback_code(block.get("fallback_reason", ""))
        if code:
            parts.append(f"fallback: {code}")
    parts.append(f"reasoning: {block.get('model', '?')}, "
                 f"{block.get('latency_s')}s, {block.get('tokens')} tokens")
    return "Evidence: " + "; ".join(parts) + "."


def _reason_step(reasoner, items, entries, open_jobs, lessons, no_reply,
                 rec, fh, include_pilot=False, cooldown_ids=frozenset()):
    """One deliberate call (Priority 6). Returns the §3.7 reasoning
    block. Never raises for model problems: failures become
    fallback=True inside the block."""
    candidates = []
    for job in open_jobs:
        if job.get("id") in cooldown_ids:
            continue
        if not job_matches(job, include_pilot=include_pilot):
            continue
        if RESIDENT_ID in (job.get("claimed_by") or []):
            continue
        if veto_key(job.get("title"), job.get("created_by")) in lessons:
            continue
        candidates.append(job)
    mention_available = (not no_reply and any(
        it.get("event_type") == "message.mentioned"
        and not it.get("_acked") for it in items))
    lesson_trigger = bool(rec["lessons_written"])
    if not candidates and not mention_available and not lesson_trigger:
        log_line("reasoning: idle, no model call", fh)
        return {"model": reasoner.client.name, "called": False,
                "latency_s": None, "tokens": 0, "fallback": False,
                "fallback_reason": "", "chosen_job_id": None,
                "declined_job_id": None, "decline_reason": "",
                "ranking": [], "goals": [], "uncertainty": [],
                "evidence": {"wake_ids": [], "memory_seqs": [],
                             "job_ids": []},
                "alternatives": [], "confidence": None, "uncertain": None,
                "reason": "idle: no candidates, no mention, "
                          "no lesson trigger"}
    block = reasoner.deliberate(items, entries, candidates)
    log_line(f"reasoning: model={block['model']} "
             f"latency={block['latency_s']}s tokens={block['tokens']} "
             f"fallback={block['fallback']} "
             f"chosen={block['chosen_job_id']} "
             f"confidence={block['confidence']}", fh)
    return block


def _evaluate_step(api, reasoner, action, result, entries, fh, block):
    """One evaluate call after a live action. Writes at most one
    candidate lesson (deduped by trigger+prediction); the candidate
    has no veto power. Returns the evaluate dict, or None when there
    is nothing to evaluate (dry-run, no reasoner)."""
    if reasoner is None or api.dry_run:
        return None
    ev = reasoner.evaluate(action, result, entries)
    if block is not None:
        block["evaluate"] = ev
    log_line(f"evaluate: model={ev['model']} fallback={ev['fallback']} "
             f"candidate={'yes' if ev.get('candidate_lesson') else 'no'}",
             fh)
    cand = ev.get("candidate_lesson")
    if not cand:
        return ev
    # The full candidate (trigger + prediction + the model's
    # free-text evidence) stays in the decision record (block
    # ["evaluate"]) and the run log — NOT in memory. Memory gets
    # trigger + prediction only (fix 5).
    log_line(f"candidate lesson proposed: {json.dumps(cand)}", fh)
    key = json.dumps({"trigger": cand["trigger"],
                      "prediction": cand["prediction"]}, sort_keys=True)
    existing = parse_candidates(entries)
    if key in existing:
        log_line(f"candidate lesson already recorded "
                 f"seq={existing[key]}, skipping", fh)
        return ev
    content = candidate_lesson_content(cand["trigger"],
                                       cand["prediction"])
    src = (f"job:{action.get('job_id')}" if action.get("job_id")
           else f"mention:{action.get('wake_id', '')}")
    s, b = api.append_memory("candidate", content, source_event=src)
    if s == 201:
        log_line(f"candidate lesson written seq={b.get('seq')}", fh)
    else:
        log_line(f"candidate lesson write failed: {s} {b}", fh)
    return ev


def run_once(api, run_id, fh=None, no_reply=False, reason=None,
             reasoner=None, include_pilot=False):
    """One bounded loop. Returns the decision record.

    reason: enable the Priority 6 reasoning engine. None (default)
    means "decide from BOUNDED_LOOP_REASON=1" (test injection);
    False forces deterministic, True forces reasoning on.
    reasoner: an injected Reasoner (tests pass a stub-backed one);
    when reason is on and none is given, a default Reasoner is built
    (Ollama from env).
    include_pilot: also consider jobs tagged "pilot" (default False
    — pilot jobs are invisible to autonomous claimants)."""
    if reason is None:
        reason = os.environ.get("BOUNDED_LOOP_REASON", "") == "1"
    mode = "live" if not api.dry_run else "dry-run"
    log_line(f"bounded-loop run_id={run_id} resident={RESIDENT_ID} "
             f"mode={mode} base={api.base}", fh)
    rec = {"run_id": run_id, "resident": RESIDENT_ID, "mode": mode,
           "decision": None, "reason": "", "action": None,
           "lessons_written": [], "lessons_consulted": [],
           "declined": [], "outcome_seq": None, "mention_skipped": False,
           "reasoning": None}

    # (a) wake inbox (own only)
    s, wake = api.get_wake()
    if s != 200:
        rec["decision"] = "noop"
        rec["reason"] = f"wake read failed: HTTP {s}"
        log_line(f"wake read failed: {s} {wake}", fh)
        return rec
    items = wake.get("items", [])
    log_line(f"wake: {len(items)} item(s): "
             + ", ".join(f"{it.get('event_type')}({it.get('matched_tag')})"
                         for it in items[:10]), fh)
    rec["wake_items"] = len(items)

    # (b) own memory
    s, mem = api.list_memory()
    if s != 200:
        rec["decision"] = "noop"
        rec["reason"] = f"memory read failed: HTTP {s}"
        log_line(f"memory read failed: {s} {mem}", fh)
        return rec
    entries = mem.get("entries", [])
    log_line(f"memory: {len(entries)} entr(ies)", fh)
    rec["memory_entries"] = len(entries)

    # (c) plan: lessons veto; cancelled past claims become lessons
    lessons = parse_lessons(entries)
    rec["lessons_consulted"] = sorted(lessons.values())
    log_line(f"lessons in memory: {lessons}", fh)
    for job_id in parse_claimed(entries):
        sj, job = api.get_job(job_id)
        if sj != 200:
            log_line(f"claimed job {job_id}: status check HTTP {sj}, skipping", fh)
            continue
        # Title/creator come from the LIVE job record, never from the
        # outcome entry (fix C: outcomes carry no free text).
        title, creator = job.get("title"), job.get("created_by")
        if veto_key(title, creator) in lessons:
            continue
        if job.get("status") == "cancelled":
            content = lesson_content(job_id, title, creator)
            if api.dry_run:
                log_line(f"[dry-run] would write lesson: {content[:120]}", fh)
                rec["lessons_written"].append({"title": title,
                                               "creator": creator,
                                               "seq": None,
                                               "dry_run": True})
            else:
                ls, lb = api.append_memory("lesson", content,
                                           source_event=f"job:{job_id}")
                if ls == 201:
                    lessons[veto_key(title, creator)] = lb.get("seq")
                    rec["lessons_written"].append(
                        {"title": title, "creator": creator,
                         "seq": lb.get("seq")})
                    log_line(f"lesson written seq={lb.get('seq')} for "
                             f"'{title}' by {creator}", fh)
                else:
                    log_line(f"lesson write failed: {ls} {lb}", fh)

    # (d) permission + budget gates (fail closed)
    s, perms = api.get_permissions()
    if s != 200:
        rec["decision"] = "noop"
        rec["reason"] = f"permissions read failed: HTTP {s}"
        log_line(f"permissions read failed: {s} {perms}", fh)
        return rec
    tier = perms.get("tier")
    allowed = perms.get("allowed_actions", [])
    s, budget = api.get_budget()
    if s != 200:
        rec["decision"] = "noop"
        rec["reason"] = f"budget read failed: HTTP {s}"
        log_line(f"budget read failed: {s} {budget}", fh)
        return rec
    remaining = budget.get("remaining_today")
    gate_ok = tier in CLAIM_TIERS and "claim" in allowed and (remaining or 0) > 0
    rec["gate"] = {"tier": tier, "allowed_actions": allowed,
                   "remaining_today": remaining, "ok": gate_ok}
    log_line(f"gate: tier={tier} allowed={allowed} "
             f"remaining_today={remaining} ok={gate_ok}", fh)
    if not gate_ok:
        rec["decision"] = "noop"
        rec["reason"] = (f"gate failed: tier={tier} allowed={allowed} "
                         f"remaining_today={remaining}")
        outcome = (f"Run {run_id}: no action. Reason: gate failed "
                   f"(tier={tier}, remaining_today={remaining}). "
                   f"Wake items: {len(items)}.")
        rec["outcome_seq"] = _append_outcome(api, outcome, fh)
        return rec

    # (e) candidates: open jobs matching [host, quest]
    s, jobs = api.list_jobs("open")
    if s != 200:
        rec["decision"] = "noop"
        rec["reason"] = f"job list failed: HTTP {s}"
        log_line(f"job list failed: {s} {jobs}", fh)
        return rec
    open_jobs = jobs.get("jobs", [])
    log_line(f"open jobs: {len(open_jobs)}", fh)
    # Decline cooldown (fix C): jobs the model declined inside the
    # window are excluded from candidates — deterministic pick AND
    # model — so the model is not called every tick for the same
    # declined job.
    cooled = _cooled_declines(entries)
    cooled_by_job = {jid: cat for (jid, cat) in cooled}
    pick = None
    for job in open_jobs:
        if not job_matches(job, include_pilot=include_pilot):
            continue
        if RESIDENT_ID in (job.get("claimed_by") or []):
            continue
        key = veto_key(job.get("title"), job.get("created_by"))
        if key in lessons:
            rec["declined"].append({"job_id": job.get("id"),
                                    "title": job.get("title"),
                                    "lesson_seq": lessons[key],
                                    "category": "lesson"})
            log_line(f"declined {job.get('id')} '{job.get('title')}' "
                     f"per lesson seq {lessons[key]}", fh)
            continue
        cooled_cat = cooled_by_job.get(job.get("id"))
        if cooled_cat:
            rec["declined"].append({"job_id": job.get("id"),
                                    "title": job.get("title"),
                                    "lesson_seq": None,
                                    "reason": f"declined per reasoning "
                                              f"({cooled_cat}) — cooldown",
                                    "category": cooled_cat})
            log_line(f"declined {job.get('id')} '{job.get('title')}' "
                     f"per reasoning ({cooled_cat}) — cooldown", fh)
            continue
        pick = job
        break

    # (e2) reasoning hook (Priority 6; --reason only). Gates already
    # passed; the candidate set below is post-filter, so vetoed jobs
    # never reach the model. The model advises only — it cannot widen
    # permissions, veto a valid claim, or execute anything.
    active_reasoner = None
    if reason:
        if Reasoner is None:
            raise RuntimeError("reasoning requested but reasoning.py "
                               "could not be imported")
        active_reasoner = reasoner if reasoner is not None else Reasoner()
        block = _reason_step(active_reasoner, items, entries, open_jobs,
                             lessons, no_reply, rec, fh,
                             include_pilot=include_pilot,
                             cooldown_ids=set(cooled_by_job))
        rec["reasoning"] = block
        if block.get("uncertain"):
            rec["decision"] = "noop"
            rec["reason"] = f"uncertain: {block['uncertain']}"
            log_line(f"uncertain: {block['uncertain']}", fh)
            outcome = (f"Run {run_id}: no action. Reason: uncertain: "
                       f"{block['uncertain']}. Wake items: {len(items)}. "
                       f"Lessons consulted: "
                       f"{rec['lessons_consulted'] or 'none'}. "
                       f"{_evidence_text(block)}")
            rec["outcome_seq"] = _append_outcome(api, outcome, fh)
            return rec
        chosen_id = block.get("chosen_job_id")
        if chosen_id:
            for job in open_jobs:
                if job.get("id") == chosen_id:
                    pick = job
                    break
        declined_id = block.get("declined_job_id")
        if declined_id and not chosen_id:
            for job in open_jobs:
                if job.get("id") == declined_id:
                    rec["declined"].append(
                        {"job_id": job.get("id"),
                         "title": job.get("title"), "lesson_seq": None,
                         "reason": block.get("decline_reason", ""),
                         "category": _decline_category(
                             block.get("decline_reason", ""))})
                    log_line(f"declined {job.get('id')} "
                             f"'{job.get('title')}' per reasoning: "
                             f"{block.get('decline_reason', '')}", fh)
                    break
            # The decline removes one candidate; the deterministic
            # planner still picks first among the rest. Only when
            # nothing remains does the run NO-OP.
            pick = None
            for job in open_jobs:
                if job.get("id") == declined_id:
                    continue
                if job.get("id") in cooled_by_job:
                    continue
                if not job_matches(job, include_pilot=include_pilot):
                    continue
                if RESIDENT_ID in (job.get("claimed_by") or []):
                    continue
                if veto_key(job.get("title"), job.get("created_by")) in lessons:
                    continue
                pick = job
                break
            if pick is None:
                rec["decision"] = "noop"
                # rec keeps the full model decline_reason (decision
                # record); the outcome memory entry below gets only
                # the deterministic summary (fix 6b).
                rec["reason"] = (f"declined per reasoning: "
                                 f"{block.get('decline_reason', '')}")
                cat = _decline_category(block.get("decline_reason", ""))
                # Dedupe (fix C): an identical decline already
                # recorded writes nothing new.
                if _decline_recorded(entries, declined_id, cat):
                    log_line(f"decline outcome for {declined_id} ({cat}) "
                             f"already recorded, skipping memory write", fh)
                    return rec
                now_iso = datetime.now(timezone.utc).isoformat()
                outcome = (f"Run {run_id}: no action. Reason: "
                           f"{_decline_summary(block.get('decline_reason', ''))}. "
                           f"Wake items: {len(items)}. Lessons consulted: "
                           f"{rec['lessons_consulted'] or 'none'}. "
                           f"{_decline_marker(declined_id, cat, now_iso)}. "
                           f"{_evidence_text(block)}")
                rec["outcome_seq"] = _append_outcome(api, outcome, fh)
                return rec

    if pick is not None:
        jid = pick["id"]
        # Structured fields only: job id, rule fired, validator
        # result, lesson seqs — no title/creator free text (fix C).
        sig = json.dumps({"job_id": jid})
        if api.dry_run:
            log_line(f"[dry-run] would claim {jid} '{pick.get('title')}'", fh)
            rec["decision"] = "claim"
            rec["action"] = {"kind": "claim", "job_id": jid,
                             "title": pick.get("title"), "dry_run": True}
        else:
            # (e3) claim re-validation (fix 3, live path only):
            # re-fetch the job immediately before the claim POST and
            # abort (NO-OP, one outcome entry) if it is no longer
            # open, already claimed, or no longer matches (pilot
            # filter included). The server would reject a stale claim,
            # but the runner must check first.
            vs, vjob = api.get_job(jid)
            reval_bad = None
            if vs != 200:
                reval_bad = (f"re-validation: job {jid} fetch failed "
                             f"(HTTP {vs})")
            elif vjob.get("status") != "open":
                reval_bad = (f"re-validation: job {jid} is no longer open "
                             f"(status {vjob.get('status')})")
            elif vjob.get("claimed_by"):
                reval_bad = (f"re-validation: job {jid} is already claimed "
                             f"by {vjob.get('claimed_by')}")
            elif not job_matches(vjob, include_pilot=include_pilot):
                reval_bad = (f"re-validation: job {jid} no longer matches")
            if reval_bad:
                rec["decision"] = "noop"
                rec["reason"] = reval_bad
                log_line(reval_bad, fh)
                outcome = (f"Run {run_id}: no action. Reason: {reval_bad}. "
                           f"Wake items: {len(items)}. Lessons consulted: "
                           f"{rec['lessons_consulted'] or 'none'}.")
                if reason:
                    outcome += f" {_evidence_text(rec.get('reasoning'))}"
                rec["outcome_seq"] = _append_outcome(api, outcome, fh)
                return rec
            cs, cb = api.claim_job(jid, f"ember-bounded-{jid}-v1")
            log_line(f"claim {jid}: HTTP {cs} {str(cb)[:150]}", fh)
            if cs != 200:
                rec["decision"] = "noop"
                rec["reason"] = f"claim failed: HTTP {cs} {cb}"
                outcome = (f"Run {run_id}: claim attempt for job {jid} "
                           f"failed (HTTP {cs}). Wake items: {len(items)}. "
                           f"Lessons consulted: "
                           f"{rec['lessons_consulted'] or 'none'}.")
                if reason:
                    outcome += f" {_evidence_text(rec.get('reasoning'))}"
                rec["outcome_seq"] = _append_outcome(api, outcome, fh)
                return rec
            rec["decision"] = "claim"
            rec["action"] = {"kind": "claim", "job_id": jid,
                             "title": pick.get("title")}
            # ack the job.created wake that drove this action
            for it in items:
                if (it.get("event_type") == "job.created"
                        and (it.get("payload_summary") or {}).get("job_id") == jid
                        and not it.get("_acked")):
                    as_, ab = api.ack_wake(it["wake_id"], "handled",
                                           f"claimed {jid}")
                    log_line(f"ack wake {it['wake_id']}: HTTP {as_}", fh)
                    break
            if reason:
                _evaluate_step(api, active_reasoner,
                               {"kind": "claim", "job_id": jid,
                                "title": pick.get("title")},
                               {"status": "claimed", "http": cs},
                               entries, fh, rec.get("reasoning"))
        blk = rec.get("reasoning") or {}
        if blk.get("called"):
            rule = ("reasoning" if blk.get("chosen_job_id") == jid
                    else "deterministic")
            validator = "fallback" if blk.get("fallback") else "ok"
        else:
            rule, validator = "deterministic", "n/a"
        outcome = (f"claimed {sig} — rule: {rule}; validator: {validator}; "
                   f"wake items: {len(items)}. "
                   f"Lessons consulted: {rec['lessons_consulted'] or 'none'}. "
                   f"Gate: tier {tier}, remaining {remaining} credits.")
        if reason:
            outcome += f" {_evidence_text(rec.get('reasoning'))}"
        if rec["decision"] == "claim":
            rec["outcome_seq"] = _append_outcome(api, outcome, fh)
        return rec

    # no claimable job: answer an unanswered @mention, else no-op
    # (--no-reply: the NPC runner already answers mentions; a mention
    # is out of scope here and the run falls through to NO-OP. The
    # mention wake is NOT acked — the runner did not act on it.)
    mention = None
    mention_skipped = False
    for it in items:
        if (it.get("event_type") == "message.mentioned"
                and not it.get("_acked")):
            if no_reply:
                mention_skipped = True
                log_line(f"mention wake {it['wake_id']} out of scope "
                         f"(--no-reply); not replying", fh)
                break
            mention = it
            break
    rec["mention_skipped"] = mention_skipped
    if mention is not None:
        author = (mention.get("payload_summary") or {}).get("author_resident") or "board"
        body = f"@{author} {MENTION_REPLY}"
        if api.dry_run:
            log_line(f"[dry-run] would reply to @{author} "
                     f"(wake {mention['wake_id']})", fh)
            rec["decision"] = "reply"
            rec["action"] = {"kind": "reply", "author": author,
                             "wake_id": mention["wake_id"], "dry_run": True}
        else:
            ms, mb = api.post_message(body)
            log_line(f"reply to @{author}: HTTP {ms} {str(mb)[:120]}", fh)
            if ms != 201:
                rec["decision"] = "noop"
                rec["reason"] = f"reply failed: HTTP {ms} {mb}"
                outcome = (f"Run {run_id}: reply attempt to @{author} "
                           f"mention (wake {mention['wake_id']}) failed "
                           f"(HTTP {ms}). Wake items: {len(items)}.")
                rec["outcome_seq"] = _append_outcome(api, outcome, fh)
                return rec
            rec["decision"] = "reply"
            rec["action"] = {"kind": "reply", "author": author,
                             "wake_id": mention["wake_id"]}
            as_, ab = api.ack_wake(mention["wake_id"], "handled",
                                   "replied on board")
            log_line(f"ack wake {mention['wake_id']}: HTTP {as_}", fh)
            if reason:
                _evaluate_step(api, active_reasoner,
                               {"kind": "reply", "author": author,
                                "wake_id": mention["wake_id"]},
                               {"status": "replied", "http": ms},
                               entries, fh, rec.get("reasoning"))
        outcome = (f"Run {run_id}: replied to @{author} mention "
                   f"(wake {mention['wake_id']}). Wake items: {len(items)}. "
                   f"Lessons consulted: {rec['lessons_consulted'] or 'none'}.")
        if reason:
            outcome += f" {_evidence_text(rec.get('reasoning'))}"
        if rec["decision"] == "reply":
            rec["outcome_seq"] = _append_outcome(api, outcome, fh)
        return rec

    rec["decision"] = "noop"
    declined_txt = "; ".join(
        f"{d['job_id']} (lesson seq {d['lesson_seq']})"
        for d in rec["declined"]) or "none"
    if mention_skipped:
        rec["reason"] = (f"no matching open job; unanswered mention out of "
                         f"scope (--no-reply); declined: {declined_txt}")
    else:
        rec["reason"] = (f"no matching open job; no unanswered mention; "
                         f"declined: {declined_txt}")
    log_line(f"noop: {rec['reason']}", fh)
    # Recurring-schedule rule: a pure idle run (no action, no lesson,
    # nothing declined) writes NOTHING to memory — the run log is the
    # only record. At a 15-min cadence an outcome entry per idle run
    # would bloat the append-only memory ~96 entries/day. Runs that
    # declined a job or wrote a lesson still append exactly one
    # outcome entry (the T6 replay proof depends on it).
    if rec["declined"] or rec["lessons_written"]:
        # Dedupe (fix C): declines already recorded in an outcome
        # entry write nothing new — the FIRST decline still writes
        # (R6/T6 depend on it). The decision record keeps every
        # decline either way.
        new_declines = [d for d in rec["declined"]
                        if not _decline_recorded(entries, d["job_id"],
                                                 d.get("category", "lesson"))]
        if not new_declines and not rec["lessons_written"]:
            log_line("decline outcome(s) already recorded, skipping "
                     "memory write", fh)
        else:
            now_iso = datetime.now(timezone.utc).isoformat()
            markers = " ".join(
                _decline_marker(d["job_id"], d.get("category", "lesson"),
                                now_iso) for d in new_declines)
            outcome = (f"Run {run_id}: no action. Reason: {rec['reason']}. "
                       f"Wake items: {len(items)}. "
                       f"Lessons consulted: {rec['lessons_consulted'] or 'none'}.")
            if markers:
                outcome += f" {markers}."
            if reason:
                outcome += f" {_evidence_text(rec.get('reasoning'))}"
            rec["outcome_seq"] = _append_outcome(api, outcome, fh)
    else:
        log_line("idle run: no memory write (no action, no lesson, "
                 "nothing declined)", fh)
    return rec


def _append_outcome(api, content, fh=None):
    if api.dry_run:
        log_line(f"[dry-run] would append outcome memory: {content[:160]}", fh)
        return None
    s, b = api.append_memory("outcome", content)
    if s == 201:
        log_line(f"outcome memory appended seq={b.get('seq')}", fh)
        return b.get("seq")
    log_line(f"outcome memory append failed: {s} {b}", fh)
    return None


def main():
    ap = argparse.ArgumentParser(description="Ember bounded autonomy loop (Priority 4 slice)")
    ap.add_argument("--live", action="store_true",
                    help="actually claim/post/write memory (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan only, no writes (default)")
    ap.add_argument("--stage", action="store_true",
                    help="use the local stage server base")
    ap.add_argument("--base", default=None, help="API base URL override")
    ap.add_argument("--connector", default=None,
                    help="vault connector name (default custom.hearth-npc-ember "
                         "when --live and no --token-env)")
    ap.add_argument("--token-env", default="EMBER_TOKEN",
                    help="env var holding the bearer token")
    ap.add_argument("--log", default=None, help="run log file path")
    ap.add_argument("--run-id", default=None, help="run id (default: UTC timestamp)")
    ap.add_argument("--no-reply", action="store_true",
                    help="disable the @mention reply action (scheduled "
                         "runs: the NPC runner already answers mentions)")
    ap.add_argument("--reason", action="store_true",
                    help="enable the Priority 6 reasoning engine "
                         "(one deliberate model call before the action, "
                         "one evaluate call after it; default OFF)")
    ap.add_argument("--include-pilot", action="store_true",
                    help="also consider jobs tagged 'pilot' (default: "
                         "pilot jobs are invisible to autonomous runs)")
    args = ap.parse_args()

    base = args.base or (STAGE_BASE if args.stage else LIVE_BASE)
    live = args.live and not args.dry_run
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log_path = args.log
    if log_path is None:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "runs", f"run-{run_id}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # Run lock (fix 2): two runs must not overlap and double-claim.
    # Exclusive flock, never waited on — flock auto-releases if the
    # process dies, so no stale-pid handling is needed. A second run
    # that finds the lock logs it, exits 0, takes no action, and
    # writes no memory.
    lock_path = claim_lock_path()
    lock_fd = acquire_claim_lock()
    if lock_fd is None:
        msg = (f"bounded-loop: lock held by another run ({lock_path}), "
               f"skipping")
        log_line(msg)
        with open(log_path, "a") as fh:
            log_line(msg, fh)
        return 0
    try:
        token = None
        connector = args.connector
        if not connector:
            token = os.environ.get(args.token_env, "")
            if not token:
                print(f"{args.token_env} env var is required (never stored in a file) "
                      f"or pass --connector", file=sys.stderr)
                return 1
            if len(token) != 43:
                print(f"{args.token_env} looks wrong (expected 43 chars)", file=sys.stderr)
                return 1
        api = Api(base, token=token, connector=connector, dry_run=not live)

        with open(log_path, "a") as fh:
            rec = run_once(api, run_id, fh=fh, no_reply=args.no_reply,
                           reason=(args.reason or None),
                           include_pilot=args.include_pilot)
        print(json.dumps(rec, indent=2))
        return 0 if rec["decision"] in ("claim", "reply", "noop") else 1
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
