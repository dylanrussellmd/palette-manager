"""TUI for managing color palettes with configurable apply behavior.

By default, palettes are stored in ~/.config/palette-manager/palettes.yaml.
Configure theme file output and apply commands via a config file:

    palette-manager --init          Create default config at
                                    ~/.config/palette-manager/config.yaml

Config file format (YAML):

    palettes_file: ~/.config/palette-manager/palettes.yaml
    theme_file: null               # where to write active palette's colors
    theme_path: null               # dotted path within the file (e.g. "theme.colors")
    theme_keys: [bg, surface, text, accent, urgent, border, shadow]
    apply_command: null            # shell command to run after writing

Usage:
    palette-manager              Launch the TUI
    palette-manager --check      List palettes and exit
    palette-manager --apply      Apply active palette (non-interactive)
    palette-manager --init       Create default config file
    palette-manager --config /path/to/config.yaml   Use a specific config

List screen:
    ↑/↓      Navigate palettes
    Enter/e  Edit selected palette
    n        New palette
    d        Delete palette
    a        Activate + apply selected palette
    q        Quit

Edit screen:
    Tab      Move between fields
    [Save]   Button or Ctrl+S
    Esc      Cancel
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Container, Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Label, Static

# ── Constants ────────────────────────────────────────────────────

COLOR_KEYS = ["bg", "surface", "text", "accent", "urgent", "border", "shadow"]

SEED_PALETTES = {
    "Default": {
        "bg": "#11111b",
        "surface": "#1e1e2e",
        "text": "#cdd6f4",
        "accent": "#4DFFBC",
        "urgent": "#FF4D4D",
        "border": "#898989",
        "shadow": "#898989",
    },
    "Catppuccin Mocha": {
        "bg": "#1e1e2e",
        "surface": "#313244",
        "text": "#cdd6f4",
        "accent": "#89b4fa",
        "urgent": "#f38ba8",
        "border": "#45475a",
        "shadow": "#11111bc0",
    },
    "Tokyo Night": {
        "bg": "#1a1b26",
        "surface": "#24283b",
        "text": "#c0caf5",
        "accent": "#7aa2f7",
        "urgent": "#f7768e",
        "border": "#414868",
        "shadow": "#000000a0",
    },
    "Gruvbox Dark": {
        "bg": "#282828",
        "surface": "#3c3836",
        "text": "#ebdbb2",
        "accent": "#b8bb26",
        "urgent": "#fb4934",
        "border": "#504945",
        "shadow": "#000000a0",
    },
    "Nord": {
        "bg": "#2e3440",
        "surface": "#3b4252",
        "text": "#d8dee9",
        "accent": "#88c0d0",
        "urgent": "#bf616a",
        "border": "#4c566a",
        "shadow": "#000000a0",
    },
    "Rose Pine": {
        "bg": "#191724",
        "surface": "#1f1d2e",
        "text": "#e0def4",
        "accent": "#ebbcba",
        "urgent": "#eb6f92",
        "border": "#26233a",
        "shadow": "#000000a0",
    },
}

CONFIG_DIR = Path.home() / ".config" / "palette-manager"
DEFAULT_CONFIG_FILE = CONFIG_DIR / "config.yaml"
DEFAULT_PALETTES_FILE = CONFIG_DIR / "palettes.yaml"


# ── Config ────────────────────────────────────────────────────────


@dataclass
class Config:
    """Runtime configuration loaded from config.yaml."""

    palettes_file: Path = DEFAULT_PALETTES_FILE
    theme_file: Path | None = None
    theme_path: str | None = None
    theme_keys: list[str] = field(default_factory=lambda: list(COLOR_KEYS))
    apply_command: str | None = None


def load_config(config_path: Path | None = None) -> Config:
    """Load config from YAML file, falling back to defaults."""
    path = config_path or DEFAULT_CONFIG_FILE
    if not path.exists():
        return Config()

    yaml = YAML()
    with open(path) as f:
        data = yaml.load(f)

    if data is None:
        return Config()

    def resolve(p: str | None) -> Path | None:
        if p is None:
            return None
        return Path(p).expanduser()

    return Config(
        palettes_file=resolve(data.get("palettes_file")) or DEFAULT_PALETTES_FILE,
        theme_file=resolve(data.get("theme_file")),
        theme_path=data.get("theme_path"),
        theme_keys=data.get("theme_keys") or list(COLOR_KEYS),
        apply_command=data.get("apply_command"),
    )


def init_config(config_path: Path | None = None) -> int:
    """Create a default config file with comments."""
    path = config_path or DEFAULT_CONFIG_FILE
    if path.exists():
        print(f"Config already exists: {path}", file=sys.stderr)
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)

    default_config = """\
