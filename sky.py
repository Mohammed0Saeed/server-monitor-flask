"""Animated terminal night sky: twinkling stars, the real moon phase, and an astronaut pointing at things."""
import math
import random
import time
from datetime import datetime, timezone

from rich.text import Text

STAR_NAMES = ["Sirius", "Vega", "Polaris", "Betelgeuse", "Rigel", "Arcturus", "Altair"]
SYNODIC = 29.530588853
NEW_MOON_JD = 2451550.1  # new moon of 2000-01-06
MOVE_SECS, HOLD_SECS = 1.4, 2.8
ARM_LEN = 5

PHASE_NAMES = [(.03, "New Moon"), (.22, "Waxing Crescent"), (.28, "First Quarter"), (.47, "Waxing Gibbous"),
               (.53, "Full Moon"), (.72, "Waning Gibbous"), (.78, "Last Quarter"), (.97, "Waning Crescent")]

# 10 rows x 9 cols; row 2 holds the visor (swapped per head direction); shoulder = (9, 4)
SPRITE = ["  _---_  ",
          " /     \\ ",
          "|  VVV  |",
          " \\_____/ ",
          " ▐█████▌ ",
          " ▐█[▪]█▌ ",
          "  █████  ",
          "  ██ ██  ",
          "  ██ ██  ",
          "  ▀▀ ▀▀  "]
VISORS = {-1: "| VVV   |", 0: "|  VVV  |", 1: "|   VVV |"}
SHOULDER = (9, 4)


def moon_phase(now=None):
    now = now or datetime.now(timezone.utc)
    jd = now.timestamp() / 86400 + 2440587.5
    age = (jd - NEW_MOON_JD) % SYNODIC
    p = age / SYNODIC
    c = math.cos(2 * math.pi * p)
    name = next((n for lim, n in PHASE_NAMES if p < lim), "New Moon")
    return {"p": p, "age": age, "c": c, "name": name, "lit": round((1 - c) / 2 * 100)}


def ease(k):
    return 4 * k ** 3 if k < .5 else 1 - (-2 * k + 2) ** 3 / 2


def line_cells(x0, y0, x1, y1):
    n = max(abs(x1 - x0), abs(y1 - y0)) or 1
    return [(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)) for i in range(1, n)]


