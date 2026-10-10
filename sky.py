"""Animated terminal starry night: twinkling stars, the moon in its real current phase, and random meteors."""
import math
import random
import time
from datetime import datetime, timezone

from rich.text import Text

SYNODIC = 29.530588853
NEW_MOON_JD = 2451550.1  # new moon of 2000-01-06

PHASE_NAMES = [(.03, "New Moon"), (.22, "Waxing Crescent"), (.28, "First Quarter"), (.47, "Waxing Gibbous"),
               (.53, "Full Moon"), (.72, "Waning Gibbous"), (.78, "Last Quarter"), (.97, "Waning Crescent")]

SKY_TOP, SKY_BOT = (2, 3, 12), (26, 30, 70)
STAR_TINTS = [(255, 255, 255), (200, 220, 255), (255, 240, 200), (255, 210, 190)]


def moon_phase(now=None):
    now = now or datetime.now(timezone.utc)
    jd = now.timestamp() / 86400 + 2440587.5
    age = (jd - NEW_MOON_JD) % SYNODIC
    p = age / SYNODIC
    c = math.cos(2 * math.pi * p)
    name = next((n for lim, n in PHASE_NAMES if p < lim), "New Moon")
    return {"p": p, "age": age, "c": c, "name": name, "lit": round((1 - c) / 2 * 100)}


def mix(a, b, t):
    t = min(max(t, 0), 1)
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rgb(c):
    return f"rgb({c[0]},{c[1]},{c[2]})"


class Sky:
    def __init__(self):
        self.size = None
        self.phase = moon_phase()
        self.phase_at = time.monotonic()
        self.meteors = []
        self.next_meteor = 0

    @property
    def subtitle(self):
        ph = self.phase
        return f"{ph['name']} · {ph['lit']}% lit · day {ph['age']:.1f}"

    def _build(self, w, h):
        rng = random.Random(w * 1000 + h)
        self.size = (w, h)
        self.r = max(2, min(5, h // 7))
        self.moon = (int(w * .68), int(h * .2))
        self.stars = [(rng.randrange(w), rng.randrange(max(1, h - 3)), rng.random() * 6.28, .8 + rng.random() * 2.2,
                       rng.choice(STAR_TINTS)) for _ in range(w * h // 22)]
        self.meteors = []

    def _spawn(self, now, w, h):
        self.meteors.append({"x": random.uniform(w * .2, w * 1.1), "y": random.uniform(0, h * .35), "t0": now,
                             "speed": random.uniform(25, 55), "len": random.randrange(6, 14),
                             "slope": random.uniform(.35, .6)})
        self.next_meteor = now + random.uniform(.8, 4.5)

    def __rich_console__(self, console, options):
        w = options.max_width
        h = options.height or options.max_height
        if (w, h) != self.size:
            self._build(w, h)
        now = time.monotonic()
        if now - self.phase_at > 3600:
            self.phase, self.phase_at = moon_phase(), now
        if now >= self.next_meteor:
            self._spawn(now, w, h)

        rows = [mix(SKY_TOP, SKY_BOT, (y / max(1, h - 1)) ** 1.6) for y in range(h)]
        grid = [[(" ", None, None) for _ in range(w)] for _ in range(h)]

        def put(x, y, ch, fg, bg=None):
            if 0 <= x < w and 0 <= y < h:
                grid[y][x] = (ch, fg, bg)

        for x, y, ph, sp, tint in self.stars:
            v = math.sin(now * sp + ph)
            lvl = 1 if v > .5 else .65 if v > -.4 else .4
            put(x, y, "*" if v > .85 else "+" if v > .5 else "." if v > -.4 else "·", mix((0, 0, 0), tint, lvl))

        self._moon(put, rows)
        self._meteors(put, w, h, now)
        self._ground(put, w, h)

        for y, row in enumerate(grid):
            line, run, key = Text(), "", None
            for ch, fg, bg in row:
                k = (fg, bg)
                if k != key and run:
                    line.append(run, self._style(key, rows[y]))
                    run = ""
                key = k
                run += ch
            line.append(run, self._style(key, rows[y]))
            yield line

    @staticmethod
    def _style(key, row_bg):
        fg, bg = key
        return f"{rgb(fg) if fg else 'white'} on {rgb(bg or row_bg)}"

    def _moon(self, put, rows):
        cx, cy = self.moon
        r, rx, ph = self.r, 2 * self.r, self.phase
        waxing, c = ph["p"] < .5, ph["c"]
        for y in range(cy - r - 2, cy + r + 3):  # soft glow around the moon
            for x in range(cx - rx - 4, cx + rx + 5):
                dist = math.hypot((x - cx) / 2, y - cy) / (r + 2)
                if dist < 1 and 0 <= y < len(rows):
                    put(x, y, " ", None, mix(rows[y], (200, 210, 255), .2 * (1 - dist) ** 1.5))
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - rx, cx + rx + 1):
                nx, ny = (x - cx) / rx, (y - cy) / r
                if nx * nx + ny * ny > 1:
                    continue
                edge = math.sqrt(max(0, 1 - ny * ny)) * c
                lit = nx > edge if waxing else nx < -edge
                put(x, y, "█" if lit else "░", (244, 238, 214) if lit else (42, 49, 80))

    def _meteors(self, put, w, h, now):
        alive = []
        for m in self.meteors:
            dist = (now - m["t0"]) * m["speed"]
            hx, hy = m["x"] - dist, m["y"] + dist * m["slope"]
            if hx < -m["len"] or hy > h:
                continue
            alive.append(m)
            for i in range(m["len"]):
                fade = 1 - i / m["len"]
                x, y = round(hx + i), round(hy - i * m["slope"])
                put(x, y, "*" if i == 0 else "-" if i < 3 else "·", mix((20, 24, 50), (255, 250, 230), fade))
        self.meteors = alive

    def _ground(self, put, w, h):
        for x in range(w):
            ridge = h - 3 + (1 if math.sin(x / 7) + math.sin(x / 2.9) > .6 else 0) + (1 if math.sin(x / 13) > .5 else 0)
            for y in range(ridge, h):
                put(x, y, "█", (14, 16, 30) if y > ridge else (30, 34, 58))
