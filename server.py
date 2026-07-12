#!/usr/bin/env python3
"""AIS Radar Screensaver — minimal server: connects to aisstream.io and serves
live ship positions for a full-screen canvas radar page.

Maintains ONE websocket connection to wss://stream.aisstream.io/v0/stream
(aisstream.io allows only one active connection per API key), accumulates
ship state by MMSI, and serves:
  /            -> radar.html (the screensaver page)
  /api/ships   -> JSON with live ships + feed stats

Configure via environment variables (see README for the full list). Get a
free API key at https://aisstream.io/ — remember: one key = one connection,
so use your own, not one already running elsewhere.
"""
import json
import math
import os
import signal
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from websocket import create_connection

HERE = os.path.dirname(os.path.abspath(__file__))

PORT = int(os.environ.get("AIS_PORT", 8096))
API_KEY = os.environ.get("AISSTREAM_KEY")

# Optional persistence: set AIS_DB_PATH to a file path to snapshot ship state
# to SQLite periodically (and on SIGTERM), so a restart doesn't start from an
# empty map. Leave unset (default) to run purely in-memory, as before.
DB_PATH = os.environ.get("AIS_DB_PATH", "")
SNAPSHOT_S = int(os.environ.get("AIS_SNAPSHOT_S", 60))

# Station center + radius — the aisstream.io bounding box is derived from
# these so the subscribed area always matches what the radar draws.
LAT = float(os.environ.get("AIS_LAT", 38.8728))
LON = float(os.environ.get("AIS_LON", 1.4015))
RANGE_NM = float(os.environ.get("AIS_RANGE_NM", 25))

PRUNE_S = int(os.environ.get("AIS_PRUNE_S", 2400))          # forget ships idle this long
TRAIL_MAX = int(os.environ.get("AIS_TRAIL_MAX", 60))        # max trail points per ship
TRAIL_MIN_GAP_S = int(os.environ.get("AIS_TRAIL_MIN_GAP_S", 30))  # min seconds between trail points

_dlat = RANGE_NM / 60.0
_dlon = RANGE_NM / 60.0 / math.cos(math.radians(LAT))
BBOX = [[[LAT - _dlat, LON - _dlon], [LAT + _dlat, LON + _dlon]]]

ships = {}   # mmsi -> dict
lock = threading.Lock()
stats = {"connected": False, "messages": 0, "started": time.time(), "last_msg": 0}


# ---------- optional SQLite persistence (state survives restarts/reboots) ----------

def _db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS ships ("
                 "mmsi INTEGER PRIMARY KEY, last REAL NOT NULL, data TEXT NOT NULL)")
    return conn


def load_ships():
    """Restore the last snapshot on startup, dropping ships already past PRUNE_S."""
    if not DB_PATH or not os.path.exists(DB_PATH):
        return
    now = time.time()
    conn = _db_connect()
    try:
        rows = conn.execute("SELECT mmsi, data FROM ships WHERE ? - last <= ?",
                            (now, PRUNE_S)).fetchall()
        with lock:
            for mmsi, data in rows:
                ships[mmsi] = json.loads(data)
        print(f"[db] restored {len(rows)} ships from {DB_PATH}", flush=True)
    except Exception as e:
        print(f"[db] failed to restore snapshot: {e}", flush=True)
    finally:
        conn.close()


def save_ships(conn):
    """Write the full current state in one transaction (replace-all snapshot)."""
    with lock:
        rows = [(m, s["last"], json.dumps(s)) for m, s in ships.items()]
    with conn:
        conn.execute("DELETE FROM ships")
        conn.executemany("INSERT INTO ships (mmsi, last, data) VALUES (?, ?, ?)", rows)


def persist_loop():
    conn = _db_connect()  # own connection: SQLite connections aren't thread-safe to share
    while True:
        time.sleep(SNAPSHOT_S)
        try:
            save_ships(conn)
        except Exception as e:
            print(f"[db] error saving snapshot: {e}", flush=True)


def _on_sigterm(signum, frame):
    try:
        save_ships(_db_connect())
        print("[db] final snapshot saved, exiting", flush=True)
    except Exception as e:
        print(f"[db] error saving final snapshot: {e}", flush=True)
    sys.exit(0)


def _merge_position(s, body, now):
    lat, lon = body.get("Latitude"), body.get("Longitude")
    if lat is None or lon is None:
        return
    s["lat"], s["lon"] = lat, lon
    if "Sog" in body:
        s["sog"] = body["Sog"]
    if "Cog" in body:
        s["cog"] = body["Cog"]
    th = body.get("TrueHeading")
    if th is not None and th != 511:
        s["hdg"] = th
    trail = s.setdefault("trail", [])
    if not trail or (now - trail[-1][2] >= TRAIL_MIN_GAP_S
                     and (abs(trail[-1][0] - lat) > 1e-4 or abs(trail[-1][1] - lon) > 1e-4)):
        trail.append([lat, lon, now])
        del trail[:-TRAIL_MAX]


