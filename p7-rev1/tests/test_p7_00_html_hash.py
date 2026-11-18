#!/usr/bin/env python3
"""P7-00 embedded game file hash (extra test, Grok acceptance #8).

The P7 patch must not change the game file: the embedded v26 game
HTML in the patched server is byte-identical to the api-41 stage
(sha256 f27d758d..., 79,828 bytes), the game endpoint still serves
that hash, and only the OpenAPI version moved to api-42.
"""
import hashlib
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
V26_SHA = ("f27d758d054f84d76447a0be993f0605117643db35f7af97d94e753327a37f5b")
V26_BYTES = 79828
PORT = 18918


def load_module(path):
    # server.py imports sibling modules (identity) — its dir must be
    # on sys.path, as the harness does for the draft stage.
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("srv_" + hashlib.sha256(
        path.encode()).hexdigest()[:8], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    api41 = os.path.join(BASE, "stage-v17-game-api41", "server.py")
    # The published rev-1 server (not the v1 DRAFT: rev 1 added the
    # run-policy route, so the OpenAPI path count is 63, not 62).
    api42 = os.path.join(BASE, "priority7", "revision", "work",
                         "stage-v17-game-api42-REV", "server.py")
    mod41 = load_module(api41)
    mod42 = load_module(api42)
    html41 = mod41._GAME_V2_HTML
    html42 = mod42._GAME_V2_HTML
    assert html41 == html42, "embedded game HTML differs between stages"
    sha = hashlib.sha256(html42.encode()).hexdigest()
    assert sha == V26_SHA, sha
    assert len(html42.encode()) == V26_BYTES, len(html42.encode())
    print(f"  embedded game HTML identical to api-41: sha {sha[:16]}..., "
          f"{V26_BYTES} bytes (v26)")
    # OpenAPI (in-module doc): version moved to api-42, 63 paths, no
    # api-41 string remains.
    oa = mod42._GAME_API_OPENAPI
    assert oa["info"]["version"] == "20261114-game-api-42", oa["info"]
    assert len(oa["paths"]) == 63, len(oa["paths"])
    assert "20261114-game-api-41" not in json.dumps(oa), \
        "api-41 string remains in OpenAPI doc"
    print("  OpenAPI version api-42, 63 paths, no api-41 string")
    h = Harness("p7_00", PORT).start()
    try:
        h.clear_rates()
        s, b = h.call("GET", "/v1/game-v2-source")
        assert s == 200, (s, b)
        assert b.get("sha256") == V26_SHA, b
        assert b.get("size_bytes") == V26_BYTES, b
        assert hashlib.sha256(b["source"].encode()).hexdigest() == V26_SHA
        print("  served game source == v26 sha")
        print("P7-00 HTML hash: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
