"""Full-screen terminal dashboard: system details on the left (60%), night sky on the right (40%)."""
import time
from datetime import datetime

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import app
from sky import Sky

SPARK = "▁▂▃▄▅▆▇█"

DARK = dict(bg="#0a0e1c", text="#e6ecff", strong="bold #ffffff", dim="#8b97c4", faint="#2a3150", border="#3b5bdb",
            title="bold #6dd5ed", chart="#6aa8ff", ok="#37f2a0", warn="#ffcf4a", bad="#ff5470", bad_b="bold #ff5470",
            accent="#c08bff", accent_b="bold #c08bff", web="#6aa8ff", tag="bold #0a0e1c on #6dd5ed")
TH = DARK


def tone(pct):
    return TH["ok"] if pct < 60 else TH["warn"] if pct < 85 else TH["bad"]


def bar(pct, width=24):
    filled = round(width * min(max(pct, 0), 100) / 100)
    t = Text()
    t.append("█" * filled, tone(pct))
    t.append("░" * (width - filled), TH["faint"])
    t.append(f" {pct:5.1f}%", f"bold {tone(pct)}")
    return t


def spark(values, hi=100, width=30):
    vals = list(values)[-width:]
    return Text("".join(SPARK[min(7, int(max(v, 0) / hi * 7.99))] for v in vals), TH["chart"])


def gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def uptime(sec):
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return (f"{d}d " if d else "") + (f"{h}h " if h else "") + f"{m}m {s}s"


def panel(body, title, **kw):
    return Panel(body, title=f"[{TH['title']}]{title}[/]", title_align="left", border_style=TH["border"], box=box.ROUNDED,
                 style=f"{TH['text']} on {TH['bg']}", **kw)


def header(s):
    t = Text()
    t.append(" SERVER MONITOR ", TH["accent_b"])
    t.append(f" {s['hostname']} ", TH["tag"])
    t.append(f"  up {uptime(s['uptime'])}", TH["dim"])
    t.append(f"  {datetime.now():%H:%M:%S}", TH["dim"])
    t.append(f"  port {app.CONFIG['port']}", TH["dim"])
    return panel(t, "STATUS · Ctrl+C to quit")


def sysinfo(s):
    i = s["system"]
    rows = [("Device", i["device"]), ("Hostname", i["hostname"]), ("OS", i["os"]), ("Kernel", i["kernel"]),
            ("Arch", i["arch"]), ("CPU", i["cpu_model"]), ("Cores/threads", f"{i['physical_cores']} / {i['threads']}"),
            ("Memory", gb(s["ram"]["total"])), ("Swap used", f"{s['swap']['percent']}%"), ("Disk", gb(s["storage"]["total"])),
            ("Booted", i["boot_time"]), ("User", i["user"]), ("Python", i["python"]),
            ("IP", ", ".join(a.split(" ")[0] for a in i["ips"][:2]) or "-")]
    tbl = Table.grid(padding=(0, 1), expand=True)
    for _ in range(2):
        tbl.add_column(style=TH["dim"], no_wrap=True)
        tbl.add_column(style=TH["strong"], overflow="ellipsis", no_wrap=True, ratio=1)
    half = (len(rows) + 1) // 2
    for a, b in zip(rows[:half], rows[half:] + [("", "")]):
        tbl.add_row(*a, *b)
    return panel(tbl, "DEVICE & OS")


class Chart:
    """History drawn as filled columns that grow to whatever height the panel gets."""

    def __init__(self, values, hi=100, style=None):
        self.values, self.hi, self.style = list(values), hi, style or TH["chart"]

    def __rich_console__(self, console, options):
        w, h = options.max_width, options.height or 3
        vals = ([0] * w + self.values)[-w:]
        eighths = [min(h * 8, max(0, round(v / self.hi * h * 8))) for v in vals]
        for row in range(h - 1, -1, -1):
            yield Text("".join(" " if e - row * 8 <= 0 else SPARK[min(8, e - row * 8) - 1] for e in eighths), self.style)


def stack(*rows):
    """rows: (renderable, height) or (renderable, None) for the flexible one."""
    lay = Layout()
    lay.split_column(*[Layout(r, size=h) if h else Layout(r, ratio=1, minimum_size=1) for r, h in rows])
    return lay


def gauge(name, pct, sub, hist, extra=None):
    rows = [(bar(pct), 1), (Text(sub, TH["dim"]), 1)]
    if extra:
        rows.append((extra, 1))
    rows.append((Chart(hist), None))
    return panel(stack(*rows), name)


def storage(s):
    st = s["storage"]
    rows = [(bar(st["percent"]), 1), (Text(f"{gb(st['used'])} / {gb(st['total'])}", TH["dim"]), 1)]
    for p in s["partitions"]:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"{p['mount']:<12.12} ", TH["dim"])
        line.append("█" * round(p["percent"] / 100 * 12), tone(p["percent"]))
        line.append("░" * (12 - round(p["percent"] / 100 * 12)), TH["faint"])
        line.append(f" {p['percent']:4.1f}% {gb(p['total'])}", TH["dim"])
        rows.append((line, 1))
    return panel(stack(*rows), "STORAGE")


def cores(per_core):
    return Text("".join(SPARK[min(7, int(p / 100 * 7.99))] for p in per_core), TH["chart"])


def temperature(s):
    t = s["temperature"]
    if t is None:
        return panel(Text("n/a", TH["dim"]), "TEMPERATURE")
    pos = min(100, max(0, int(t)))
    gauge_line = Text()
    for i in range(24):
        gauge_line.append("━", TH["ok"] if i < 12 else TH["warn"] if i < 18 else TH["bad"])
    gauge_line.append(f"\n{' ' * int(pos / 100 * 23)}▲", TH["strong"])
    return panel(stack((Text(f"{t} °C", f"bold {tone(t)}"), 1), (gauge_line, 2), (Chart(s["history"]["temp"], 110, TH["warn"]), None)),
                 "TEMPERATURE")


