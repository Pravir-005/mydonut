# mydonut

A configurable, animated, interactive ASCII donut for your terminal.
Themes, animations, character sets, live keyboard controls, and a twinkling
star background, all rendered with NumPy.

## Install

```bash
# Recommended: isolated install, `mydonut` lands on your PATH
pipx install mydonut

# or plain pip
pip install mydonut

# Arch Linux (AUR)
yay -S mydonut
```

Run it:

```bash
mydonut
mydonut --theme rainbow --color-by angle --cycle 0.2 --stars
mydonut --theme ocean --animation wobble,pulse --charset blocks
mydonut --list          # every theme, animation and charset
```

## Controls

| Key | Action | Key | Action |
|---|---|---|---|
| `↑` `↓` | speed | `c` / `C` | theme |
| `←` `→` | size | `a` / `A` | animation |
| `t` / `T` | thickness | `s` / `S` | characters |
| `o` / `O` | hole size | `b` / `B` | color mode |
| `l` | light spin | `u` | color cycling |
| `space` | pause | `h` | toggle help bar |
| `r` | reset | `q` | quit |

## Options

| Flag | Meaning |
|---|---|
| `--theme` | `mono fire sunset ocean forest neon ice matrix strawberry gold rainbow` |
| `--color-by` | `light depth angle tube` |
| `--animation` | comma-separated: `static spin tumble flip roll wobble sway pulse morph orbit bounce` |
| `--charset` | `classic smooth blocks dots minimal binary hash` |
| `--speed` `--size` | multipliers |
| `--thickness` `--hole` | tube radius / ring radius |
| `--light-azimuth` `--light-elevation` `--light-spin` | light direction and orbit |
| `--cycle` | palette cycles per second |
| `--stars` | star background |
| `--quality` | `low medium high` |
| `--fps` | target frame rate |
| `--no-hud` | start with the help bar hidden |

Set `NO_COLOR=1` to default to the monochrome theme.

## How it works

1. A torus is sampled as ~28k surface points, each with a normal vector.
2. Points and normals are rotated by a matrix built from the current animation.
3. Perspective projection maps them onto the character grid.
4. A depth buffer keeps the nearest point per cell.
5. Brightness (normal · light direction) picks the character and colour.

Inspired by Andy Sloane's classic `donut.c`.

## Development

```bash
git clone https://github.com/Pravir-005/mydonut
cd mydonut
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
