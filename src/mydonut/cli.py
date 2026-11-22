"""
mydonut: a configurable, animated, interactive ASCII donut for your terminal.

Examples
--------
    mydonut                                        # defaults
    mydonut --theme ocean --animation wobble,pulse
    mydonut --theme rainbow --color-by angle --cycle 0.2 --stars
    mydonut --charset blocks --animation tumble --size 1.3
    mydonut --list                                 # show every choice

While running, press `h` to toggle the help bar, `r` to reset, `q` to quit.
"""

from __future__ import annotations

import argparse
import copy
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass, field, fields

import numpy as np

from . import __version__

# =============================================================================
# Constants
# =============================================================================

CAMERA_DISTANCE = 5.0      # distance from viewer to the donut's centre
CHAR_ASPECT = 0.5          # terminal cells are ~2x taller than wide
REFERENCE_SCALE = 27.6     # projection scale at which "quality" is calibrated
TWO_PI = 2 * math.pi

# (tube_steps, ring_steps) = number of points sampled around the tube / ring
QUALITY = {"low": (60, 200), "medium": (90, 314), "high": (130, 440)}

# Terminal control sequences
ALT_SCREEN_ON, ALT_SCREEN_OFF = "\x1b[?1049h", "\x1b[?1049l"
HIDE_CURSOR, SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
CLEAR, HOME, RESET, DIM = "\x1b[2J", "\x1b[H", "\x1b[0m", "\x1b[2m"

# =============================================================================
# Choices: character sets, colour themes, colour modes
# =============================================================================

# Ordered dark -> bright. (No leading space: every lit point should be visible.)
CHARSETS = {
    "classic": ".,-~:;=!*#$@",
    "smooth": ".:-=+*#%@",
    "blocks": "░▒▓█",
    "dots": "·∙•●",
    "minimal": ".oO@",
    "binary": "01",
    "hash": ".+x#",
}
CHARSET_ARRAYS = {name: np.array(list(chars)) for name, chars in CHARSETS.items()}

# Gradient stops (RGB), dark -> bright. `cyclic` palettes wrap around smoothly.
THEMES: dict[str, tuple[list[tuple[int, int, int]], bool]] = {
    "mono":       ([], False),   # no colour, just characters
    "fire":       ([(70, 10, 0), (200, 40, 0), (255, 140, 0), (255, 230, 120), (255, 255, 230)], False),
    "sunset":     ([(40, 10, 90), (180, 40, 120), (255, 100, 80), (255, 180, 60), (255, 240, 160)], False),
    "ocean":      ([(0, 20, 70), (0, 80, 160), (0, 160, 200), (120, 230, 230), (230, 255, 255)], False),
    "forest":     ([(5, 40, 15), (20, 100, 40), (90, 170, 60), (190, 230, 110), (240, 255, 190)], False),
    "neon":       ([(60, 0, 120), (160, 0, 255), (255, 0, 200), (0, 255, 255), (255, 255, 255)], False),
    "ice":        ([(20, 30, 70), (60, 100, 180), (140, 200, 240), (220, 245, 255)], False),
    "matrix":     ([(0, 30, 0), (0, 110, 20), (0, 200, 50), (120, 255, 140), (220, 255, 220)], False),
    "strawberry": ([(90, 30, 60), (200, 80, 140), (255, 140, 190), (255, 210, 230), (255, 245, 250)], False),
    "gold":       ([(60, 40, 0), (170, 110, 10), (240, 190, 40), (255, 235, 140), (255, 252, 225)], False),
    "rainbow":    ([(255, 60, 60), (255, 200, 40), (80, 230, 80), (40, 220, 220),
                    (70, 100, 255), (220, 70, 255), (255, 60, 60)], True),
}

COLOR_MODES = {
    "light": "colour follows brightness (the classic look)",
    "depth": "colour follows distance from the viewer",
    "angle": "colour changes around the ring (rainbow ring)",
    "tube":  "colour changes around the tube's cross-section",
}

_LUT_CACHE: dict[str, np.ndarray] = {}


def theme_lut(name: str) -> np.ndarray:
    """256-entry RGB lookup table for a theme, built once and cached."""
    if name not in _LUT_CACHE:
        stops, _ = THEMES[name]
        arr = np.array(stops, dtype=float)
        xs = np.linspace(0, 1, len(arr))
        grid = np.linspace(0, 1, 256)
        _LUT_CACHE[name] = np.stack(
            [np.interp(grid, xs, arr[:, c]) for c in range(3)], axis=1
        )
    return _LUT_CACHE[name]