# Palette Manager configuration
# https://github.com/dylanrussellmd/palette-manager

# Where to store palettes (created automatically if missing)
palettes_file: ~/.config/palette-manager/palettes.yaml

# Where to write the active palette's colors on apply.
# Set to null to skip writing (palettes are still saved).
theme_file: null

# Dotted path within the theme file to write colors under.
# e.g. "theme.colors" writes to doc["theme"]["colors"]
# Leave null to write at the root level.
theme_path: null

# Color keys to write to the theme file.
theme_keys:
  - bg
  - surface
  - text
  - accent
  - urgent
  - border
  - shadow

# Shell command to run after writing colors on apply.
# Examples:
#   apply_command: chezmoi apply
#   apply_command: hyprctl reload
#   apply_command: ~/.config/palette-manager/apply.sh
apply_command: null
"""
    path.write_text(default_config)
    print(f"Created config: {path}")
    print("Edit it to configure theme_file and apply_command for your setup.")
    return 0


# ── YAML helpers ──────────────────────────────────────────────────


def load_palettes(config: Config) -> tuple[dict, str]:
    """Load palettes.yaml. Seeds with defaults if missing."""
    yaml = YAML()
    if not config.palettes_file.exists():
        config.palettes_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"active": "Default", "palettes": SEED_PALETTES}
        _dump_yaml(config.palettes_file, data)
        return dict(SEED_PALETTES), "Default"

    with open(config.palettes_file) as f:
        doc = yaml.load(f)
    palettes = dict(doc.get("palettes", {}))
    active = doc.get("active", "")
    if not palettes:
        palettes = dict(SEED_PALETTES)
        active = "Default"
    if active not in palettes:
        active = next(iter(palettes))
    return palettes, active


def save_palettes(palettes: dict, active: str, config: Config) -> None:
    """Write palettes + active name to palettes.yaml."""
    data = {"active": active, "palettes": palettes}
    _dump_yaml(config.palettes_file, data)


def write_theme_colors(colors: dict, config: Config) -> None:
    """Write active palette's colors into theme file, preserving comments."""
    if config.theme_file is None:
        return

    yaml = YAML()
    if config.theme_file.exists():
        with open(config.theme_file) as f:
            doc = yaml.load(f)
    else:
        doc = {}

    # Navigate to the target path
    target = doc
    if config.theme_path:
        for part in config.theme_path.split("."):
            if part not in target or target[part] is None:
                target[part] = {}
            target = target[part]

    for key in config.theme_keys:
        target[key] = colors[key]

    config.theme_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config.theme_file, "w") as f:
        yaml.dump(doc, f)


def _dump_yaml(path: Path, data: dict) -> None:
    yaml = YAML()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f)