def _merge_static(s, body):
    name = (body.get("Name") or "").strip()
    if name:
        s["name"] = name
    if body.get("Type"):
        s["type"] = body["Type"]
    dest = (body.get("Destination") or "").strip()
    if dest:
        s["dest"] = dest


def handle_message(msg):
    meta = msg.get("MetaData", {})
    mmsi = meta.get("MMSI")
    if not mmsi:
        return
    now = time.time()
    mtype = msg.get("MessageType", "")
    body = msg.get("Message", {}).get(mtype, {})
    with lock:
        s = ships.setdefault(mmsi, {"mmsi": mmsi})
        s["last"] = now
        name = (meta.get("ShipName") or "").strip()
        if name and not s.get("name"):
            s["name"] = name
        if mtype in ("PositionReport", "StandardClassBPositionReport",
                     "ExtendedClassBPositionReport"):
            _merge_position(s, body, now)
        elif mtype == "ShipStaticData":
            _merge_static(s, body)
        elif mtype == "StaticDataReport":
            ra = body.get("ReportA") or {}
            rb = body.get("ReportB") or {}
            n = (ra.get("Name") or "").strip()
            if n:
                s["name"] = n
            if rb.get("ShipType"):
                s["type"] = rb["ShipType"]
        stats["messages"] += 1
        stats["last_msg"] = now


def ws_consumer():
    backoff = 5
    while True:
        try:
            ws = create_connection("wss://stream.aisstream.io/v0/stream", timeout=30)
            ws.send(json.dumps({"APIKey": API_KEY, "BoundingBoxes": BBOX}))
            with lock:
                stats["connected"] = True
            backoff = 5
            while True:
                msg = json.loads(ws.recv())
                if "error" in msg:
                    raise RuntimeError(f"API error: {msg['error']}")
                handle_message(msg)
        except Exception as e:
            with lock:
                stats["connected"] = False
            print(f"[ws] disconnected: {e} — retrying in {backoff}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)


# Explicit static-file whitelist — never serve the directory listing.
STATIC = {
    "/": ("radar.html", "text/html; charset=utf-8", "no-store"),
    "/radar.html": ("radar.html", "text/html; charset=utf-8", "no-store"),
    "/vendor/space-grotesk-700.woff2": ("vendor/space-grotesk-700.woff2", "font/woff2", "max-age=604800"),
    "/vendor/space-grotesk-400.woff2": ("vendor/space-grotesk-400.woff2", "font/woff2", "max-age=604800"),
    "/vendor/jetbrains-mono-400.woff2": ("vendor/jetbrains-mono-400.woff2", "font/woff2", "max-age=604800"),
}
# coast.json is optional: only advertised if you dropped one next to this file.
# Format: a JSON array of polylines, each a list of [lon, lat] points.
if os.path.exists(os.path.join(HERE, "coast.json")):
    STATIC["/coast.json"] = ("coast.json", "application/json", "max-age=86400")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _headers(self, code, ctype, cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", cache)
        self.end_headers()

    def do_GET(self):
        if self.path in STATIC:
            fname, ctype, cache = STATIC[self.path]
            try:
                with open(os.path.join(HERE, fname), "rb") as f:
                    data = f.read()
            except OSError:
                self._headers(500, "text/plain")
                self.wfile.write(f"{fname} missing".encode())
                return
            self._headers(200, ctype, cache)
            self.wfile.write(data)
        elif self.path == "/api/ships":
            now = time.time()
            with lock:
                dead = [m for m, s in ships.items() if now - s["last"] > PRUNE_S]
                for m in dead:
                    del ships[m]
                out = {
                    "server_ts": now,
                    "connected": stats["connected"],
                    "messages": stats["messages"],
                    "last_msg_age": round(now - stats["last_msg"]) if stats["last_msg"] else None,
                    "uptime_s": round(now - stats["started"]),
                    "ships": [dict(s) for s in ships.values() if "lat" in s],
                }
            self._headers(200, "application/json")
            self.wfile.write(json.dumps(out).encode())
        else:
            self._headers(404, "text/plain")
            self.wfile.write(b"not found")


def main():
    if not API_KEY:
        raise SystemExit(
            "AISSTREAM_KEY not set. Get a free key at https://aisstream.io/ — "
            "note: aisstream.io allows only ONE active websocket connection per key, "
            "so use your OWN key, not one already running elsewhere."
        )
    if DB_PATH:
        load_ships()
        signal.signal(signal.SIGTERM, _on_sigterm)
        threading.Thread(target=persist_loop, daemon=True).start()
    threading.Thread(target=ws_consumer, daemon=True).start()
    db_note = f" · persisting to {DB_PATH}" if DB_PATH else ""
    print(f"[http] listening on :{PORT} — station {LAT},{LON} · range {RANGE_NM} NM{db_note}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
