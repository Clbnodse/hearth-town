#!/usr/bin/env python3
"""Demo bridge swap: exchange musebucks for embers at par (1:1).

Usage: demo-exchange.py --keys ./demo-keys.json --base http://127.0.0.1:8479
       [--amount 25] [--from musebucks] [--to embers]
Prints balances before and after. Used by the hackathon demo script.
"""
import argparse
import json
import subprocess
import sys

sys.path.insert(0, "/home/hatch/workspace/hearth")
from identity import sign_request  # noqa: E402


def call(base, method, path, fields=None, signed=None, endpoint=None):
    if signed is not None:
        fields = sign_request(signed["agent_id"], signed["private_key"],
                              endpoint, **(fields or {}))
    url = base + path
    cmd = ["curl", "-sS", "--max-time", "30",
           "-H", "Content-Type: application/json",
           "-H", "User-Agent: hearth-demo/1.0", "-X", method, url]
    if method == "POST":
        cmd += ["--data", json.dumps(fields or {})]
    elif fields:
        import urllib.parse
        url = base + path + "?" + urllib.parse.urlencode(fields)
        cmd[-1] = url
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"curl failed: {out.stderr.strip()}")
    return json.loads(out.stdout or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True)
    ap.add_argument("--base", default="http://127.0.0.1:8479")
    ap.add_argument("--amount", type=int, default=25)
    ap.add_argument("--from", dest="frm", default="musebucks")
    ap.add_argument("--to", dest="to", default="embers")
    args = ap.parse_args()
    ident = json.loads(open(args.keys).read())
    base = args.base.rstrip("/")
    before = call(base, "GET", "/api/v1/balance", {},
                  signed=ident, endpoint="balance")
    print("before:", before.get("balances"))
    r = call(base, "POST", "/api/v1/exchange",
             {"from_currency": args.frm, "to_currency": args.to,
              "amount": args.amount}, signed=ident, endpoint="exchange")
    print("exchange:", r)
    after = call(base, "GET", "/api/v1/balance", {},
                 signed=ident, endpoint="balance")
    print("after:", after.get("balances"))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