def run_apply_command(config: Config) -> tuple[bool, str]:
    """Run the configured apply command. Returns (success, message)."""
    if config.apply_command is None:
        return True, ""

    try:
        result = subprocess.run(
            config.apply_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"{config.apply_command} complete"
        return False, f"{config.apply_command} failed: {result.stderr[:200]}"
    except FileNotFoundError:
        return False, f"command not found: {config.apply_command}"
    except subprocess.TimeoutExpired:
        return False, f"{config.apply_command} timed out"


# ── Color swatch widget ──────────────────────────────────────────


class ColorSwatch(Static):
    """A colored block showing a hex color as its background."""

    hex_color: reactive[str] = reactive("#000000")

    def __init__(self, hex_color: str, **kwargs) -> None:
        super().__init__("", **kwargs)
        self.hex_color = hex_color

    def watch_hex_color(self, hex_color: str) -> None:
        try:
            self.styles.background = Color.parse(hex_color)
        except Exception:
            pass


# ── Palette card (list screen rows) ──────────────────────────────


class PaletteCard(Widget):
    """A card showing a palette name, active marker, and mini swatches."""

    DEFAULT_CSS = """
    PaletteCard {
        height: auto;
        min-height: 4;
        padding: 0 2;
        margin: 0 0 1 0;
        border: round $surface;
    }
    PaletteCard.-selected {
        border: round $accent;
    }
    .card-name {
        text-style: bold;
        padding: 0 1;
    }
    .card-swatches {
        height: 3;
        padding: 0 1;
        align: center middle;
    }
    .mini-swatch {
        width: 8;
        height: 3;
        margin: 0 1 0 0;
    }
    .card-hex {
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(
        self, name: str, colors_data: dict, is_active: bool = False, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.palette_name = name
        self.colors_data = colors_data
        self.is_active = is_active

    def compose(self) -> ComposeResult:
        marker = "  ★ active" if self.is_active else ""
        yield Label(f"{self.palette_name}{marker}", classes="card-name")
        with Horizontal(classes="card-swatches"):
            for key in COLOR_KEYS:
                hex_val = self.colors_data.get(key, "#000000")
                yield ColorSwatch(hex_val, classes="mini-swatch")
        hex_line = "  ".join(self.colors_data.get(k, "???") for k in COLOR_KEYS)
        yield Label(hex_line, classes="card-hex")


# ── Palette edit screen ──────────────────────────────────────────


class PaletteEditScreen(ModalScreen):
    """Modal screen for editing a palette's name and colors."""

    DEFAULT_CSS = """
    PaletteEditScreen {
        align: center middle;
    }
    PaletteEditScreen > #edit-dialog {
        width: 74;
        max-width: 92%;
        height: auto;
        max-height: 88%;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    PaletteEditScreen .section-label {
        background: $primary;
        text-style: bold;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    PaletteEditScreen .name-row {
        height: 3;
        layout: horizontal;
        padding: 0 2;
        align: center middle;
    }
    PaletteEditScreen .name-label {
        width: 14;
        content-align: right middle;
    }
    PaletteEditScreen .name-input {
        width: 40;
    }
    PaletteEditScreen .color-row {
        height: 3;
        layout: horizontal;
        padding: 0 2;
        align: center middle;
    }
    PaletteEditScreen .color-label {
        width: 14;
        content-align: right middle;
    }
    PaletteEditScreen .swatch {
        width: 16;
        height: 3;
        margin: 0 1;
    }
    PaletteEditScreen .hex-input {
        width: 22;
    }
    PaletteEditScreen #preview-mock {
        height: 5;
        padding: 1 2;
        margin: 1 2 0 2;
    }
    PaletteEditScreen .button-row {
        height: 3;
        padding: 1 2 0 2;
        align: center middle;
    }
    PaletteEditScreen .button-row Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, name: str, colors: dict, is_new: bool = False) -> None:
        super().__init__()
        self.original_name = name
        self.colors = dict(colors)
        self.is_new = is_new

    def compose(self) -> ComposeResult:
        title = " NEW PALETTE" if self.is_new else " EDIT PALETTE"
        with Container(id="edit-dialog"):
            yield Label(title, classes="section-label")
            with Horizontal(classes="name-row"):
                yield Label("name", classes="name-label")
                yield Input(
                    value=self.original_name, id="palette-name", classes="name-input"
                )
            yield Label(" COLORS", classes="section-label")
            for key in COLOR_KEYS:
                hex_val = self.colors.get(key, "#000000")
                with Horizontal(classes="color-row"):
                    yield Label(key, classes="color-label")
                    yield ColorSwatch(hex_val, id=f"swatch-{key}", classes="swatch")
                    yield Input(value=hex_val, id=f"color-{key}", classes="hex-input")
            yield Label(" PREVIEW", classes="section-label")
            yield Static(id="preview-mock")
            with Horizontal(classes="button-row"):
                yield Button("Save", id="save-btn", variant="success")
                yield Button("Cancel", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        self._update_preview()

    def on_input_changed(self, event: Input.Changed) -> None:
        input_id = event.input.id or ""
        if not input_id.startswith("color-"):
            return
        key = input_id.removeprefix("color-")
        hex_val = event.value.strip()
        try:
            self.query_one(f"#swatch-{key}", ColorSwatch).hex_color = hex_val
        except Exception:
            pass
        self._update_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def _update_preview(self) -> None:
        colors = self._collect_colors()
        try:
            mock = self.query_one("#preview-mock", Static)
            bg = colors.get("bg", "#000000")
            mock.styles.background = Color.parse(bg)
            mock.update(
                f"[{colors.get('text', '#fff')}]Main System Dashboard[/]\n"
                f"[{colors.get('accent', '#0f0')}]CPU: 14% | RAM: 4.2GB[/]\n"
                f"[{colors.get('urgent', '#f00')}]! Low battery[/]"
            )
        except Exception:
            pass

    def _collect_colors(self) -> dict:
        colors: dict[str, str] = {}
        for key in COLOR_KEYS:
            try:
                colors[key] = self.query_one(
                    f"#color-{key}", Input
                ).value.strip() or self.colors.get(key, "#000000")
            except Exception:
                colors[key] = self.colors.get(key, "#000000")
        return colors

    def _get_name(self) -> str:
        try:
            return (
                self.query_one("#palette-name", Input).value.strip()
                or self.original_name
            )
        except Exception:
            return self.original_name

    def action_save(self) -> None:
        self.dismiss((self._get_name(), self._collect_colors()))

    def action_cancel(self) -> None:
        self.dismiss(None)


# ── Main app ─────────────────────────────────────────────────────


class PaletteApp(App):
    """Palette manager with configurable apply behavior."""

    TITLE = "Palette Manager"
    SUB_TITLE = ""  # set in __init__

    CSS = """
    #palette-list {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("up", "navigate(-1)", "↑", show=False, priority=True),
        Binding("down", "navigate(1)", "↓", show=False, priority=True),
        Binding("k", "navigate(-1)", show=False, priority=True),
        Binding("j", "navigate(1)", show=False, priority=True),
        Binding("enter", "edit", "Edit", show=False),
        Binding("e", "edit", "Edit"),
        Binding("n", "new", "New"),
        Binding("d", "delete", "Delete"),
        Binding("a", "activate", "Activate"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+p", "noop", show=False),
    ]

    selected_index = reactive(0)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.palettes, self.active_palette = load_palettes(config)
        self.SUB_TITLE = str(config.palettes_file)

    # ── Compose ───────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="palette-list"):
            for i, (name, colors) in enumerate(self.palettes.items()):
                card = PaletteCard(
                    name,
                    colors,
                    is_active=(name == self.active_palette),
                )
                if i == self.selected_index:
                    card.add_class("-selected")
                yield card
        yield Footer()

    def on_mount(self) -> None:
        scroll = self.query_one("#palette-list", VerticalScroll)
        scroll.can_focus = False
        self._refresh_cards()

    # ── Rendering ─────────────────────────────────────────────────

    def _refresh_cards(self) -> None:
        """Full rebuild of the palette list."""
        scroll = self.query_one("#palette-list", VerticalScroll)
        scroll.remove_children()
        for i, (name, colors) in enumerate(self.palettes.items()):
            card = PaletteCard(
                name,
                colors,
                is_active=(name == self.active_palette),
            )
            if i == self.selected_index:
                card.add_class("-selected")
            scroll.mount(card)
        self._scroll_to_selected()

    def _update_selection(self) -> None:
        """Lightweight CSS-only update for navigation."""
        try:
            scroll = self.query_one("#palette-list", VerticalScroll)
        except Exception:
            return  # DOM not ready yet
        for i, card in enumerate(scroll.children):
            if isinstance(card, PaletteCard):
                card.set_class(i == self.selected_index, "-selected")

    def _scroll_to_selected(self) -> None:
        """Keep the selected card scrolled into view."""
        try:
            scroll = self.query_one("#palette-list", VerticalScroll)
            cards = [c for c in scroll.children if isinstance(c, PaletteCard)]
            if 0 <= self.selected_index < len(cards):
                scroll.scroll_to_widget(cards[self.selected_index], animate=False)
        except Exception:
            pass

    def watch_selected_index(self, _idx: int) -> None:
        self._update_selection()
        self._scroll_to_selected()

    # ── Actions ───────────────────────────────────────────────────

    def action_navigate(self, delta: int) -> None:
        max_idx = max(len(self.palettes) - 1, 0)
        self.selected_index = max(0, min(self.selected_index + delta, max_idx))

    def _palette_names(self) -> list[str]:
        return list(self.palettes.keys())

    def _selected_name(self) -> str | None:
        names = self._palette_names()
        if not names:
            return None
        idx = min(self.selected_index, len(names) - 1)
        return names[idx]

    def action_edit(self) -> None:
        name = self._selected_name()
        if name is None:
            return

        def on_result(result):
            if result is None:
                return
            new_name, new_colors = result
            if new_name != name:
                del self.palettes[name]
                if self.active_palette == name:
                    self.active_palette = new_name
            self.palettes[new_name] = new_colors
            save_palettes(self.palettes, self.active_palette, self.config)
            self._refresh_cards()
            self.notify(f"Saved '{new_name}'", timeout=2)

        self.push_screen(
            PaletteEditScreen(name, self.palettes[name]),
            on_result,
        )

    def action_new(self) -> None:
        default_colors = dict(SEED_PALETTES["Catppuccin Mocha"])
        base = "New Palette"
        name = base
        n = 2
        while name in self.palettes:
            name = f"{base} {n}"
            n += 1

        def on_result(result):
            if result is None:
                return
            new_name, new_colors = result
            self.palettes[new_name] = new_colors
            save_palettes(self.palettes, self.active_palette, self.config)
            self.selected_index = list(self.palettes.keys()).index(new_name)
            self._refresh_cards()
            self.notify(f"Created '{new_name}'", timeout=2)

        self.push_screen(
            PaletteEditScreen(name, default_colors, is_new=True),
            on_result,
        )

    def action_delete(self) -> None:
        if len(self.palettes) <= 1:
            self.notify("Cannot delete the last palette", severity="error")
            return
        name = self._selected_name()
        if name is None:
            return
        del self.palettes[name]
        if self.active_palette == name:
            self.active_palette = next(iter(self.palettes))
        if self.selected_index >= len(self.palettes):
            self.selected_index = max(0, len(self.palettes) - 1)
        save_palettes(self.palettes, self.active_palette, self.config)
        self._refresh_cards()
        self.notify(f"Deleted '{name}'", timeout=2)

    def action_activate(self) -> None:
        """Set selected palette as active, write colors, and run apply command."""
        name = self._selected_name()
        if name is None:
            return
        self.active_palette = name
        colors = self.palettes[name]

        # Write to theme file if configured
        if self.config.theme_file is not None:
            write_theme_colors(colors, self.config)

        save_palettes(self.palettes, self.active_palette, self.config)
        self._refresh_cards()

        # Run apply command if configured
        if self.config.apply_command:
            self.notify(
                f"Applied '{name}' — running {self.config.apply_command}...",
                timeout=3,
            )
            ok, msg = run_apply_command(self.config)
            if ok and msg:
                self.notify(msg, timeout=3)
            elif not ok:
                self.notify(msg, timeout=5, severity="error")
        else:
            self.notify(f"Saved '{name}' as active", timeout=2)

    def action_noop(self) -> None:
        """Suppress Textual's built-in command palette (Ctrl+P)."""
        pass


# ── CLI entry points ─────────────────────────────────────────────


def check_palettes(config: Config) -> int:
    palettes, active = load_palettes(config)
    print(f"\n  Palettes: {config.palettes_file}")
    if config.theme_file:
        print(
            f"  Theme:    {config.theme_file}"
            + (f" ({config.theme_path})" if config.theme_path else "")
        )
    if config.apply_command:
        print(f"  Apply:    {config.apply_command}")
    print(f"\n  Active: {active}\n")
    for name, colors in palettes.items():
        marker = " ★" if name == active else ""
        print(f"  {name}{marker}")
        for k, v in colors.items():
            print(f"    {k:14s} {v}")
        print()
    return 0


def apply_noninteractive(config: Config) -> int:
    palettes, active = load_palettes(config)
    if not palettes or not active:
        print("No active palette found", file=sys.stderr)
        return 1
    colors = palettes[active]
    if config.theme_file is not None:
        write_theme_colors(colors, config)
        print(f"Written '{active}' colors to {config.theme_file}")
    save_palettes(palettes, active, config)
    if config.apply_command:
        ok, msg = run_apply_command(config)
        print(f"  {msg}" if msg else "  (no output)")
        return 0 if ok else 1
    print(f"Saved '{active}' as active")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="palette-manager",
        description="TUI for managing color palettes",
    )
    parser.add_argument("--config", type=Path, help="Path to config file")
    parser.add_argument("--check", action="store_true", help="List palettes and exit")
    parser.add_argument(
        "--apply", action="store_true", help="Apply active palette (non-interactive)"
    )
    parser.add_argument(
        "--init", action="store_true", help="Create default config file"
    )
    args = parser.parse_args()

    if args.init:
        sys.exit(init_config(args.config))

    config = load_config(args.config)

    if args.check:
        sys.exit(check_palettes(config))

    if args.apply:
        sys.exit(apply_noninteractive(config))

    PaletteApp(config).run()
