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


def tone(pct):
    return "green" if pct < 60 else "yellow" if pct < 85 else "red"


def bar(pct, width=24):
    filled = round(width * min(max(pct, 0), 100) / 100)
    t = Text()
    t.append("█" * filled, tone(pct))
    t.append("░" * (width - filled), "grey30")
    t.append(f" {pct:5.1f}%", f"bold {tone(pct)}")
    return t


def spark(values, hi=100, width=30):
    vals = list(values)[-width:]
    return Text("".join(SPARK[min(7, int(max(v, 0) / hi * 7.99))] for v in vals), "cyan")


def gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def uptime(sec):
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return (f"{d}d " if d else "") + (f"{h}h " if h else "") + f"{m}m {s}s"


def panel(body, title, **kw):
    return Panel(body, title=f"[bold cyan]{title}[/]", title_align="left", border_style="blue", box=box.ROUNDED, **kw)


def header(s):
    t = Text()
    t.append(" SERVER MONITOR ", "bold bright_magenta")
    t.append(f" {s['hostname']} ", "black on bright_cyan")
    t.append(f"  up {uptime(s['uptime'])}", "grey70")
    t.append(f"  {datetime.now():%H:%M:%S}", "grey70")
    t.append(f"  port {app.CONFIG['port']}", "grey70")
    t.append("   Ctrl+C to quit", "grey42")
    return panel(t, "STATUS")


def sysinfo(s):
    i = s["system"]
    rows = [("Device", i["device"]), ("Hostname", i["hostname"]), ("OS", i["os"]), ("Kernel", i["kernel"]),
            ("Arch", i["arch"]), ("CPU", i["cpu_model"]), ("Cores/threads", f"{i['physical_cores']} / {i['threads']}"),
            ("Memory", gb(s["ram"]["total"])), ("Swap used", f"{s['swap']['percent']}%"), ("Disk", gb(s["storage"]["total"])),
            ("Booted", i["boot_time"]), ("User", i["user"]), ("Python", i["python"]),
            ("IP", ", ".join(a.split(" ")[0] for a in i["ips"][:2]) or "-")]
    tbl = Table.grid(padding=(0, 1), expand=True)
    for _ in range(2):
        tbl.add_column(style="grey62", no_wrap=True)
        tbl.add_column(style="bold white", overflow="ellipsis", no_wrap=True, ratio=1)
    half = (len(rows) + 1) // 2
    for a, b in zip(rows[:half], rows[half:] + [("", "")]):
        tbl.add_row(*a, *b)
    return panel(tbl, "DEVICE & OS")


class Chart:
    """History drawn as filled columns that grow to whatever height the panel gets."""

    def __init__(self, values, hi=100, style="cyan"):
        self.values, self.hi, self.style = list(values), hi, style

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
    rows = [(bar(pct), 1), (Text(sub, "grey62"), 1)]
    if extra:
        rows.append((extra, 1))
    rows.append((Chart(hist), None))
    return panel(stack(*rows), name)


def storage(s):
    st = s["storage"]
    rows = [(bar(st["percent"]), 1), (Text(f"{gb(st['used'])} / {gb(st['total'])}", "grey62"), 1)]
    for p in s["partitions"]:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"{p['mount']:<12.12} ", "grey70")
        line.append("█" * round(p["percent"] / 100 * 12), tone(p["percent"]))
        line.append("░" * (12 - round(p["percent"] / 100 * 12)), "grey30")
        line.append(f" {p['percent']:4.1f}% {gb(p['total'])}", "grey62")
        rows.append((line, 1))
    return panel(stack(*rows), "STORAGE")


def cores(per_core):
    return Text("".join(SPARK[min(7, int(p / 100 * 7.99))] for p in per_core), "bright_blue")