# =============================================================================
# Animations
#
# An animation is a function that adjusts a Pose (rotation angles, scale,
# shape, screen offset) as a function of time `t`. Several can be combined with
# commas (e.g. "spin,pulse,orbit"); their effects add up.
# =============================================================================

@dataclass
class Pose:
    ax: float = 0.0       # rotation around X (radians)
    ay: float = 0.0       # rotation around Y
    az: float = 0.0       # rotation around Z
    scale: float = 1.0    # size multiplier
    tube: float = 1.0     # tube radius
    ring: float = 2.0     # ring radius (hole size)
    ox: float = 0.0       # horizontal offset, fraction of terminal width
    oy: float = 0.0       # vertical offset, fraction of terminal height


def _tri(x: float) -> float:
    """Triangle wave in [-1, 1] with period 1 (0 at x = 0)."""
    return 4 * abs((x + 0.25) % 1.0 - 0.5) - 1


ANIMATIONS = {
    "static": (lambda p, t: (setattr(p, "ax", p.ax + 0.9), setattr(p, "az", p.az + 0.35)),
               "fixed tilt, no motion"),
    "spin":   (lambda p, t: (setattr(p, "ax", p.ax + 1.2 * t), setattr(p, "az", p.az + 0.6 * t)),
               "the classic two-axis spin"),
    "tumble": (lambda p, t: (setattr(p, "ax", p.ax + 1.3 * t), setattr(p, "ay", p.ay + 0.9 * t),
                             setattr(p, "az", p.az + 0.5 * t)),
               "chaotic three-axis tumble"),
    "flip":   (lambda p, t: (setattr(p, "ax", p.ax + 1.4 * t), setattr(p, "az", p.az + 0.35)),
               "end-over-end flipping"),
    "roll":   (lambda p, t: (setattr(p, "ax", p.ax + 1.0), setattr(p, "az", p.az + 1.0 * t)),
               "tilted donut rolling like a wheel"),
    "wobble": (lambda p, t: (setattr(p, "ax", p.ax + 0.9 + 0.6 * math.sin(1.4 * t)),
                             setattr(p, "az", p.az + 0.5 * math.sin(0.9 * t))),
               "gentle rocking back and forth"),
    "sway":   (lambda p, t: (setattr(p, "ax", p.ax + 1.0), setattr(p, "ay", p.ay + 0.9 * math.sin(1.1 * t)),
                             setattr(p, "az", p.az + 0.3 * math.sin(0.7 * t))),
               "tilted donut swinging side to side"),
    "pulse":  (lambda p, t: setattr(p, "scale", p.scale * (1 + 0.14 * math.sin(3.0 * t))),
               "size throbs like a heartbeat"),
    "morph":  (lambda p, t: setattr(p, "tube", p.tube * (1 + 0.4 * math.sin(1.6 * t))),
               "donut gets fatter and thinner"),
    "orbit":  (lambda p, t: (setattr(p, "ox", p.ox + 0.2 * math.cos(0.8 * t)),
                             setattr(p, "oy", p.oy + 0.15 * math.sin(0.8 * t))),
               "travels in a circle around the screen"),
    "bounce": (lambda p, t: (setattr(p, "ox", p.ox + 0.18 * _tri(0.18 * t)),
                             setattr(p, "oy", p.oy + 0.14 * _tri(0.23 * t))),
               "bounces off the edges like a DVD logo"),
}


# =============================================================================
# Settings (everything the user can choose)
# =============================================================================

@dataclass
class Settings:
    theme: str = "fire"
    charset: str = "classic"
    animations: list[str] = field(default_factory=lambda: ["spin"])
    color_by: str = "light"
    speed: float = 1.0
    size: float = 1.0
    thickness: float = 1.0      # tube radius
    ring: float = 2.0           # ring radius (bigger = bigger hole)
    fps: int = 30
    quality: str = "medium"
    light_az: float = 0.0       # light direction, degrees
    light_el: float = 45.0
    light_spin: float = 0.0     # radians/second the light orbits
    cycle: float = 0.0          # palette cycles per second
    stars: bool = False
    hud: bool = True
    paused: bool = False


LIMITS = {
    "speed": (0.1, 6.0), "size": (0.3, 2.5), "thickness": (0.25, 1.6),
    "ring": (1.0, 3.2), "fps": (5, 120),
}


