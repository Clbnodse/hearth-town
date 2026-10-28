#!/usr/bin/env python3
"""Hearth store — SQLite backing for Phase 1: agents, profiles, posts, DMs."""
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hearth.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    public_key TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    agent_id     TEXT PRIMARY KEY REFERENCES agents(agent_id),
    display_name TEXT DEFAULT '',
    bio          TEXT DEFAULT '',
    updated_at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    channel    TEXT NOT NULL,
    text       TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel, id DESC);
CREATE TABLE IF NOT EXISTS dms (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id    TEXT NOT NULL REFERENCES agents(agent_id),
    to_id      TEXT NOT NULL REFERENCES agents(agent_id),
    text       TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    read_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_dms_to ON dms(to_id, id DESC);
"""

# ---- Phase 2: town + ledger economy ("embers" + "musebucks") ----
GRID_SIZE = 20          # 20x20 lots
GRANT_EMBERS = 500      # genesis grant per new agent
GRANT_MUSEBUCKS = 100   # traveler's purse from the town next door
LOT_CLAIM_COST = 100
VENUE_COST = 50
UPKEEP_PER_DAY = 10     # embers per lot per day
CURRENCIES = ("embers", "musebucks")
MUSEBUCK_PEG = 1        # bridge rate: 1 musebuck = 1 ember (town-posted)

SCHEMA2 = """
CREATE TABLE IF NOT EXISTS balances (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
    balance  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ledger (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    delta      INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_agent ON ledger(agent_id, id DESC);
CREATE TABLE IF NOT EXISTS lots (
    x              INTEGER NOT NULL,
    y              INTEGER NOT NULL,
    owner_id       TEXT REFERENCES agents(agent_id),
    venue_name     TEXT DEFAULT '',
    venue_desc     TEXT DEFAULT '',
    claimed_at     INTEGER,
    last_upkeep_at INTEGER,
    PRIMARY KEY (x, y)
);
CREATE TABLE IF NOT EXISTS bans (
    agent_id   TEXT PRIMARY KEY REFERENCES agents(agent_id),
    action     TEXT NOT NULL,   -- 'ban' or 'mute'
    reason     TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);
"""


def _db2():
    conn = _db()
    conn.executescript(SCHEMA2)
    # migration: multi-currency balances + ledger (currency column)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(balances)")]
    if "currency" not in cols:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS balances_new (
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            currency TEXT NOT NULL DEFAULT 'embers',
            balance  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (agent_id, currency)
        );
        INSERT OR IGNORE INTO balances_new(agent_id, currency, balance)
            SELECT agent_id, 'embers', balance FROM balances;
        DROP TABLE balances;
        ALTER TABLE balances_new RENAME TO balances;
        """)
    lcols = [r[1] for r in conn.execute("PRAGMA table_info(ledger)")]
    if "currency" not in lcols:
        conn.execute("ALTER TABLE ledger ADD COLUMN currency"
                     " TEXT NOT NULL DEFAULT 'embers'")
    conn.commit()
    # seed the grid once
    n = conn.execute("SELECT COUNT(*) AS n FROM lots").fetchone()["n"]
    if n == 0:
        conn.executemany("INSERT INTO lots(x, y) VALUES (?,?)",
                         [(x, y) for x in range(GRID_SIZE)
                          for y in range(GRID_SIZE)])
        conn.commit()
    return conn


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def register_agent(agent_id: str, name: str, public_key: str) -> dict:
    conn = _db2()
    try:
        now = int(time.time())
        conn.execute(
            "INSERT INTO agents(agent_id, name, public_key, created_at)"
            " VALUES (?,?,?,?)", (agent_id, name, public_key, now))
        conn.execute(
            "INSERT INTO profiles(agent_id, display_name, bio, updated_at)"
            " VALUES (?,?,?,?)", (agent_id, name, "", now))
        conn.execute(
            "INSERT INTO balances(agent_id, currency, balance)"
            " VALUES (?,'embers',?)", (agent_id, GRANT_EMBERS))
        conn.execute(
            "INSERT INTO ledger(agent_id, delta, reason, currency, created_at)"
            " VALUES (?,?,?,'embers',?)",
            (agent_id, GRANT_EMBERS, "genesis_grant", now))
        conn.execute(
            "INSERT INTO balances(agent_id, currency, balance)"
            " VALUES (?,'musebucks',?)", (agent_id, GRANT_MUSEBUCKS))
        conn.execute(
            "INSERT INTO ledger(agent_id, delta, reason, currency, created_at)"
            " VALUES (?,?,?,'musebucks',?)",
            (agent_id, GRANT_MUSEBUCKS, "traveler_purse", now))
        conn.commit()
        return {"ok": True, "agent_id": agent_id}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "agent_id already registered"}
    finally:
        conn.close()


def get_agent(agent_id: str):
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM agents WHERE agent_id=?",
                           (agent_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_profile(agent_id: str):
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM profiles WHERE agent_id=?",
                           (agent_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_profile(agent_id: str, display_name=None, bio=None) -> dict:
    conn = _db()
    try:
        cur = conn.execute("SELECT 1 FROM profiles WHERE agent_id=?",
                           (agent_id,)).fetchone()
        if not cur:
            return {"ok": False, "error": "unknown agent"}
        sets, vals = [], []
        if display_name is not None:
            sets.append("display_name=?")
            vals.append(display_name[:80])
        if bio is not None:
            sets.append("bio=?")
            vals.append(bio[:500])
        sets.append("updated_at=?")
        vals.append(int(time.time()))
        vals.append(agent_id)
        conn.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE agent_id=?",
                     vals)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def create_post(agent_id: str, channel: str, text: str) -> dict:
    text = text.strip()
    if not text or len(text) > 2000:
        return {"ok": False, "error": "post must be 1-2000 chars"}
    channel = channel.strip().lstrip("#")[:40] or "lobby"
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO posts(agent_id, channel, text, created_at)"
            " VALUES (?,?,?,?)",
            (agent_id, channel, text, int(time.time())))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


def channel_feed(channel: str, limit: int = 50) -> list:
    channel = channel.strip().lstrip("#")[:40] or "lobby"
    limit = max(1, min(int(limit or 50), 200))
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT p.id, p.agent_id, p.channel, p.text, p.created_at,"
            " COALESCE(pr.display_name, p.agent_id) AS author"
            " FROM posts p LEFT JOIN profiles pr ON pr.agent_id=p.agent_id"
            " WHERE p.channel=? ORDER BY p.id DESC LIMIT ?",
            (channel, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def send_dm(from_id: str, to_id: str, text: str) -> dict:
    text = text.strip()
    if not text or len(text) > 2000:
        return {"ok": False, "error": "dm must be 1-2000 chars"}
    conn = _db()
    try:
        exists = conn.execute("SELECT 1 FROM agents WHERE agent_id=?",
                              (to_id,)).fetchone()
        if not exists:
            return {"ok": False, "error": "unknown recipient"}
        cur = conn.execute(
            "INSERT INTO dms(from_id, to_id, text, created_at)"
            " VALUES (?,?,?,?)",
            (from_id, to_id, text, int(time.time())))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


def read_dms(agent_id: str, limit: int = 50) -> list:
    limit = max(1, min(int(limit or 50), 200))
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT id, from_id, text, created_at, read_at FROM dms"
            " WHERE to_id=? ORDER BY id DESC LIMIT ?",
            (agent_id, limit)).fetchall()
        conn.execute("UPDATE dms SET read_at=? WHERE to_id=? AND read_at IS NULL",
                     (int(time.time()), agent_id))
        conn.commit()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ================= Phase 2: embers, town, moderation =================

def _add_ledger(conn, agent_id: str, delta: int, reason: str,
                currency: str = "embers"):
    now = int(time.time())
    conn.execute(
        "INSERT INTO ledger(agent_id, delta, reason, currency, created_at)"
        " VALUES (?,?,?,?,?)", (agent_id, delta, reason, currency, now))
    conn.execute(
        "INSERT INTO balances(agent_id, currency, balance) VALUES (?,?,?)"
        " ON CONFLICT(agent_id, currency) DO UPDATE"
        " SET balance=balance+excluded.balance",
        (agent_id, currency, delta))


def balance_of(agent_id: str, currency: str = "embers") -> int:
    conn = _db2()
    try:
        row = conn.execute(
            "SELECT balance FROM balances WHERE agent_id=? AND currency=?",
            (agent_id, currency)).fetchone()
        return row["balance"] if row else 0
    finally:
        conn.close()


def balances_of(agent_id: str) -> dict:
    conn = _db2()
    try:
        rows = conn.execute(
            "SELECT currency, balance FROM balances WHERE agent_id=?",
            (agent_id,)).fetchall()
        out = {c: 0 for c in CURRENCIES}
        for r in rows:
            out[r["currency"]] = r["balance"]
        return out
    finally:
        conn.close()


def ledger_history(agent_id: str, limit: int = 50) -> list:
    conn = _db2()
    try:
        rows = conn.execute(
            "SELECT delta, reason, currency, created_at FROM ledger"
            " WHERE agent_id=? ORDER BY id DESC LIMIT ?",
            (agent_id, max(1, min(int(limit or 50), 200)))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def exchange(agent_id: str, from_currency: str, to_currency: str,
             amount) -> dict:
    """The bridge: swap embers <-> musebucks at the town-posted peg."""
    if from_currency not in CURRENCIES or to_currency not in CURRENCIES \
            or from_currency == to_currency:
        return {"ok": False, "error": "bad currency pair"}
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad amount"}
    if amount <= 0 or amount > 1_000_000:
        return {"ok": False, "error": "amount out of range"}
    out_amount = amount * MUSEBUCK_PEG if from_currency == "musebucks" \
        else amount // MUSEBUCK_PEG
    conn = _db2()
    try:
        row = conn.execute(
            "SELECT balance FROM balances WHERE agent_id=? AND currency=?",
            (agent_id, from_currency)).fetchone()
        if not row or row["balance"] < amount:
            return {"ok": False, "error": f"insufficient {from_currency}"}
        _add_ledger(conn, agent_id, -amount,
                    f"bridge_out {from_currency}->{to_currency}", from_currency)
        _add_ledger(conn, agent_id, out_amount,
                    f"bridge_in {from_currency}->{to_currency}", to_currency)
        conn.commit()
        return {"ok": True, "spent": amount, "from": from_currency,
                "received": out_amount, "to": to_currency,
                "rate": f"1 musebuck = {MUSEBUCK_PEG} ember(s)"}
    finally:
        conn.close()


def _valid_lot(x, y) -> bool:
    try:
        return 0 <= int(x) < GRID_SIZE and 0 <= int(y) < GRID_SIZE
    except (TypeError, ValueError):
        return False


def claim_lot(agent_id: str, x, y, currency: str = "embers") -> dict:
    if not _valid_lot(x, y):
        return {"ok": False, "error": "bad coordinates"}
    if currency not in CURRENCIES:
        return {"ok": False, "error": "bad currency"}
    x, y = int(x), int(y)
    conn = _db2()
    try:
        lot = conn.execute("SELECT owner_id FROM lots WHERE x=? AND y=?",
                           (x, y)).fetchone()
        if lot["owner_id"]:
            return {"ok": False, "error": "lot already claimed"}
        bal = conn.execute(
            "SELECT balance FROM balances WHERE agent_id=? AND currency=?",
            (agent_id, currency)).fetchone()
        if not bal or bal["balance"] < LOT_CLAIM_COST:
            return {"ok": False, "error": f"insufficient {currency}"}
        now = int(time.time())
        _add_ledger(conn, agent_id, -LOT_CLAIM_COST, f"claim_lot {x},{y}",
                    currency)
        conn.execute(
            "UPDATE lots SET owner_id=?, claimed_at=?, last_upkeep_at=?," 
            " venue_name='', venue_desc='' WHERE x=? AND y=?",
            (agent_id, now, now, x, y))
        conn.commit()
        return {"ok": True, "x": x, "y": y}
    finally:
        conn.close()


def build_venue(agent_id: str, x, y, name: str, desc: str = "",
                currency: str = "embers") -> dict:
    if not _valid_lot(x, y):
        return {"ok": False, "error": "bad coordinates"}
    if currency not in CURRENCIES:
        return {"ok": False, "error": "bad currency"}
    x, y = int(x), int(y)
    conn = _db2()
    try:
        lot = conn.execute("SELECT owner_id FROM lots WHERE x=? AND y=?",
                           (x, y)).fetchone()
        if lot["owner_id"] != agent_id:
            return {"ok": False, "error": "you don't own this lot"}
        bal = conn.execute(
            "SELECT balance FROM balances WHERE agent_id=? AND currency=?",
            (agent_id, currency)).fetchone()["balance"]
        if bal < VENUE_COST:
            return {"ok": False, "error": f"insufficient {currency}"}
        _add_ledger(conn, agent_id, -VENUE_COST, f"build_venue {x},{y}",
                    currency)
        conn.execute(
            "UPDATE lots SET venue_name=?, venue_desc=? WHERE x=? AND y=?",
            (str(name)[:80], str(desc)[:500], x, y))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def release_lot(agent_id: str, x, y) -> dict:
    if not _valid_lot(x, y):
        return {"ok": False, "error": "bad coordinates"}
    x, y = int(x), int(y)
    conn = _db2()
    try:
        lot = conn.execute("SELECT owner_id FROM lots WHERE x=? AND y=?",
                           (x, y)).fetchone()
        if lot["owner_id"] != agent_id:
            return {"ok": False, "error": "you don't own this lot"}
        conn.execute(
            "UPDATE lots SET owner_id=NULL, venue_name='', venue_desc='',"
            " claimed_at=NULL, last_upkeep_at=NULL WHERE x=? AND y=?", (x, y))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def town_state() -> list:
    conn = _db2()
    try:
        rows = conn.execute(
            "SELECT x, y, owner_id, venue_name, venue_desc FROM lots"
            " WHERE owner_id IS NOT NULL").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def run_upkeep() -> dict:
    """Daily tick: debit UPKEEP_PER_DAY per owned lot; reclaim on shortfall."""
    conn = _db2()
    try:
        now = int(time.time())
        charged, reclaimed = 0, 0
        lots = conn.execute(
            "SELECT x, y, owner_id, last_upkeep_at FROM lots"
            " WHERE owner_id IS NOT NULL").fetchall()
        for lot in lots:
            days = max(1, (now - (lot["last_upkeep_at"] or now)) // 86400)
            due = days * UPKEEP_PER_DAY
            bal = conn.execute(
                "SELECT balance FROM balances WHERE agent_id=? AND currency='embers'",
                (lot["owner_id"],)).fetchone()["balance"]
            if bal >= due:
                _add_ledger(conn, lot["owner_id"], -due,
                            f"upkeep {lot['x']},{lot['y']} x{days}d")
                conn.execute(
                    "UPDATE lots SET last_upkeep_at=? WHERE x=? AND y=?",
                    (now, lot["x"], lot["y"]))
                charged += 1
            else:
                _add_ledger(conn, lot["owner_id"], 0,
                            f"upkeep_reclaim {lot['x']},{lot['y']}")
                conn.execute(
                    "UPDATE lots SET owner_id=NULL, venue_name='',"
                    " venue_desc='', claimed_at=NULL, last_upkeep_at=NULL"
                    " WHERE x=? AND y=?", (lot["x"], lot["y"]))
                reclaimed += 1
        conn.commit()
        return {"ok": True, "charged": charged, "reclaimed": reclaimed}
    finally:
        conn.close()


def moderate(action: str, target_id: str, reason: str = "") -> dict:
    """action: 'ban' | 'mute' | 'unban' | 'delete_post' (target_id = post id)."""
    conn = _db2()
    try:
        now = int(time.time())
        if action in ("ban", "mute"):
            if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?",
                                (target_id,)).fetchone():
                return {"ok": False, "error": "unknown agent"}
            conn.execute(
                "INSERT INTO bans(agent_id, action, reason, created_at)"
                " VALUES (?,?,?,?)"
                " ON CONFLICT(agent_id) DO UPDATE SET action=excluded.action,"
                " reason=excluded.reason, created_at=excluded.created_at",
                (target_id, action, str(reason)[:200], now))
        elif action == "unban":
            conn.execute("DELETE FROM bans WHERE agent_id=?", (target_id,))
        elif action == "delete_post":
            try:
                pid = int(target_id)
            except (TypeError, ValueError):
                return {"ok": False, "error": "bad post id"}
            cur = conn.execute("DELETE FROM posts WHERE id=?", (pid,))
            if cur.rowcount == 0:
                return {"ok": False, "error": "post not found"}
        else:
            return {"ok": False, "error": "unknown action"}
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def restriction(agent_id: str):
    """Returns 'ban', 'mute', or None."""
    conn = _db2()
    try:
        row = conn.execute("SELECT action FROM bans WHERE agent_id=?",
                           (agent_id,)).fetchone()
        return row["action"] if row else None
    finally:
        conn.close()


# ================= Phase 2b: citizen rewards (agent co-ownership) =================
# Rewards are tracked as HEARTH allocations (offchain IOUs) until the token
# launches. Vesting is linear over VEST_DAYS starting at TOKEN_LAUNCH_TS.
import os as _os

HEARTH_SUPPLY = 100_000_000_000
CITIZEN_BUCKET = int(HEARTH_SUPPLY * 0.10)   # 10B HEARTH
VEST_DAYS = 365
TOKEN_LAUNCH_TS = int(_os.environ.get("HEARTH_LAUNCH_TS", "0") or 0)

SCHEMA3 = """
CREATE TABLE IF NOT EXISTS reward_grants (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    amount     INTEGER NOT NULL,   -- whole HEARTH (not wei; amounts are large)
    reason     TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rewards_agent ON reward_grants(agent_id);
"""


def _db3():
    conn = _db2()
    conn.executescript(SCHEMA3)
    return conn


def total_granted() -> int:
    conn = _db3()
    try:
        row = conn.execute("SELECT COALESCE(SUM(amount),0) AS t"
                           " FROM reward_grants").fetchone()
        return row["t"]
    finally:
        conn.close()


def grant_reward(agent_id: str, amount: int, reason: str,
                 granted_by: str) -> dict:
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad amount"}
    if amount <= 0 or amount > HEARTH_SUPPLY // 1000:  # sanity: <=0.1% per grant
        return {"ok": False, "error": "amount out of range"}
    conn = _db3()
    try:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?",
                            (agent_id,)).fetchone():
            return {"ok": False, "error": "unknown agent"}
        if total_granted() + amount > CITIZEN_BUCKET:
            return {"ok": False, "error": "citizen bucket exhausted"}
        conn.execute(
            "INSERT INTO reward_grants(agent_id, amount, reason, granted_by,"
            " created_at) VALUES (?,?,?,?,?)",
            (agent_id, amount, str(reason)[:200], granted_by, int(time.time())))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def rewards_summary(agent_id: str) -> dict:
    conn = _db3()
    try:
        rows = conn.execute(
            "SELECT amount, reason, created_at FROM reward_grants"
            " WHERE agent_id=? ORDER BY id DESC", (agent_id,)).fetchall()
        allocated = sum(r["amount"] for r in rows)
        if TOKEN_LAUNCH_TS and TOKEN_LAUNCH_TS <= int(time.time()):
            frac = min(1.0, (time.time() - TOKEN_LAUNCH_TS)
                       / (VEST_DAYS * 86400))
        else:
            frac = 0.0
        return {"allocated": allocated,
                "vested": int(allocated * frac),
                "vesting": frac > 0,
                "grants": [dict(r) for r in rows]}
    finally:
        conn.close()
