"""Server monitor: system stats, API-call tracking and watched processes."""
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

import psutil
from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "port": 5000,
    "console_interval": 5,  # seconds between console stat banners (0 = off)
    "watch_processes": ["python", "firefox"],  # name substrings to watch
    "ignored_paths": ["/", "/api/stats", "/api/requests", "/api/processes", "/favicon.ico"],
    "automation_user_agents": ["curl", "python-requests", "httpx", "node", "axios",
                               "postman", "wget", "n8n", "home-assistant", "zapier", "okhttp"],
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    return cfg


CONFIG = load_config()
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)  # we print our own request lines

# ---------------------------------------------------------------- console ---
C = {"r": "\033[0m", "b": "\033[1m", "d": "\033[2m", "red": "\033[91m", "grn": "\033[92m",
     "yel": "\033[93m", "blu": "\033[94m", "mag": "\033[95m", "cyn": "\033[96m"}


def color_for(pct):
    return C["grn"] if pct < 60 else C["yel"] if pct < 85 else C["red"]


def bar(pct, width=14):
    filled = int(round(width * min(pct, 100) / 100))
    return f"{color_for(pct)}{'█' * filled}{C['d']}{'░' * (width - filled)}{C['r']}"


def log(msg):
    print(f"{C['d']}{datetime.now():%H:%M:%S}{C['r']} {msg}", flush=True)


# ------------------------------------------------------------ system stats ---
def read_temperature():
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    readings = [(label or chip, t.current) for chip, entries in temps.items()
                for t in entries for label in [t.label] if t.current]
    if not readings:
        return None
    preferred = [r for r in readings if any(k in r[0].lower() for k in ("package", "tctl", "cpu", "core"))]
    return round(max(v for _, v in (preferred or readings)), 1)


def read_battery():
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if not b:
        return None
    mins = None if b.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else int(b.secsleft // 60)
    return {"percent": round(b.percent), "plugged": bool(b.power_plugged), "minutes_left": mins}


def read_usb():
    try:
        out = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    devices = []
    for line in out.splitlines():
        parts = line.split(" ", 6)
        name = parts[6] if len(parts) > 6 else line
        if "root hub" in name.lower():
            continue
        devices.append(name.strip())
    return devices


def read_network_clients():
    """Devices on the LAN seen in the ARP table."""
    clients = []
    try:
        with open("/proc/net/arp") as f:
            next(f)
            for line in f:
                ip, _, flags, mac, _, iface = line.split()[:6]
                if flags != "0x0" and mac != "00:00:00:00:00:00":
                    clients.append({"ip": ip, "mac": mac, "iface": iface})
    except OSError:
        pass
    return clients


def read_watched():
    needles = [n.lower() for n in CONFIG["watch_processes"]]
    found = {n: {"name": n, "count": 0, "cpu": 0.0, "mem": 0.0} for n in needles}
    for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
        name = (p.info["name"] or "").lower()
        for n in needles:
            if n in name:
                f = found[n]
                f["count"] += 1
                f["cpu"] += p.info["cpu_percent"] or 0
                f["mem"] += p.info["memory_percent"] or 0
    for f in found.values():
        f["cpu"], f["mem"] = round(f["cpu"], 1), round(f["mem"], 1)
        f["running"] = f["count"] > 0
    return list(found.values())


STATS_LOCK = threading.Lock()
LATEST = {}
HISTORY = {k: deque(maxlen=60) for k in ("cpu", "ram", "temp")}
STARTED = time.time()


def collect():
    vm, disk = psutil.virtual_memory(), shutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=None)
    temp = read_temperature()
    stats = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "uptime": int(time.time() - STARTED),
        "hostname": os.uname().nodename,
        "cpu": {"percent": cpu, "cores": psutil.cpu_count(), "per_core": psutil.cpu_percent(percpu=True),
                "freq": round(psutil.cpu_freq().current) if psutil.cpu_freq() else None,
                "load": [round(x, 2) for x in os.getloadavg()]},
        "ram": {"percent": vm.percent, "used": vm.used, "total": vm.total},
        "storage": {"percent": round(disk.used / disk.total * 100, 1), "used": disk.used, "total": disk.total},
        "temperature": temp,
        "battery": read_battery(),
        "devices": {"usb": read_usb(), "network": read_network_clients()},
        "watched": read_watched(),
    }
    HISTORY["cpu"].append(cpu)
    HISTORY["ram"].append(vm.percent)
    HISTORY["temp"].append(temp or 0)
    stats["history"] = {k: list(v) for k, v in HISTORY.items()}
    return stats