def clamp_setting(s: Settings, name: str) -> None:
    lo, hi = LIMITS[name]
    setattr(s, name, min(hi, max(lo, getattr(s, name))))


# =============================================================================
# Geometry
# =============================================================================

class Torus:
    """A torus as a dense cloud of surface points plus their normals."""

    def __init__(self, quality: str, factor: float = 1.0) -> None:
        tube_steps, ring_steps = QUALITY[quality]
        self.quality, self.factor = quality, factor
        theta = np.linspace(0, TWO_PI, int(tube_steps * factor), endpoint=False)  # around the tube
        phi = np.linspace(0, TWO_PI, int(ring_steps * factor), endpoint=False)    # around the ring
        theta, phi = (a.ravel() for a in np.meshgrid(theta, phi))
        self.theta, self.phi = theta, phi
        self.cos_t, self.sin_t = np.cos(theta), np.sin(theta)
        self.cos_p, self.sin_p = np.cos(phi), np.sin(phi)
        # The outward normal of a torus doesn't depend on its radii.
        self.normals = np.stack(
            [self.cos_t * self.cos_p, self.sin_t, -self.cos_t * self.sin_p], axis=1
        )

    def points(self, tube: float, ring: float) -> np.ndarray:
        offset = ring + tube * self.cos_t
        return np.stack(
            [offset * self.cos_p, tube * self.sin_t, -offset * self.sin_p], axis=1
        )


def rotation_matrix(ax: float, ay: float, az: float) -> np.ndarray:
    """Rotate around X, then Y, then Z."""
    cx, sx, cy, sy, cz, sz = (f(a) for a in (ax, ay, az) for f in (math.cos, math.sin))
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def light_vector(s: Settings, t: float) -> np.ndarray:
    """Unit vector pointing from the donut toward the light."""
    az = math.radians(s.light_az) + s.light_spin * t
    el = math.radians(s.light_el)
    return np.array([math.cos(el) * math.sin(az), math.sin(el), -math.cos(el) * math.cos(az)])


def fit_scale(width: int, height: int) -> float:
    """Projection scale that fits the default donut to the terminal."""
    return min(0.375 * width, 1.15 * height)


def density_factor(s: Settings, width: int, height: int) -> float:
    """Sample more points on big donuts so the surface has no gaps."""
    ratio = fit_scale(width, height) * s.size / REFERENCE_SCALE
    return min(2.0, max(1.0, math.ceil(ratio * 2) / 2))


# =============================================================================
# Rendering
# =============================================================================

def compute_pose(s: Settings, t: float) -> Pose:
    pose = Pose(tube=s.thickness, ring=s.ring)
    for name in s.animations:
        ANIMATIONS[name][0](pose, t)
    return pose


def render_cells(torus: Torus, s: Settings, t: float, width: int, height: int):
    """Rasterise the donut. Returns (chars, rgb); rgb is None for the mono theme."""
    pose = compute_pose(s, t)
    rot = rotation_matrix(pose.ax, pose.ay, pose.az)
    pts = torus.points(pose.tube, pose.ring) @ rot.T
    nrm = torus.normals @ rot.T

    # Perspective projection: nearer points (smaller z) appear larger.
    inv_z = 1.0 / np.maximum(pts[:, 2] + CAMERA_DISTANCE, 0.5)
    scale = fit_scale(width, height) * s.size * pose.scale
    cx = width / 2 + pose.ox * width
    cy = height / 2 + pose.oy * height
    col = np.floor(cx + scale * pts[:, 0] * inv_z).astype(np.int64)
    row = np.floor(cy - scale * CHAR_ASPECT * pts[:, 1] * inv_z).astype(np.int64)

    # Lighting: brightness = how directly each surface faces the light.
    brightness = nrm @ light_vector(s, t)

    chars = np.full(width * height, " ", dtype="<U1")
    use_color = s.theme != "mono"
    rgb = np.zeros((width * height, 3), dtype=np.uint8) if use_color else None

    keep = np.flatnonzero(
        (brightness > 0) & (col >= 0) & (col < width) & (row >= 0) & (row < height)
    )
    if keep.size == 0:
        return chars, rgb

    # Z-buffer: of all points landing in one cell, only the nearest survives.
    cell = row[keep] * width + col[keep]
    order = np.lexsort((inv_z[keep], cell))          # by cell, then by nearness
    cell_sorted = cell[order]
    is_last = np.append(cell_sorted[1:] != cell_sorted[:-1], True)
    win = keep[order[is_last]]                       # index of the winning point per cell
    win_cells = cell_sorted[is_last]

    # Character from brightness.
    b = brightness[win]
    glyphs = CHARSET_ARRAYS[s.charset]
    levels = np.minimum((b * len(glyphs)).astype(int), len(glyphs) - 1)
    chars[win_cells] = glyphs[levels]

    if use_color:
        # Pick a 0..1 value for each cell according to the colour mode.
        shade = None
        if s.color_by == "light":
            v = b
        else:
            if s.color_by == "depth":
                extent = pose.ring + pose.tube
                near = 1.0 / max(CAMERA_DISTANCE - extent, 0.5)
                far = 1.0 / (CAMERA_DISTANCE + extent)
                v = (inv_z[win] - far) / (near - far)
            elif s.color_by == "angle":
                v = torus.phi[win] / TWO_PI
            else:  # "tube"
                v = torus.theta[win] / TWO_PI
            shade = 0.35 + 0.65 * b                  # keep some 3D shading
        v = np.clip(v, 0.0, 1.0)

        # Animated palette shift: wrap for cyclic themes, ping-pong otherwise.
        shift = s.cycle * t
        if shift:
            if THEMES[s.theme][1]:
                v = (v + shift) % 1.0
            else:
                m = (v + shift) % 2.0
                v = np.where(m <= 1.0, m, 2.0 - m)

        colors = theme_lut(s.theme)[(v * 255).astype(int)]
        if shade is not None:
            colors = colors * shade[:, None]
        rgb[win_cells] = colors.astype(np.uint8)

    return chars, rgb