class Sky:
    def __init__(self):
        self.size = None
        self.idx = -1
        self.last = -1
        self.cur = -math.pi / 3
        self.frm = self.to = self.cur
        self.t0 = time.monotonic()
        self.target = None
        self.phase = moon_phase()
        self.phase_at = time.monotonic()

    @property
    def subtitle(self):
        ph = self.phase
        return f"🌙 {ph['name']} · {ph['lit']}% lit · day {ph['age']:.1f}"

    # ------------------------------------------------------------ layout ---
    def _build(self, w, h):
        rng = random.Random(w * 1000 + h)
        self.size = (w, h)
        self.moon = (int(w * .68), int(h * .2), max(2, min(5, h // 7)))
        self.ax, self.ay = max(1, int(w * .22)), max(0, h - 2 - len(SPRITE))
        self.shoulder = (self.ax + SHOULDER[0], self.ay + SHOULDER[1])
        mx, my, mr = self.moon
        self.stars = [(rng.randrange(w), rng.randrange(max(1, h - 3)), rng.random() * 6.28, .8 + rng.random() * 2)
                      for _ in range(w * h // 35)]
        self.targets = [{"x": mx, "y": my, "label": "the Moon"}]
        for name in STAR_NAMES:
            for _ in range(50):
                x, y = rng.randrange(3, max(4, w - 3)), rng.randrange(1, max(2, int(h * .55)))
                if math.hypot((x - mx) / 2, y - my) > mr + 3 and y < self.shoulder[1] - 2:
                    break
            self.targets.append({"x": x, "y": y, "label": name})
        self.idx = -1
        self._pick(time.monotonic())

    def _pick(self, now):
        self.idx += 1
        nxt = 0  # every other point goes to the moon
        if self.idx % 2 == 1:
            nxt = self.last
            while nxt == self.last:
                nxt = random.randrange(1, len(self.targets))
        self.last = nxt
        self.target = self.targets[nxt]
        sx, sy = self.shoulder
        self.frm = self.cur
        to = math.atan2(self.target["y"] - sy, (self.target["x"] - sx) / 2)
        d = (to - self.frm + math.pi) % (2 * math.pi) - math.pi  # shortest way round
        self.to = self.frm + d
        self.t0 = now

    # ------------------------------------------------------------ render ---
    def __rich_console__(self, console, options):
        w = options.max_width
        h = options.height or options.max_height
        if (w, h) != self.size:
            self._build(w, h)
        now = time.monotonic()
        if now - self.phase_at > 3600:
            self.phase, self.phase_at = moon_phase(), now
        k = max(0, min(1, (now - self.t0) / MOVE_SECS))
        arrived = k >= 1
        self.cur = self.frm + (self.to - self.frm) * ease(k) + (math.sin(now * 4) * .03 if arrived else 0)
        if now - self.t0 > MOVE_SECS + HOLD_SECS:
            self._pick(now)

        grid = [[(" ", "") for _ in range(w)] for _ in range(h)]

        def put(x, y, ch, style):
            if 0 <= x < w and 0 <= y < h:
                grid[y][x] = (ch, style)

        for x, y, ph, sp in self.stars:
            v = math.sin(now * sp + ph)
            put(x, y, "*" if v > .85 else "+" if v > .5 else "·" if v > -.4 else ".", "white" if v > .3 else "grey50")
        for t in self.targets[1:]:
            on = int(now * 2) % 2 == 0 or t is not self.target or not arrived
            put(t["x"], t["y"], "✦" if on else "✧", "bold bright_yellow")

        self._moon(put)
        self._ground(put, w, h, now)

        sx, sy = self.shoulder
        tx, ty = self.target["x"], self.target["y"]
        cos, sin = math.cos(self.cur), math.sin(self.cur)
        hand = (sx + round(cos * 2 * ARM_LEN), sy + round(sin * ARM_LEN))
        if arrived:  # dotted beam from hand to target
            for i, (x, y) in enumerate(line_cells(*hand, tx, ty)):
                if i % 2 == 0:
                    put(x, y, "·", "cyan")
            for j, ch in enumerate(f"← {self.target['label']}"):
                put(tx + 2 + j, ty, ch, "bold bright_cyan")
        self._astronaut(put, cos, now)
        seen = set()
        for i in range(1, ARM_LEN + 1):
            cell = (sx + round(cos * 2 * i), sy + round(sin * i))
            if cell in seen:
                continue
            seen.add(cell)
            ch = "│" if abs(sin) > .85 else "─" if abs(cos) > .85 else "╱" if cos * sin < 0 else "╲"
            put(*cell, "O" if i == ARM_LEN else ch, "bold white")

        for row in grid:
            line, run, style = Text(), "", None
            for ch, st in row:
                if st != style and run:
                    line.append(run, style or None)
                    run = ""
                style = st
                run += ch
            line.append(run, style or None)
            yield line

    def _moon(self, put):
        mx, my, r = self.moon
        rx, ph = 2 * r, self.phase
        waxing, c = ph["p"] < .5, ph["c"]
        for y in range(my - r, my + r + 1):
            for x in range(mx - rx, mx + rx + 1):
                nx, ny = (x - mx) / rx, (y - my) / r
                if nx * nx + ny * ny > 1:
                    continue
                edge = math.sqrt(max(0, 1 - ny * ny)) * c
                lit = nx > edge if waxing else nx < -edge
                put(x, y, "█" if lit else "░", "#f4eed6" if lit else "#2a3150")

    def _ground(self, put, w, h, now):
        for x in range(w):
            top = h - 2 + (1 if math.sin(x / 5) + math.sin(x / 2.3) > .7 else 0)
            for y in range(top, h):
                put(x, y, "▄" if y == top and top == h - 2 else "▓", "grey62" if y == top else "grey37")
        for cx in (int(w * .75), int(w * .08), int(w * .5)):
            put(cx, h - 1, "o", "grey23")

    def _astronaut(self, put, cos, now):
        face = -1 if cos < -.35 else 1 if cos > .35 else 0
        for j, row in enumerate(SPRITE):
            if j == 2:
                row = VISORS[face]
            for i, ch in enumerate(row):
                if ch == " ":
                    continue
                style = "bold white"
                if ch == "V":
                    ch, style = "█", "bright_blue"
                elif ch == "▪":
                    style = "bold red"
                elif i <= 1 and j in (4, 5):
                    style = "grey62"
                put(self.ax + i, self.ay + j, ch, style)
