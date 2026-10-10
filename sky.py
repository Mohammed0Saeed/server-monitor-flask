"""Animated terminal night sky: twinkling stars and the moon in its real current phase."""
import math
import random
import time
from datetime import datetime, timezone

from rich.text import Text

SYNODIC = 29.530588853
NEW_MOON_JD = 2451550.1  # new moon of 2000-01-06

PHASE_NAMES = [(.03, "New Moon"), (.22, "Waxing Crescent"), (.28, "First Quarter"), (.47, "Waxing Gibbous"),
               (.53, "Full Moon"), (.72, "Waning Gibbous"), (.78, "Last Quarter"), (.97, "Waning Crescent")]

def moon_phase(now=None):
    now = now or datetime.now(timezone.utc)
    jd = now.timestamp() / 86400 + 2440587.5
    age = (jd - NEW_MOON_JD) % SYNODIC
    p = age / SYNODIC
    c = math.cos(2 * math.pi * p)
    name = next((n for lim, n in PHASE_NAMES if p < lim), "New Moon")
    return {"p": p, "age": age, "c": c, "name": name, "lit": round((1 - c) / 2 * 100)}


class Sky:
    def __init__(self):
        self.size = None
        self.phase = moon_phase()
        self.phase_at = time.monotonic()

    @property
    def subtitle(self):
        ph = self.phase
        return f"{ph['name']} · {ph['lit']}% lit · day {ph['age']:.1f}"

    def _build(self, w, h):
        rng = random.Random(w * 1000 + h)
        self.size = (w, h)
        self.moon = (int(w * .68), int(h * .2), max(2, min(5, h // 7)))
        self.stars = [(rng.randrange(w), rng.randrange(max(1, h - 3)), rng.random() * 6.28, .8 + rng.random() * 2)
                      for _ in range(w * h // 30)]

    def __rich_console__(self, console, options):
        w = options.max_width
        h = options.height or options.max_height
        if (w, h) != self.size:
            self._build(w, h)
        now = time.monotonic()
        if now - self.phase_at > 3600:
            self.phase, self.phase_at = moon_phase(), now
        grid = [[(" ", "") for _ in range(w)] for _ in range(h)]

        def put(x, y, ch, style):
            if 0 <= x < w and 0 <= y < h:
                grid[y][x] = (ch, style)

        for x, y, ph, sp in self.stars:
            v = math.sin(now * sp + ph)
            put(x, y, "*" if v > .85 else "+" if v > .5 else "." if v > -.4 else " ", "bold white" if v > .85 else "white" if v > .3 else "grey50")
        self._moon(put)
        self._ground(put, w, h)

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

    def _ground(self, put, w, h):
        for x in range(w):
            top = h - 2 + (1 if math.sin(x / 5) + math.sin(x / 2.3) > .7 else 0)
            for y in range(top, h):
                put(x, y, "▄" if y == top and top == h - 2 else "▓", "grey62" if y == top else "grey37")
        for cx in (int(w * .75), int(w * .08), int(w * .5)):
            put(cx, h - 1, "o", "grey23")