class Starfield:
    """Twinkling background stars that only fill empty cells."""

    def __init__(self) -> None:
        self.size: tuple[int, int] | None = None

    def apply(self, chars, rgb, width: int, height: int, t: float) -> None:
        if self.size != (width, height):
            rng = np.random.default_rng(7)
            n = max(1, width * height // 45)
            self.cells = rng.choice(width * height, size=n, replace=False)
            self.glyphs = rng.choice(np.array([".", ".", "·", "*", "+"]), size=n)
            self.phase = rng.uniform(0, TWO_PI, n)
            self.base = rng.uniform(70, 170, n)
            self.size = (width, height)
        free = chars[self.cells] == " "
        cells = self.cells[free]
        chars[cells] = self.glyphs[free]
        if rgb is not None:
            g = self.base[free] * (0.55 + 0.45 * np.sin(2.0 * t + self.phase[free]))
            rgb[cells] = np.stack([g, g, g * 1.1], axis=1).clip(0, 255).astype(np.uint8)


def compose(chars, rgb, width: int, height: int) -> str:
    """Turn the cell grids into a printable string (run-length colour codes)."""
    grid = chars.reshape(height, width).tolist()
    if rgb is None:
        return "\n".join("".join(r) for r in grid)

    quant = ((rgb >> 2) << 2).reshape(height, width, 3).tolist()  # fewer colour changes
    lines = []
    for char_row, rgb_row in zip(grid, quant):
        out, prev = [], None
        for ch, c in zip(char_row, rgb_row):
            if ch == " ":
                out.append(" ")
                continue
            if c != prev:
                out.append(f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m")
                prev = c
            out.append(ch)
        lines.append("".join(out))
    return "\n".join(lines) + RESET


HUD_KEYS = ("q quit  space pause  ↑↓ speed  ←→ size  t thickness  o hole  c theme  "
            "a anim  s chars  b color-by  l light  u cycle  h hud  r reset")


def hud_lines(s: Settings, fps: float, width: int) -> list[str]:
    # Most important info first, so narrow terminals cut off the least useful part.
    parts = ["[PAUSED]"] if s.paused else []
    parts += [s.theme, "+".join(s.animations), s.charset, f"by {s.color_by}",
              f"{s.speed:.2f}x", f"size {s.size:.2f}", f"thick {s.thickness:.2f}",
              f"hole {s.ring:.2f}", f"{fps:.0f}fps"]
    status = " " + "  ".join(parts)
    return [f"{DIM}{text[:width].ljust(width)}{RESET}" for text in (status, " " + HUD_KEYS)]


# =============================================================================
# Keyboard input (non-blocking, Unix + Windows)
# =============================================================================

_ARROWS = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}


def _parse_unix_keys(raw: str) -> list[str]:
    """Split raw terminal input into keys, decoding arrow-key escape sequences."""
    keys, i = [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\x1b":
            if i + 1 < len(raw) and raw[i + 1] in "[O":
                j = i + 2
                while j < len(raw) and not ("@" <= raw[j] <= "~"):
                    j += 1
                if j < len(raw) and raw[j] in _ARROWS:
                    keys.append(_ARROWS[raw[j]])
                i = j + 1
            else:
                i += 1                                # lone ESC: ignore
        else:
            keys.append(ch)
            i += 1
    return keys


class Keyboard:
    """Context manager for reading single keypresses without Enter."""

    def __enter__(self) -> "Keyboard":
        self.enabled = sys.stdin.isatty()
        self._old = None
        if self.enabled and os.name != "nt":
            import termios
            import tty
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *exc) -> None:
        if self._old is not None:
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def poll(self) -> list[str]:
        if not self.enabled:
            return []
        if os.name == "nt":
            import msvcrt
            keys = []
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    code = {"H": "UP", "P": "DOWN", "M": "RIGHT", "K": "LEFT"}.get(msvcrt.getwch())
                    if code:
                        keys.append(code)
                else:
                    keys.append(ch)
            return keys
        import select
        raw = ""
        while select.select([self._fd], [], [], 0)[0]:
            data = os.read(self._fd, 64)
            if not data:
                break
            raw += data.decode("utf-8", "ignore")
        return _parse_unix_keys(raw)


def _cycle(options: list[str], current: str, step: int) -> str:
    return options[(options.index(current) + step) % len(options)]


def handle_key(key: str, s: Settings, initial: Settings) -> bool:
    """Apply one keypress to the settings. Returns True if the user wants to quit."""
    if key in ("q", "Q", "\x03"):
        return True
    if key == " ":
        s.paused = not s.paused
    elif key in ("UP", "+", "="):
        s.speed *= 1.15
        clamp_setting(s, "speed")
    elif key in ("DOWN", "-", "_"):
        s.speed /= 1.15
        clamp_setting(s, "speed")
    elif key in ("RIGHT", "]"):
        s.size *= 1.08
        clamp_setting(s, "size")
    elif key in ("LEFT", "["):
        s.size /= 1.08
        clamp_setting(s, "size")
    elif key in ("t", "T"):
        s.thickness += 0.05 if key == "t" else -0.05
        clamp_setting(s, "thickness")
    elif key in ("o", "O"):
        s.ring += 0.1 if key == "o" else -0.1
        clamp_setting(s, "ring")
    elif key in ("c", "C"):
        s.theme = _cycle(list(THEMES), s.theme, 1 if key == "c" else -1)
    elif key in ("a", "A"):
        names = list(ANIMATIONS)
        current = s.animations[0] if len(s.animations) == 1 else names[0]
        s.animations = [_cycle(names, current, 1 if key == "a" else -1)]
    elif key in ("s", "S"):
        s.charset = _cycle(list(CHARSETS), s.charset, 1 if key == "s" else -1)
    elif key in ("b", "B"):
        s.color_by = _cycle(list(COLOR_MODES), s.color_by, 1 if key == "b" else -1)
    elif key == "l":
        s.light_spin = 0.0 if s.light_spin else 1.0
    elif key == "u":
        s.cycle = 0.0 if s.cycle else 0.15
    elif key == "h":
        s.hud = not s.hud
    elif key == "r":
        for f in fields(initial):
            setattr(s, f.name, copy.deepcopy(getattr(initial, f.name)))
    return False


# =============================================================================
# Main loop
# =============================================================================

def run(s: Settings) -> None:
    initial = copy.deepcopy(s)
    stars = Starfield()
    torus = Torus(s.quality, 1.0)
    out = sys.stdout
    t, fps_avg = 0.0, float(s.fps)
    last_layout = None
    last_tick = time.perf_counter()

    out.write(ALT_SCREEN_ON + HIDE_CURSOR + CLEAR)
    try:
        with Keyboard() as keyboard:
            while True:
                frame_start = time.perf_counter()
                dt = min(frame_start - last_tick, 0.1)
                last_tick = frame_start
                fps_avg = 0.95 * fps_avg + 0.05 * (1.0 / max(dt, 1e-3))

                for key in keyboard.poll():
                    if handle_key(key, s, initial):
                        return
                if not s.paused:
                    t += dt * s.speed

                cols, lines = shutil.get_terminal_size((80, 24))
                width = max(10, cols - 1)                       # avoid last-column wrap
                height = max(5, lines - (2 if s.hud else 0))
                if (cols, lines, s.hud) != last_layout:         # resize / HUD toggle
                    out.write(CLEAR)
                    last_layout = (cols, lines, s.hud)

                factor = density_factor(s, width, height)
                if factor != torus.factor:
                    torus = Torus(s.quality, factor)

                chars, rgb = render_cells(torus, s, t, width, height)
                if s.stars:
                    stars.apply(chars, rgb, width, height, t)
                frame = compose(chars, rgb, width, height)
                if s.hud:
                    frame += "\n" + "\n".join(hud_lines(s, fps_avg, width))
                out.write(HOME + frame + RESET)
                out.flush()

                time.sleep(max(0.0, 1.0 / s.fps - (time.perf_counter() - frame_start)))
    finally:
        out.write(RESET + SHOW_CURSOR + ALT_SCREEN_OFF)
        out.flush()


# =============================================================================
# Command line
# =============================================================================

def print_choices() -> None:
    print("themes:     ", ", ".join(THEMES))
    print("charsets:   ", ", ".join(f"{k} ({v})" for k, v in CHARSETS.items()))
    print("color-by:")
    for name, desc in COLOR_MODES.items():
        print(f"  {name:<8} {desc}")
    print("animations (combine with commas, e.g. spin,pulse,orbit):")
    for name, (_, desc) in ANIMATIONS.items():
        print(f"  {name:<8} {desc}")
    print("quality:    ", ", ".join(QUALITY))


def parse_args(argv: list[str] | None = None) -> Settings:
    d = Settings()
    if os.environ.get("NO_COLOR"):
        d.theme = "mono"
    p = argparse.ArgumentParser(
        prog="mydonut",
        description="Animated, customisable ASCII donut. Press h while running for key help.",
    )
    p.add_argument("--theme", choices=list(THEMES), default=d.theme, help="colour theme")
    p.add_argument("--charset", choices=list(CHARSETS), default=d.charset, help="characters used for shading")
    p.add_argument("--animation", default="spin", metavar="NAMES",
                   help="comma-separated animations, e.g. spin,pulse (see --list)")
    p.add_argument("--color-by", choices=list(COLOR_MODES), default=d.color_by, help="what drives the colour")
    p.add_argument("--speed", type=float, default=d.speed, help="animation speed multiplier (0.1-6)")
    p.add_argument("--size", type=float, default=d.size, help="size multiplier (0.3-2.5)")
    p.add_argument("--thickness", type=float, default=d.thickness, help="tube radius (0.25-1.6)")
    p.add_argument("--hole", type=float, default=d.ring, help="ring radius; bigger = bigger hole (1.0-3.2)")
    p.add_argument("--fps", type=int, default=d.fps, help="target frames per second (5-120)")
    p.add_argument("--quality", choices=list(QUALITY), default=d.quality, help="surface sampling density")
    p.add_argument("--light-azimuth", type=float, default=d.light_az, help="light direction left/right, degrees")
    p.add_argument("--light-elevation", type=float, default=d.light_el, help="light height, degrees")
    p.add_argument("--light-spin", type=float, default=d.light_spin, help="light orbit speed (rad/s)")
    p.add_argument("--cycle", type=float, default=d.cycle, help="palette cycles per second, e.g. 0.15")
    p.add_argument("--stars", action="store_true", help="twinkling star background")
    p.add_argument("--no-hud", action="store_true", help="start with the help bar hidden")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--list", action="store_true", help="list all themes, charsets and animations, then exit")
    a = p.parse_args(argv)

    if a.list:
        print_choices()
        sys.exit(0)

    names = [n.strip() for n in a.animation.split(",") if n.strip()]
    bad = [n for n in names if n not in ANIMATIONS]
    if bad or not names:
        p.error(f"unknown animation(s) {bad or a.animation!r}; run with --list to see choices")

    s = Settings(
        theme=a.theme, charset=a.charset, animations=names, color_by=a.color_by,
        speed=a.speed, size=a.size, thickness=a.thickness, ring=a.hole, fps=a.fps,
        quality=a.quality, light_az=a.light_azimuth, light_el=a.light_elevation,
        light_spin=a.light_spin, cycle=a.cycle, stars=a.stars, hud=not a.no_hud,
    )
    for name in LIMITS:
        clamp_setting(s, name)
    return s


def main(argv: list[str] | None = None) -> None:
    try:
        settings = parse_args(argv)
        if os.name == "nt":
            os.system("")      # enables ANSI escape codes in the Windows console
        run(settings)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:    # e.g. `mydonut --list | head`
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass


if __name__ == "__main__":
    main()
