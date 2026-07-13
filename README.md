# palette-manager

A terminal UI for managing 16-color palettes using the [base16](https://github.com/base16-project/base16) naming convention. Built for people who want a single source of truth for colors across their desktop — window manager, terminal, shell prompt, editor — without hand-editing config files.

## How it works

```
                        ┌─────────────────────────────┐
                        │       palettes.yaml          │  your palettes
                        │       (user-defined)         │  (editable)
                        └──────────┬──────────────────┘
                                   │
  base16-schemes.yaml              │
  (auto-downloaded from       palette-manager
   tinted-theming/schemes)         │
  325+ read-only schemes      merges + renders TUI
                                   │
                            active palette
                                   │
                        writes 32 color keys to
                        theme_file (base16 + use-names)
                                   │
                        runs apply_command
                        (e.g. chezmoi apply, hyprctl reload)
```

Palette-manager stores palettes in a YAML file and optionally writes the active palette's colors to a separate theme file, then runs a shell command. The specific integration (chezmoi, hyprland, custom script) is defined in a config file.

### Dual naming system

Every color has two names — templates and configs can use either:

| base16 name | use-name (default) | Typical role |
|---|---|---|
| `base00` | `bg` | darkest background |
| `base01` | `surface` | card/panel surface |
| `base02` | `selection` | selection background |
| `base03` | `muted` | comments, dim text |
| `base04` | `border` | inactive borders, separators |
| `base05` | `text` | primary foreground |
| `base06` | `shadow` | shadow color |
| `base07` | `accent` | highlights, active elements |
| `base08` | `red` | errors, ANSI 1 |
| `base09` | `orange` | warnings, ANSI 9 |
| `base0A` | `yellow` | warnings, ANSI 3 |
| `base0B` | `green` | success, diff added, ANSI 2 |
| `base0C` | `cyan` | secondary accent, ANSI 6 |
| `base0D` | `blue` | info, diff changed, ANSI 4 |
| `base0E` | `magenta` | diagnostic hint, ANSI 5 |
| `base0F` | `urgent` | attention/urgent, ANSI 15 |

The base16 names (`base00`–`base0F`) never change. The use-names are customizable aliases — rename them in the TUI and palette-manager writes both sets of keys to the theme file:

```yaml
# theme.yaml (auto-generated)
theme:
  colors:
    base00: "#11111b"   # base16 name (stable)
    # ...
    bg: "#11111b"        # use-name alias (customizable)
    # ...
```

Templates reference whichever name is more readable:

```
{{ .theme.colors.base00 }}     # always works
{{ .theme.colors.bg }}         # works if "bg" is the use-name for base00
```

## Install

```bash
uv tool install git+https://github.com/dylanrussellmd/palette-manager
```

## Quick start

```bash
palette-manager --init    # create default config at ~/.config/palette-manager/config.yaml
palette-manager           # launch the TUI
```

Without any config, palette-manager stores palettes in `~/.config/palette-manager/palettes.yaml` and does nothing on apply (just marks the palette as active).

## Configuration

Edit `~/.config/palette-manager/config.yaml`:

```yaml
# Where to store palettes (created automatically if missing)
palettes_file: ~/.config/palette-manager/palettes.yaml

# Where to write the active palette's colors on apply.
# Set to null to skip writing.
theme_file: null

# Dotted path within the theme file to write colors under.
# e.g. "theme.colors" writes to doc["theme"]["colors"]
# Leave null to write at the root level.
theme_path: null

# palette-manager writes all 16 base16 keys (base00–base0F) plus
# their use-name aliases (bg, surface, text, etc.) from the `uses`
# mapping in palettes.yaml. No need to list keys here.

# Shell command to run after writing colors on apply.
# Set to null to skip.
apply_command: null
```

### Example: chezmoi + niri + Quickshell + kitty + starship

```yaml
palettes_file: ~/.local/share/chezmoi/.chezmoidata/palettes.yaml
theme_file: ~/.local/share/chezmoi/.chezmoidata/theme.yaml
theme_path: theme.colors
apply_command: chezmoi apply
```

With this setup, `palette-manager` writes colors to `theme.yaml`, then `chezmoi apply` renders all template files that reference `{{ .theme.colors.* }}` — window manager config, terminal config, shell prompt, panel widgets, etc.

### Example: Hyprland

```yaml
palettes_file: ~/.config/palette-manager/palettes.yaml
theme_file: ~/.config/hypr/colors.conf
theme_path: null
apply_command: hyprctl reload
```

### Example: custom script

```yaml
palettes_file: ~/.config/palette-manager/palettes.yaml
theme_file: ~/.config/palette-manager/colors.yaml
theme_path: null
apply_command: ~/.config/palette-manager/apply.sh
```

### Example: standalone (no apply)

```yaml
palettes_file: ~/.config/palette-manager/palettes.yaml
theme_file: null
theme_path: null
apply_command: null
```

## Usage

```bash
palette-manager              # launch the TUI
palette-manager --check      # list palettes from CLI
palette-manager --apply      # apply active palette (non-interactive)
palette-manager --init       # create default config file
palette-manager --update-base16  # force-update base16 scheme cache
palette-manager --config /path/to/config.yaml   # use a specific config
```

### List screen

| Key | Action |
|---|---|
| `↑`/`↓` or `k`/`j` | Navigate palettes |
| `e` or `Enter` | Edit palette (duplicates if built-in 🔒) |
| `n` | New palette |
| `d` | Delete palette (user palettes only) |
| `u` | Edit use-name mapping |
| `a` | Activate + apply |
| `q` | Quit |

### Edit screen

| Key | Action |
|---|---|
| `Tab` | Move between fields |
| `Ctrl+A` | Autofill from 3 seed colors |
| `Ctrl+S` or Save | Save |
| `Esc` or Cancel | Discard |

The edit screen shows all 16 colors with their base16 name and use-name (e.g. `base00 / bg`), a live color swatch, and a hex input field. A live preview panel shows text, accent, and urgent colors on the palette's background.

### Use-name editor

Press `u` from the list screen to rename use-name aliases. This lets you rebind which base16 slot a use-name points to — for example, pointing `accent` at `base0D` instead of `base07`. Changes are saved to `palettes.yaml` and applied on the next `palette-manager --apply`.

### Autofill

Instead of picking all 16 colors by hand, provide 3 seed colors and let palette-manager derive the rest:

1. **Set the seeds:** `base00` (bg), `base05` (text), `base07` (accent)
2. **Press `Ctrl+A`** or click the Autofill button
3. **Adjust** any derived colors you don't like, then save

The derivation uses [HSLuv](https://www.hsluv.org/) (perceptually uniform color space) so that derived greens and blues look equally bright at the same lightness step:

- **Structural colors** (`base01`–`base04`, `base06`) are interpolated along a lightness ramp between bg and text, sharing bg's hue and saturation.
- **Semantic colors** (`base08`–`base0F`) use 8 canonical hues (slightly shifted from pure ANSI values for a refined look) with the accent's chroma and lightness, clamped to readable ranges.

## Built-in base16 schemes

Palette-manager ships with 325+ color schemes from the [tinted-theming/schemes](https://github.com/tinted-theming/schemes) repository. These appear in the palette list with a 🔒 indicator.

- **Read-only:** built-in schemes cannot be edited or deleted
- **Duplicate to edit:** pressing `e` on a 🔒 scheme creates a copy with a unique name and opens the editor
- **Auto-updated:** the scheme cache is refreshed from GitHub every 24 hours when you launch the TUI. If you're offline, the cached copy is used
- **Force update:** run `palette-manager --update-base16` to download the latest schemes immediately

The cache is stored at `base16-schemes.yaml` alongside your `palettes.yaml`.

## Seeded user palettes

Six palettes are seeded on first run:

- **Default** — a dark neutral palette with a green accent
- **Catppuccin Mocha** — warm pastel theme
- **Tokyo Night** — cool blue-toned theme
- **Gruvbox Dark** — earthy retro theme
- **Nord** — arctic blue theme
- **Rose Pine** — soft pine/pink theme

These are user palettes (not read-only) — edit, rename, or delete them freely.

## Requirements

- Python ≥ 3.11
- A terminal with true-color (24-bit color) support
- Network access for base16 scheme downloads (optional — works offline with cached schemes)

## License

MIT
