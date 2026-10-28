#!/usr/bin/env python3
"""Meta Model API client via the custom.meta-model-api connector.

The real API key never lives in this file: authd issues an ``hsurr:*``
surrogate that the egress layer swaps for the real credential on approved
requests to api.meta.ai. Transport is curl (this box's Python urllib RSTs
through the egress proxy; curl is reliable).

Usage:
  meta_api.py models
  meta_api.py chat <model> <message> [--max-tokens N] [--temperature T]
"""
import json
import subprocess
import sys

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import dynamic_credential_entry  # noqa: E402

CREDENTIAL = "custom.meta-model-api"
BASE = "https://api.meta.ai/v1"


def _bearer() -> str:
    entry = dynamic_credential_entry(CREDENTIAL, "access_token")
    return str(entry["surrogate"]).strip()


def _curl(method: str, path: str, body: dict | None = None) -> dict:
    cmd = [
        "curl", "-sS", "--max-time", "60",
        "-H", f"Authorization: Bearer {_bearer()}",
        "-H", "Content-Type: application/json",
        "-H", "User-Agent: hearth-brains/1.0",
        "-w", "\n%{http_code}",
        "-X", method,
        f"{BASE}{path}",
    ]
    if body is not None:
        cmd += ["--data", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if out.returncode != 0:
        raise RuntimeError(f"curl failed: {out.stderr.strip()}")
    text, _, code = out.stdout.rpartition("\n")
    try:
        payload = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": text}
    payload["_http"] = int(code)
    return payload


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "models":
        print(json.dumps(_curl("GET", "/models"), indent=2))
        return 0
    if argv[0] == "chat":
        if len(argv) < 3:
            print("usage: meta_api.py chat <model> <message>", file=sys.stderr)
            return 2
        model, message = argv[1], argv[2]
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": message}],
        }
        i = 3
        while i < len(argv):
            if argv[i] == "--max-tokens" and i + 1 < len(argv):
                body["max_tokens"] = int(argv[i + 1])
                i += 2
            elif argv[i] == "--temperature" and i + 1 < len(argv):
                body["temperature"] = float(argv[i + 1])
                i += 2
            elif argv[i] == "--reasoning-effort" and i + 1 < len(argv):
                body["reasoning_effort"] = argv[i + 1]
                i += 2
            else:
                i += 1
        print(json.dumps(_curl("POST", "/chat/completions", body), indent=2))
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