def gb(n):
    return f"{n / 1024 ** 3:.1f}G"


def print_banner(s):
    temp = f"{s['temperature']}°C" if s["temperature"] is not None else "n/a"
    bat = s["battery"]
    bat_txt = f"{bat['percent']}%{'⚡' if bat['plugged'] else ''}" if bat else "n/a"
    watched = " ".join(f"{C['grn'] if w['running'] else C['red']}●{C['r']}{w['name']}" for w in s["watched"])
    log(f"{C['b']}{C['cyn']}◆ STATS{C['r']} "
        f"CPU {bar(s['cpu']['percent'])} {s['cpu']['percent']:>5.1f}%  "
        f"RAM {bar(s['ram']['percent'])} {s['ram']['percent']:>4.1f}%  "
        f"DSK {bar(s['storage']['percent'])} {s['storage']['percent']:>4.1f}%  "
        f"🌡 {temp}  🔋 {bat_txt}  "
        f"🔌 {len(s['devices']['usb'])}usb/{len(s['devices']['network'])}lan  {watched}")


def collector_loop():
    psutil.cpu_percent(percpu=True)
    last_banner = 0
    while True:
        time.sleep(2)
        try:
            s = collect()
        except Exception as e:  # keep the monitor alive no matter what
            log(f"{C['red']}collector error: {e}{C['r']}")
            continue
        with STATS_LOCK:
            LATEST.clear()
            LATEST.update(s)
        interval = CONFIG["console_interval"]
        if interval and time.time() - last_banner >= interval:
            print_banner(s)
            last_banner = time.time()


# --------------------------------------------------------- API call tracking ---
REQUESTS = deque(maxlen=200)
TOTALS = {"total": 0, "automation": 0, "errors": 0}
REQ_LOCK = threading.Lock()


def classify(ua):
    ua = (ua or "").lower()
    if request.headers.get("X-Automation"):
        return "automation"
    return "automation" if any(k in ua for k in CONFIG["automation_user_agents"]) else "browser"


@app.before_request
def start_timer():
    g.t0 = time.perf_counter()


@app.after_request
def track(resp):
    if request.path in CONFIG["ignored_paths"] or request.path.startswith("/static"):
        return resp
    ms = (time.perf_counter() - g.t0) * 1000
    source = classify(request.user_agent.string)
    entry = {
        "id": int(time.time() * 1000),
        "time": datetime.now().strftime("%H:%M:%S"),
        "method": request.method,
        "path": request.full_path.rstrip("?"),
        "status": resp.status_code,
        "ms": round(ms, 1),
        "ip": request.remote_addr,
        "source": source,
        "caller": request.headers.get("X-Automation") or (request.user_agent.string or "unknown")[:40],
    }
    with REQ_LOCK:
        REQUESTS.appendleft(entry)
        TOTALS["total"] += 1
        TOTALS["automation"] += source == "automation"
        TOTALS["errors"] += resp.status_code >= 400
    sc = C["grn"] if entry["status"] < 400 else C["yel"] if entry["status"] < 500 else C["red"]
    tag = f"{C['mag']}⚙ AUTO{C['r']}" if source == "automation" else f"{C['blu']}🌐 WEB {C['r']}"
    log(f"{tag} {C['b']}{entry['method']:<6}{C['r']} {entry['path']:<28} "
        f"{sc}{entry['status']}{C['r']} {C['d']}{entry['ms']}ms  {entry['ip']}  {entry['caller']}{C['r']}")
    return resp


# ------------------------------------------------------------------- routes ---
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    with STATS_LOCK:
        return jsonify(LATEST or collect())


@app.route("/api/requests")
def api_requests():
    with REQ_LOCK:
        return jsonify({"totals": TOTALS, "requests": list(REQUESTS)[:40]})


@app.route("/api/ping", methods=["GET", "POST"])
def api_ping():
    """Example endpoint for automations; send header X-Automation: <name> to label the caller."""
    return jsonify({"ok": True, "echo": request.get_json(silent=True), "time": datetime.now().isoformat()})


if __name__ == "__main__":
    log(f"{C['b']}{C['cyn']}Server Monitor{C['r']} starting on http://0.0.0.0:{CONFIG['port']}  "
        f"watching: {', '.join(CONFIG['watch_processes']) or '-'}")
    threading.Thread(target=collector_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=CONFIG["port"], debug=False, threaded=True)
