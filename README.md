# palette-manager

TUI for managing color palettes with configurable apply behavior.

## How it works

```
palettes.yaml  ──palette-manager──►  active palette
                                          │
                                     writes colors to (optional)
                                          │
                                     theme_file  ──runs──►  apply_command
```

Palette-manager is generic — it stores palettes in a YAML file and optionally writes the active palette's colors to a separate file, then runs a shell command. The specific integration (chezmoi, hyprland, custom script) is defined in a config file.

## Install

```bash
uv tool install git+ssh://git@github.com/dylanrussellmd/palette-manager
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
# Where to store palettes
palettes_file: ~/.config/palette-manager/palettes.yaml

# Where to write the active palette's colors on apply.
# Set to null to skip writing.
theme_file: null

# Dotted path within the theme file to write colors under.
# e.g. "theme.colors" writes to doc["theme"]["colors"]
# Leave null to write at the root level.
theme_path: null

# Color keys to write to the theme file.
theme_keys: [bg, surface, text, accent, urgent, border, shadow]

# Shell command to run after writing colors on apply.
# Set to null to skip.
apply_command: null
```

### Example: chezmoi + niri + Quickshell

```yaml
palettes_file: ~/.local/share/chezmoi/.chezmoidata/palettes.yaml
theme_file: ~/.local/share/chezmoi/.chezmoidata/theme.yaml
theme_path: theme.colors
theme_keys: [bg, surface, text, accent, urgent, border, shadow]
apply_command: chezmoi apply
```

### Example: Hyprland

```yaml
palettes_file: ~/.config/palette-manager/palettes.yaml
theme_file: ~/.config/hypr/colors.conf
theme_path: null
theme_keys: [bg, surface, text, accent, urgent, border, shadow]
apply_command: hyprctl reload
```

### Example: custom script

```yaml
palettes_file: ~/.config/palette-manager/palettes.yaml
theme_file: ~/.config/palette-manager/colors.yaml
theme_path: null
theme_keys: [bg, surface, text, accent, urgent, border, shadow]
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
palette-manager --config /path/to/config.yaml   # use a specific config
```

### List screen

| Key | Action |
|---|---|
| `↑`/`↓` or `k`/`j` | Navigate palettes |
| `e` or `Enter` | Edit selected palette |
| `n` | New palette |
| `d` | Delete palette |
| `a` | Activate + apply |
| `q` | Quit |

### Edit screen

- Editable palette name
- 7 color inputs with live true-color swatches
- Live preview panel showing text/accent/urgent on background
- `Ctrl+S` or Save button to save
- `Esc` or Cancel button to discard

## Seeded palettes

Default, Catppuccin Mocha, Tokyo Night, Gruvbox Dark, Nord, Rose Pine.

## Requirements

- Python ≥ 3.11
- A terminal with true-color support