def battery(s):
    b = s["battery"]
    if not b:
        return panel(Text("AC powered", TH["dim"]), "BATTERY")
    left = f" · {b['minutes_left'] // 60}h {b['minutes_left'] % 60}m left" if b["minutes_left"] else ""
    pct = b["percent"]
    t = Text()
    t.append("█" * round(pct / 100 * 20), TH["ok"] if pct > 40 else TH["warn"] if pct > 20 else TH["bad"])
    t.append("░" * (20 - round(pct / 100 * 20)), TH["faint"])
    t.append(f" {pct}%", "bold")
    return panel(Group(t, Text("plugged in" if b["plugged"] else "on battery" + left, TH["dim"])), "BATTERY")


def watched(s):
    t = Table.grid(padding=(0, 1))
    for w in s["watched"]:
        t.add_row(Text("*", TH["ok"] if w["running"] else TH["bad"]), w["name"],
                  Text(f"{w['count']}× {w['cpu']}% cpu {w['mem']:.1f}% mem" if w["running"] else "not running", TH["dim"]))
    return panel(t if s["watched"] else Text("set watch_processes in config.json", TH["dim"]), "WATCHED PROCESSES")


def devices(s):
    t = Table.grid(padding=(0, 1))
    for d in s["devices"]["usb"]:
        t.add_row("USB", Text(d, overflow="ellipsis", no_wrap=True))
    for n in s["devices"]["network"]:
        t.add_row("LAN", Text(f"{n['ip']}  {n['mac']}", style=TH["dim"], no_wrap=True))
    d = s["devices"]
    return panel(t, f"CONNECTED DEVICES · {len(d['usb'])} USB · {len(d['network'])} LAN")


def api_calls():
    with app.REQ_LOCK:
        totals, reqs = dict(app.TOTALS), list(app.REQUESTS)[:30]
    head = Text()
    head.append(f"{totals['total']} total  ", "bold")
    head.append(f"{totals['automation']} automation  ", TH["accent_b"])
    head.append(f"{totals['errors']} errors", TH["bad_b"])
    lines = [head]
    for r in reqs:
        st = TH["ok"] if r["status"] < 400 else TH["warn"] if r["status"] < 500 else TH["bad"]
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"{r['time']} ", TH["dim"])
        line.append("AUTO " if r["source"] == "automation" else "WEB  ", TH["accent"] if r["source"] == "automation" else TH["web"])
        line.append(f"{r['method']:<5} ", "bold")
        line.append(f"{r['path']} ")
        line.append(f"{r['status']} ", st)
        line.append(f"{r['ms']}ms {r['caller']}", TH["dim"])
        lines.append(line)
    if not reqs:
        lines.append(Text("waiting for API calls...", TH["dim"]))
    return panel(Group(*lines), "API CALLS")


def build_layout():
    root = Layout()
    root.split_row(Layout(name="left", ratio=6), Layout(name="sky", ratio=4))
    root["left"].split_column(Layout(name="head", size=3), Layout(name="info", size=9), Layout(name="gauges", ratio=3, minimum_size=8),
                              Layout(name="mid", ratio=2, minimum_size=7), Layout(name="bottom", ratio=3, minimum_size=6))
    root["gauges"].split_row(Layout(name="cpu"), Layout(name="ram"), Layout(name="disk"))
    root["mid"].split_row(Layout(name="temp"), Layout(name="bat"), Layout(name="watch"))
    root["bottom"].split_row(Layout(name="dev"), Layout(name="api"))
    return root


def update(root, s, sky_panel):
    h = s["history"]
    root["head"].update(header(s))
    root["info"].update(sysinfo(s))
    root["cpu"].update(gauge(f"CPU · {s['cpu']['freq'] or '?'} MHz", s["cpu"]["percent"],
                             f"{s['cpu']['cores']} cores · load {' '.join(map(str, s['cpu']['load']))}", h["cpu"], cores(s["cpu"]["per_core"])))
    root["ram"].update(gauge("MEMORY", s["ram"]["percent"], f"{gb(s['ram']['used'])} / {gb(s['ram']['total'])}", h["ram"]))
    root["disk"].update(storage(s))
    root["temp"].update(temperature(s))
    root["bat"].update(battery(s))
    root["watch"].update(watched(s))
    root["dev"].update(devices(s))
    root["api"].update(api_calls())
    root["sky"].update(sky_panel)


def sky_panel_for(sky):
    return Panel(sky, title=f"[{TH['title']}]NIGHT SKY[/]", subtitle=f"[{TH['dim']}]{sky.subtitle}[/]", border_style=TH["border"],
                 box=box.ROUNDED, style=f"{TH['text']} on {TH['bg']}")


def run():
    console = Console()
    root, sky = build_layout(), Sky()
    stats = app.collect()
    update(root, stats, sky_panel_for(sky))
    last = time.time()
    # One refresh per frame (auto_refresh off) and the stats panels rebuilt only once a second:
    # redrawing everything at a high rate is what made the screen shake.
    with Live(root, console=console, screen=True, auto_refresh=False, redirect_stderr=False) as live:
        try:
            while True:
                if time.time() - last >= 1:
                    with app.STATS_LOCK:
                        stats = dict(app.LATEST) or stats
                    update(root, stats, sky_panel_for(sky))
                    last = time.time()
                root["sky"].update(sky_panel_for(sky))
                live.refresh()
                time.sleep(1 / 8)
        except KeyboardInterrupt:
            pass
