<img width="1672" height="941" alt="Neon ASCII Donut Terminal Banner" src="https://github.com/user-attachments/assets/f7a34dc0-727a-49f3-8e3d-080a4deb38e5" /># mydonut

<p align="center">
  <img src="Neon ASCII Donut Terminal Banner.png" alt="mydonut — a customizable ASCII donut for your terminal" width="100%">
</p>


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

## Product Hunt

<div style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif; border: 1px solid rgb(224, 224, 224); border-radius: 12px; padding: 20px; max-width: 500px; background: rgb(255, 255, 255); box-shadow: rgba(0, 0, 0, 0.05) 0px 2px 8px;">
  <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
    <img alt="mydonut" style="width: 64px; height: 64px; border-radius: 8px; object-fit: cover; flex-shrink: 0;" src="https://ph-files.imgix.net/544d0b7f-5cf5-4879-bd09-7fbd1a6ba244.png?auto=compress,format&amp;codec=mozjpeg&amp;cs=strip&amp;fit=crop&amp;h=80&amp;w=80">
    <div style="flex: 1 1 0%; min-width: 0px;">
      <h3 style="margin: 0px; font-size: 18px; font-weight: 600; color: rgb(26, 26, 26); line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">mydonut</h3>
      <p style="margin: 4px 0px 0px; font-size: 14px; color: rgb(102, 102, 102); line-height: 1.4; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -moz-box-orient: vertical;">fun to use and visually attractive!</p>
    </div>
  </div>
  <a href="https://www.producthunt.com/products/mydonut?embed=true&amp;utm_source=embed&amp;utm_medium=post_embed" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 4px; margin-top: 12px; padding: 8px 16px; background: rgb(255, 97, 84); color: rgb(255, 255, 255); text-decoration: none; border-radius: 9999px; font-size: 16px; font-weight: 600; line-height: 1.5;">Check it out on Product Hunt →</a>
</div>
