# palette-manager

TUI for managing color palettes for [niri](https://github.com/niri-wm/niri) + [Quickshell](https://quickshell.outfoxxed.me/) theming via [chezmoi](https://chezmoi.io/) data files.

## How it works

```
palettes.yaml  ──palette-manager──►  active palette
                                          │
                                     writes colors to
                                          │
                                     theme.yaml  ──chezmoi apply──►  config.kdl + Theme.qml
                                          │                                │
                                          ▼                                ▼
                                        niri                          Quickshell
```

Both niri and Quickshell read from the same chezmoi data (`theme.yaml`), so colors stay unified across the compositor and shell components.

## Install

```bash
uv tool install git+ssh://git@github.com/dylanrussellmd/palette-manager
```

## Usage

```bash
palette-manager              # launch the TUI
palette-manager --check      # list palettes from CLI
palette-manager --apply      # apply active palette + chezmoi apply (non-interactive)
```

### List screen

| Key | Action |
|---|---|
| `↑`/`↓` or `k`/`j` | Navigate palettes |
| `e` or `Enter` | Edit selected palette |
| `n` | New palette |
| `d` | Delete palette |
| `a` | Activate + apply (writes theme.yaml, runs chezmoi apply) |
| `q` | Quit |

### Edit screen

- Editable palette name
- 7 color inputs with live true-color swatches
- Live preview panel showing text/accent/urgent on background
- `Ctrl+S` or Save button to save
- `Esc` or Cancel button to discard

## Configuration

Paths default to chezmoi's data directory but can be overridden:

| Env var | Default |
|---|---|
| `CHEZMOI_DIR` | `~/.local/share/chezmoi` |
| `PALETTES_FILE` | `$CHEZMOI_DIR/.chezmoidata/palettes.yaml` |
| `THEME_FILE` | `$CHEZMOI_DIR/.chezmoidata/theme.yaml` |

## Seeded palettes

Default, Catppuccin Mocha, Tokyo Night, Gruvbox Dark, Nord, Rose Pine.

## Requirements

- Python ≥ 3.11
- chezmoi (for apply action)
- A terminal with true-color support