def temperature(s):
    t = s["temperature"]
    if t is None:
        return panel(Text("n/a", "grey62"), "TEMPERATURE")
    pos = min(100, max(0, int(t)))
    gauge_line = Text()
    for i in range(24):
        gauge_line.append("━", "green" if i < 12 else "yellow" if i < 18 else "red")
    gauge_line.append(f"\n{' ' * int(pos / 100 * 23)}▲", "bold white")
    return panel(stack((Text(f"{t} °C", f"bold {tone(t)}"), 1), (gauge_line, 2), (Chart(s["history"]["temp"], 110, "yellow"), None)),
                 "TEMPERATURE")


def battery(s):
    b = s["battery"]
    if not b:
        return panel(Text("AC powered", "grey62"), "BATTERY")
    left = f" · {b['minutes_left'] // 60}h {b['minutes_left'] % 60}m left" if b["minutes_left"] else ""
    pct = b["percent"]
    t = Text()
    t.append("█" * round(pct / 100 * 20), "green" if pct > 40 else "yellow" if pct > 20 else "red")
    t.append("░" * (20 - round(pct / 100 * 20)), "grey30")
    t.append(f" {pct}%", "bold")
    return panel(Group(t, Text("plugged in" if b["plugged"] else "on battery" + left, "grey62")), "BATTERY")


def watched(s):
    t = Table.grid(padding=(0, 1))
    for w in s["watched"]:
        t.add_row(Text("*", "green" if w["running"] else "red"), w["name"],
                  Text(f"{w['count']}× {w['cpu']}% cpu {w['mem']:.1f}% mem" if w["running"] else "not running", "grey62"))
    return panel(t if s["watched"] else Text("set watch_processes in config.json", "grey62"), "WATCHED PROCESSES")


def devices(s):
    t = Table.grid(padding=(0, 1))
    for d in s["devices"]["usb"]:
        t.add_row("USB", Text(d, overflow="ellipsis", no_wrap=True))
    for n in s["devices"]["network"]:
        t.add_row("LAN", Text(f"{n['ip']}  {n['mac']}", style="grey70", no_wrap=True))
    d = s["devices"]
    return panel(t, f"CONNECTED DEVICES · {len(d['usb'])} USB · {len(d['network'])} LAN")


def api_calls():
    with app.REQ_LOCK:
        totals, reqs = dict(app.TOTALS), list(app.REQUESTS)[:30]
    head = Text()
    head.append(f"{totals['total']} total  ", "bold")
    head.append(f"{totals['automation']} automation  ", "bold magenta")
    head.append(f"{totals['errors']} errors", "bold red")
    lines = [head]
    for r in reqs:
        st = "green" if r["status"] < 400 else "yellow" if r["status"] < 500 else "red"
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"{r['time']} ", "grey50")
        line.append("AUTO " if r["source"] == "automation" else "WEB  ", "magenta" if r["source"] == "automation" else "blue")
        line.append(f"{r['method']:<5} ", "bold")
        line.append(f"{r['path']} ")
        line.append(f"{r['status']} ", st)
        line.append(f"{r['ms']}ms {r['caller']}", "grey50")
        lines.append(line)
    if not reqs:
        lines.append(Text("waiting for API calls...", "grey50"))
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


def run():
    console = Console()
    root, sky = build_layout(), Sky()
    sky_panel = Panel(sky, title="[bold bright_yellow]NIGHT SKY[/]", border_style="blue", box=box.ROUNDED)
    stats = app.collect()
    update(root, stats, sky_panel)
    last = time.time()
    # One refresh per frame (auto_refresh off) and the stats panels rebuilt only once a second:
    # redrawing everything at a high rate is what made the screen shake.
    with Live(root, console=console, screen=True, auto_refresh=False, redirect_stderr=False) as live:
        try:
            while True:
                if time.time() - last >= 1:
                    with app.STATS_LOCK:
                        stats = dict(app.LATEST) or stats
                    update(root, stats, sky_panel)
                    last = time.time()
                sky_panel.subtitle = f"[bright_yellow]{sky.subtitle}[/]"
                live.refresh()
                time.sleep(1 / 6)
        except KeyboardInterrupt:
            pass
