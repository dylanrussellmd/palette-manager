"""TUI for managing color palettes with configurable apply behavior.

Palettes use a 16-color base16 system. Each color has TWO names:

  - a base16 name (base00–base0F) — the canonical storage key
  - a use-name (bg, surface, text, accent, etc.) — a customizable alias
    defined by the `uses` mapping in palettes.yaml

On apply, palette-manager writes BOTH the base16 keys and the use-name
aliases to the theme file, so downstream tools can read whichever they
prefer. Users can remap use-names (e.g. point "accent" at base0D instead
of base07) by editing the `uses` block in palettes.yaml.

By default, palettes are stored in ~/.config/palette-manager/palettes.yaml.
Configure theme file output and apply commands via a config file:

    palette-manager --init          Create default config at
                                    ~/.config/palette-manager/config.yaml

Config file format (YAML):

    palettes_file: ~/.config/palette-manager/palettes.yaml
    theme_file: null               # where to write active palette's colors
    theme_path: null               # dotted path within the file (e.g. "theme.colors")
    apply_command: null            # shell command to run after writing

Usage:
    palette-manager              Launch the TUI
    palette-manager --check      List palettes and exit
    palette-manager --apply      Apply active palette (non-interactive)
    palette-manager --init       Create default config file
    palette-manager --update-base16  Force-update base16 scheme cache
    palette-manager --config /path/to/config.yaml   Use a specific config

List screen:
    ↑/↓      Navigate palettes
    e/Enter  Edit (or duplicate if built-in)
    n        New palette
    d        Delete palette
    u        Edit use-name mapping
    v        Cycle display mode (hex → base16 → use-names)
    a        Activate + apply selected palette
    /        Focus search bar
    Esc      Clear search / unfocus
    q        Quit

Edit screen:
    Tab      Move between fields
    Ctrl+A   Autofill from base00 + base05 + base07
    [Save]   Button or Ctrl+S
    Esc      Cancel

Autofill:
    Given 3 seed colors (base00/bg, base05/text, base07/accent),
    derives the remaining 13 colors using color theory:
      - Structural colors (base01–base04, base06) are interpolated
        along a perceptually uniform lightness ramp (HSLuv) between
        bg and text, sharing bg's hue and saturation.
      - Semantic colors (base08–base0F) use 8 canonical hues with
        the accent's chroma and lightness, clamped to readable ranges.
    Enter the 3 seeds, press Ctrl+A or click Autofill, then adjust.

Built-in base16 schemes (🔒) are downloaded from tinted-theming/schemes
and cached for 24h. They cannot be edited or deleted, but pressing 'e'
on one duplicates it as a user palette for editing.
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from hsluv import hex_to_hsluv, hsluv_to_hex
from rich.style import Style
from rich.text import Text
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

BASE16_KEYS = [
    "base00",
    "base01",
    "base02",
    "base03",
    "base04",
    "base05",
    "base06",
    "base07",
    "base08",
    "base09",
    "base0A",
    "base0B",
    "base0C",
    "base0D",
    "base0E",
    "base0F",
]

DEFAULT_USES = {
    "base00": "bg",
    "base01": "surface",
    "base02": "selection",
    "base03": "muted",
    "base04": "border",
    "base05": "text",
    "base06": "shadow",
    "base07": "accent",
    "base08": "red",
    "base09": "orange",
    "base0A": "yellow",
    "base0B": "green",
    "base0C": "cyan",
    "base0D": "blue",
    "base0E": "magenta",
    "base0F": "urgent",
}

# base16 schemes cache
BASE16_REPO_URL = (
    "https://github.com/tinted-theming/schemes/archive/refs/heads/spec-0.11.tar.gz"
)
BASE16_CACHE_TTL = timedelta(hours=24)  # re-download if older than this

# Backward-compat alias (some code references COLOR_KEYS).
COLOR_KEYS = BASE16_KEYS

# Canonical hues (in HSLuv degrees) for the 8 semantic colors.
# Slightly shifted from pure ANSI values for a more refined look.
CANONICAL_HUES = {
    "base08": 0,  # red
    "base09": 30,  # orange
    "base0A": 55,  # yellow (warm, not pure 60°)
    "base0B": 135,  # green (teal-leaning, not pure 120°)
    "base0C": 185,  # cyan
    "base0D": 225,  # blue (purple-leaning, not pure 240°)
    "base0E": 300,  # magenta
    "base0F": 350,  # urgent (pink-red, not pure 0°)
}

SEED_PALETTES = {
    "Default": {
        "base00": "#11111b",
        "base01": "#1e1e2e",
        "base02": "#313244",
        "base03": "#6c7086",
        "base04": "#898989",
        "base05": "#cdd6f4",
        "base06": "#898989",
        "base07": "#4DFFBC",
        "base08": "#FF4D4D",
        "base09": "#FFA94D",
        "base0A": "#FFD75F",
        "base0B": "#4DFFBC",
        "base0C": "#7DCFFF",
        "base0D": "#7aa2f7",
        "base0E": "#BB9AF7",
        "base0F": "#FF4D4D",
    },
    "Catppuccin Mocha": {
        "base00": "#1e1e2e",
        "base01": "#313244",
        "base02": "#45475a",
        "base03": "#6c7086",
        "base04": "#45475a",
        "base05": "#cdd6f4",
        "base06": "#11111bc0",
        "base07": "#89b4fa",
        "base08": "#f38ba8",
        "base09": "#fab387",
        "base0A": "#f9e2af",
        "base0B": "#a6e3a1",
        "base0C": "#94e2d5",
        "base0D": "#89b4fa",
        "base0E": "#cba6f7",
        "base0F": "#f38ba8",
    },
    "Tokyo Night": {
        "base00": "#1a1b26",
        "base01": "#24283b",
        "base02": "#283457",
        "base03": "#565f89",
        "base04": "#414868",
        "base05": "#c0caf5",
        "base06": "#000000a0",
        "base07": "#7aa2f7",
        "base08": "#f7768e",
        "base09": "#ff9e64",
        "base0A": "#e0af68",
        "base0B": "#9ece6a",
        "base0C": "#7dcfff",
        "base0D": "#7aa2f7",
        "base0E": "#bb9af7",
        "base0F": "#f7768e",
    },
    "Gruvbox Dark": {
        "base00": "#282828",
        "base01": "#3c3836",
        "base02": "#504945",
        "base03": "#7c6f64",
        "base04": "#504945",
        "base05": "#ebdbb2",
        "base06": "#000000a0",
        "base07": "#b8bb26",
        "base08": "#fb4934",
        "base09": "#fe8019",
        "base0A": "#fabd2f",
        "base0B": "#b8bb26",
        "base0C": "#8ec07c",
        "base0D": "#83a598",
        "base0E": "#d3869b",
        "base0F": "#fb4934",
    },
    "Nord": {
        "base00": "#2e3440",
        "base01": "#3b4252",
        "base02": "#434c5e",
        "base03": "#4c566a",
        "base04": "#4c566a",
        "base05": "#d8dee9",
        "base06": "#000000a0",
        "base07": "#88c0d0",
        "base08": "#bf616a",
        "base09": "#d08770",
        "base0A": "#ebcb8b",
        "base0B": "#a3be8c",
        "base0C": "#88c0d0",
        "base0D": "#81a1c1",
        "base0E": "#b48ead",
        "base0F": "#bf616a",
    },
    "Rose Pine": {
        "base00": "#191724",
        "base01": "#1f1d2e",
        "base02": "#26233a",
        "base03": "#6e6a86",
        "base04": "#26233a",
        "base05": "#e0def4",
        "base06": "#000000a0",
        "base07": "#ebbcba",
        "base08": "#eb6f92",
        "base09": "#f6c177",
        "base0A": "#f6c177",
        "base0B": "#9ccfd8",
        "base0C": "#9ccfd8",
        "base0D": "#31748f",
        "base0E": "#c4a7e7",
        "base0F": "#eb6f92",
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
    apply_command: str | None = None

    @property
    def base16_schemes_file(self) -> Path:
        """Cache file for downloaded base16 schemes, alongside palettes_file."""
        return self.palettes_file.parent / "base16-schemes.yaml"


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

# palette-manager writes all 16 base16 keys (base00–base0F) plus
# their use-name aliases (bg, surface, text, etc.) from the `uses`
# mapping in palettes.yaml. No need to list keys here.

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


# ── Color helpers ─────────────────────────────────────────────────


def _hex_to_hsluv(hex_str: str) -> tuple[float, float, float]:
    """Convert #rrggbb or #rrggbbaa to (h, s, l) in HSLuv space."""
    h = hex_str.lstrip("#")
    if len(h) == 8:
        h = h[:6]  # strip alpha
    return hex_to_hsluv(f"#{h}")


def _hsluv_to_hex(h: float, s: float, l: float) -> str:
    """Convert (h, s, l) in HSLuv to #rrggbb."""
    return hsluv_to_hex((h, s, l))


# ── Autofill ──────────────────────────────────────────────────────


def autofill_colors(colors: dict) -> dict:
    """Derive all 16 colors from 3 seed colors.

    Requires:
      - base00 (bg): darkest background color
      - base05 (text): lightest foreground color
      - base07 (accent): the palette's accent / highlight color

    Derives:
      - base01–base04: lightness ramp between bg and text (bg's hue/saturation)
      - base06: shadow (darker than bg, same hue)
      - base08–base0F: semantic colors at canonical hues, using accent's
        chroma/lightness clamped to readable ranges
    """
    bg = colors.get("base00")
    text = colors.get("base05")
    accent = colors.get("base07")

    if not all([bg, text, accent]):
        raise ValueError(
            "Autofill requires base00 (bg), base05 (text), and base07 (accent)"
        )

    result = dict(colors)

    bg_h, bg_s, bg_l = _hex_to_hsluv(bg)
    text_h, text_s, text_l = _hex_to_hsluv(text)
    _, accent_s, accent_l = _hex_to_hsluv(accent)

    # Structural ramp: base01–base04 interpolated between bg and text.
    # Uses bg's hue and saturation for a cohesive structural palette.
    ramp_keys = ["base01", "base02", "base03", "base04"]
    n_steps = len(ramp_keys) + 1  # 5 intervals between bg and text
    for i, key in enumerate(ramp_keys, 1):
        t = i / n_steps
        l = bg_l + (text_l - bg_l) * t
        result[key] = _hsluv_to_hex(bg_h, bg_s, l)

    # Shadow: darker than bg, same hue
    result["base06"] = _hsluv_to_hex(bg_h, bg_s, max(bg_l * 0.35, 5))

    # Semantic colors: canonical hues with accent's chroma/lightness,
    # clamped to ensure readability across all hues.
    target_s = max(50, min(90, accent_s))
    target_l = max(55, min(80, accent_l))

    for key, hue in CANONICAL_HUES.items():
        result[key] = _hsluv_to_hex(hue, target_s, target_l)

    return result


# ── Base16 scheme cache ──────────────────────────────────────────


def _needs_update(cache_file: Path) -> bool:
    """Check if the base16 cache is missing or stale."""
    if not cache_file.exists():
        return True
    try:
        yaml = YAML()
        with open(cache_file) as f:
            doc = yaml.load(f)
        if doc is None:
            return True
        last_updated_str = doc.get("last_updated")
        if not last_updated_str:
            return True
        last_updated = datetime.fromisoformat(last_updated_str)
        return datetime.now() - last_updated > BASE16_CACHE_TTL
    except Exception:
        return True


def _download_base16_schemes() -> dict:
    """Download and parse all base16 schemes from the tinted-theming repo.

    Returns a dict: { "Scheme Name": { "base00": "#hex", ... }, ... }
    Raises on network failure.
    """
    response = urllib.request.urlopen(BASE16_REPO_URL, timeout=15)
    tar_bytes = response.read()

    schemes: dict[str, dict[str, str]] = {}
    yaml = YAML()

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not ("/base16/" in member.name and member.name.endswith(".yaml")):
                continue
            if member.size == 0:
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            content = f.read().decode("utf-8")
            try:
                data = yaml.load(content)
            except Exception:
                continue
            if data is None:
                continue
            # The tinted-theming spec uses `name` for the scheme name and
            # nests colors under `palette`. Fall back to `scheme` and flat
            # keys for compatibility with older/different formats.
            name = data.get("name") or data.get("scheme")
            if not name:
                continue
            palette = data.get("palette")
            if not isinstance(palette, dict):
                palette = data  # flat format
            colors: dict[str, str] = {}
            for key in BASE16_KEYS:
                hex_val = palette.get(key, "000000")
                if isinstance(hex_val, str):
                    hex_val = hex_val.lstrip("#")
                    colors[key] = f"#{hex_val}"
                else:
                    colors[key] = "#000000"
            schemes[str(name)] = colors

    return schemes


def update_base16_cache(config: Config, force: bool = False) -> tuple[bool, int, str]:
    """Download base16 schemes if cache is stale or missing.

    Returns (updated, count, message). If network fails, returns (False, 0, error_msg).
    """
    cache_file = config.base16_schemes_file

    if not force and not _needs_update(cache_file):
        # Cache is fresh — load and return count
        schemes = _load_base16_cache(cache_file)
        return False, len(schemes), ""

    try:
        schemes = _download_base16_schemes()
    except Exception as e:
        return False, 0, str(e)

    # Save cache
    data = {
        "last_updated": datetime.now().isoformat(),
        "schemes": schemes,
    }
    _dump_yaml(cache_file, data)
    return True, len(schemes), ""


def _load_base16_cache(cache_file: Path) -> dict:
    """Load base16 schemes from cache file. Returns empty dict if missing."""
    if not cache_file.exists():
        return {}
    try:
        yaml = YAML()
        with open(cache_file) as f:
            doc = yaml.load(f)
        if doc is None:
            return {}
        return dict(doc.get("schemes", {}))
    except Exception:
        return {}


def load_base16_schemes(config: Config) -> dict:
    """Load base16 schemes from cache (without downloading)."""
    return _load_base16_cache(config.base16_schemes_file)


# ── YAML helpers ──────────────────────────────────────────────────


def load_palettes(config: Config) -> tuple[dict, str, dict, dict]:
    """Load palettes.yaml. Seeds with defaults if missing."""
    yaml = YAML()
    if not config.palettes_file.exists():
        config.palettes_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"active": "Default", "uses": DEFAULT_USES, "palettes": SEED_PALETTES}
        _dump_yaml(config.palettes_file, data)
        return (
            dict(SEED_PALETTES),
            "Default",
            dict(DEFAULT_USES),
            load_base16_schemes(config),
        )

    with open(config.palettes_file) as f:
        doc = yaml.load(f)
    palettes = dict(doc.get("palettes", {}))
    active = doc.get("active", "")
    uses = (
        dict(doc.get("uses", DEFAULT_USES)) if doc.get("uses") else dict(DEFAULT_USES)
    )
    if not palettes:
        palettes = dict(SEED_PALETTES)
        active = "Default"
    if active not in palettes:
        active = next(iter(palettes))

    # Load base16 schemes from cache (download happens separately in on_mount)
    base16 = load_base16_schemes(config)

    return palettes, active, uses, base16


def save_palettes(palettes: dict, active: str, uses: dict, config: Config) -> None:
    """Write palettes + active name + uses mapping to palettes.yaml."""
    data = {"active": active, "uses": uses, "palettes": palettes}
    _dump_yaml(config.palettes_file, data)


def write_theme_colors(colors: dict, config: Config, uses: dict) -> None:
    """Write active palette's colors into theme file as both base16 names and use-name aliases."""
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

    # Write base16 keys
    for key in BASE16_KEYS:
        target[key] = colors.get(key, "#000000")

    # Write use-name aliases (same hex values, different keys)
    for base16_key, use_name in uses.items():
        if base16_key in colors:
            target[use_name] = colors[base16_key]

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
    PaletteCard.-readonly .card-name {
        color: $text-muted;
    }
    .card-name {
        text-style: bold;
        padding: 0 1;
    }
    .card-swatches {
        height: 3;
        padding: 0 1;
    }
    .mini-swatch {
        width: 7;
        height: 3;
        margin: 0 2 0 0;
    }
    .card-hex {
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        name: str,
        colors_data: dict,
        is_active: bool = False,
        is_readonly: bool = False,
        display_mode: str = "hex",
        uses: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.palette_name = name
        self.colors_data = colors_data
        self.is_active = is_active
        self.is_readonly = is_readonly
        self.display_mode = display_mode
        self.uses = uses or {}

    def _format_line(self) -> str:
        """Format the color info line based on display_mode."""
        if self.display_mode == "base16":
            return "  ".join(k for k in BASE16_KEYS)
        elif self.display_mode == "use":
            return "  ".join(self.uses.get(k, k) for k in BASE16_KEYS)
        else:  # hex
            return "  ".join(self.colors_data.get(k, "???") for k in BASE16_KEYS)

    def compose(self) -> ComposeResult:
        marker = "  ★ active" if self.is_active else ""
        lock = "  🔒" if self.is_readonly else ""
        yield Label(f"{self.palette_name}{marker}{lock}", classes="card-name")
        with Horizontal(classes="card-swatches"):
            for key in BASE16_KEYS:
                hex_val = self.colors_data.get(key, "#000000")
                yield ColorSwatch(hex_val, classes="mini-swatch")
        yield Label(self._format_line(), classes="card-hex")


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
        width: 20;
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
    PaletteEditScreen #color-scroll {
        height: 20;
        max-height: 20;
        padding: 0 2;
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
        Binding("ctrl+a", "autofill", "Autofill"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self, name: str, colors: dict, uses: dict, is_new: bool = False
    ) -> None:
        super().__init__()
        self.original_name = name
        self.colors = dict(colors)
        self.uses = dict(uses)
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
            with VerticalScroll(id="color-scroll"):
                for key in BASE16_KEYS:
                    hex_val = self.colors.get(key, "#000000")
                    use_name = self.uses.get(key, key) if hasattr(self, "uses") else key
                    with Horizontal(classes="color-row"):
                        yield Label(f"{key} / {use_name}", classes="color-label")
                        yield ColorSwatch(hex_val, id=f"swatch-{key}", classes="swatch")
                        yield Input(
                            value=hex_val, id=f"color-{key}", classes="hex-input"
                        )
            yield Label(" PREVIEW", classes="section-label")
            yield Static(id="preview-mock")
            with Horizontal(classes="button-row"):
                yield Button("Autofill", id="autofill-btn", variant="primary")
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
        elif event.button.id == "autofill-btn":
            self.action_autofill()

    def action_autofill(self) -> None:
        """Derive missing colors from seed colors (base00, base05, base07)."""
        colors = self._collect_colors()
        try:
            filled = autofill_colors(colors)
        except ValueError as e:
            self.notify(str(e), severity="error", timeout=4)
            return

        # Update all input fields and swatches with derived values
        for key in BASE16_KEYS:
            try:
                input_widget = self.query_one(f"#color-{key}", Input)
                input_widget.value = filled[key]
            except Exception:
                pass
            try:
                self.query_one(f"#swatch-{key}", ColorSwatch).hex_color = filled[key]
            except Exception:
                pass

        self._update_preview()
        self.notify("Autofilled from base00 + base05 + base07", timeout=3)

    def _update_preview(self) -> None:
        colors = self._collect_colors()
        uses_rev = {v: k for k, v in self.uses.items()}
        try:
            mock = self.query_one("#preview-mock", Static)
            bg = colors.get(uses_rev.get("bg", "base00"), "#000000")
            text = colors.get(uses_rev.get("text", "base05"), "#fff")
            accent = colors.get(uses_rev.get("accent", "base07"), "#0f0")
            urgent = colors.get(uses_rev.get("urgent", "base0F"), "#f00")
            mock.styles.background = Color.parse(bg)
            mock.update(
                f"[{text}]Main System Dashboard[/]\n"
                f"[{accent}]CPU: 14% | RAM: 4.2GB[/]\n"
                f"[{urgent}]! Low battery[/]"
            )
        except Exception:
            pass

    def _collect_colors(self) -> dict:
        colors: dict[str, str] = {}
        for key in BASE16_KEYS:
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


class UsesEditScreen(ModalScreen):
    """Modal screen for editing the base16 → use-name mapping."""

    DEFAULT_CSS = """
    UsesEditScreen {
        align: center middle;
    }
    UsesEditScreen > #uses-dialog {
        width: 60;
        max-width: 92%;
        height: auto;
        max-height: 88%;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    UsesEditScreen .section-label {
        background: $primary;
        text-style: bold;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    UsesEditScreen .use-row {
        height: 3;
        layout: horizontal;
        padding: 0 2;
        align: center middle;
    }
    UsesEditScreen .base16-label {
        width: 12;
        content-align: right middle;
    }
    UsesEditScreen .arrow {
        width: 3;
        content-align: center middle;
        color: $text-muted;
    }
    UsesEditScreen .use-input {
        width: 30;
    }
    UsesEditScreen #use-scroll {
        height: 20;
        max-height: 20;
        padding: 0 2;
    }
    UsesEditScreen .button-row {
        height: 3;
        padding: 1 2 0 2;
        align: center middle;
    }
    UsesEditScreen .button-row Button {
        margin: 0 1;
    }
    UsesEditScreen .help-text {
        color: $text-muted;
        padding: 0 2;
        height: 3;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, uses: dict) -> None:
        super().__init__()
        self.uses = dict(uses)

    def compose(self) -> ComposeResult:
        with Container(id="uses-dialog"):
            yield Label(" EDIT USE-NAMES", classes="section-label")
            yield Label(
                " Rename use-name aliases. base16 keys never change.",
                classes="help-text",
            )
            with VerticalScroll(id="use-scroll"):
                for key in BASE16_KEYS:
                    use_name = self.uses.get(key, key)
                    with Horizontal(classes="use-row"):
                        yield Label(key, classes="base16-label")
                        yield Label("→", classes="arrow")
                        yield Input(
                            value=use_name, id=f"use-{key}", classes="use-input"
                        )
            with Horizontal(classes="button-row"):
                yield Button("Save", id="save-btn", variant="success")
                yield Button("Cancel", id="cancel-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def _collect_uses(self) -> dict:
        uses: dict[str, str] = {}
        for key in BASE16_KEYS:
            try:
                uses[key] = self.query_one(
                    f"#use-{key}", Input
                ).value.strip() or self.uses.get(key, key)
            except Exception:
                uses[key] = self.uses.get(key, key)
        return uses

    def action_save(self) -> None:
        self.dismiss(self._collect_uses())

    def action_cancel(self) -> None:
        self.dismiss(None)


# ── Fuzzy search ──────────────────────────────────────────────────


def fuzzy_match(query: str, text: str) -> bool:
    """Return True if query fuzzy-matches text (subsequence match, case-insensitive).

    Every character in query must appear in text in order, but not necessarily
    contiguously. Empty query matches everything.
    """
    if not query:
        return True
    query = query.lower()
    text = text.lower()
    qi = 0
    for ch in text:
        if qi < len(query) and ch == query[qi]:
            qi += 1
    return qi == len(query)


def palette_matches(query: str, name: str, colors: dict) -> bool:
    """Check if a palette matches the search query by name or hex codes."""
    if fuzzy_match(query, name):
        return True
    query_lower = query.lower()
    for key in BASE16_KEYS:
        hex_val = colors.get(key, "")
        if query_lower in hex_val.lower():
            return True
    return False


# ── Main app ─────────────────────────────────────────────────────


class PaletteApp(App):
    """Palette manager with configurable apply behavior."""

    TITLE = "Palette Manager"
    SUB_TITLE = ""  # set in __init__

    CSS = """
    #palette-list {
        height: 1fr;
        padding: 0 1;
        overflow-y: hidden;
    }
    #search-bar {
        height: 3;
        padding: 0 2;
        dock: top;
    }
    #search-input {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("up", "navigate(-1)", "↑", show=False, priority=True),
        Binding("down", "navigate(1)", "↓", show=False, priority=True),
        Binding("k", "navigate(-1)", show=False, priority=True),
        Binding("j", "navigate(1)", show=False, priority=True),
        Binding("pageup", "page_up", "PgUp", show=False, priority=True),
        Binding("pagedown", "page_down", "PgDn", show=False, priority=True),
        Binding("home", "scroll_top", "Home", show=False, priority=True),
        Binding("end", "scroll_bottom", "End", show=False, priority=True),
        Binding("enter", "edit", "Edit", show=False),
        Binding("e", "edit", "Edit"),
        Binding("n", "new", "New"),
        Binding("d", "delete", "Delete"),
        Binding("u", "edit_uses", "Use-names"),
        Binding("v", "cycle_display", "View"),
        Binding("a", "activate", "Activate"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+p", "noop", show=False),
        Binding("/", "focus_search", "Search", show=False),
        Binding("escape", "blur_search", show=False),
    ]

    selected_index = reactive(0)
    display_mode = reactive("hex")
    search_query = reactive("")
    scroll_offset = reactive(0)

    CARD_HEIGHT = 4
    DISPLAY_MODES = ["hex", "base16", "use"]
    DISPLAY_LABELS = {"hex": "hex", "base16": "base16", "use": "use-names"}

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.palettes, self.active_palette, self.uses, self.base16_schemes = (
            load_palettes(config)
        )
        self.readonly = set(self.base16_schemes.keys())
        self.SUB_TITLE = str(config.palettes_file)
        self._filter_cache: tuple[str, list[tuple[str, dict]]] | None = None
        self._search_counter = 0

    # ── Compose ───────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="search-bar"):
            yield Input(
                placeholder="Search palettes by name or hex code…  (/ to focus, Esc to clear)",
                id="search-input",
            )
        yield Static(id="palette-list")
        yield Footer()

    def on_mount(self) -> None:
        self._render_list()
        self._update_base16_schemes()

    def _update_base16_schemes(self) -> None:
        """Download base16 schemes if cache is stale."""
        import threading

        def do_update():
            updated, count, err = update_base16_cache(self.config)
            if updated and count > 0:
                self.base16_schemes = load_base16_schemes(self.config)
                self.readonly = set(self.base16_schemes.keys())
                self._invalidate_cache()
                self.call_from_thread(self._on_base16_updated, count)
            elif err and not self.base16_schemes:
                pass

        thread = threading.Thread(target=do_update, daemon=True)
        thread.start()

    def _on_base16_updated(self, count: int) -> None:
        self._render_list()
        self.notify(f"Updated {count} base16 schemes", timeout=3)

    # ── Data helpers ──────────────────────────────────────────────

    def _all_palettes(self) -> dict:
        all_palettes = {}
        all_palettes.update(self.palettes)
        for name, colors in self.base16_schemes.items():
            if name not in all_palettes:
                all_palettes[name] = colors
        return all_palettes

    def _filtered_list(self) -> list[tuple[str, dict]]:
        """Return filtered palettes as a list of (name, colors) tuples. Cached."""
        if (
            self._filter_cache is not None
            and self._filter_cache[0] == self.search_query
        ):
            return self._filter_cache[1]
        all_palettes = self._all_palettes()
        if not self.search_query:
            result = list(all_palettes.items())
        else:
            result = [
                (name, colors)
                for name, colors in all_palettes.items()
                if palette_matches(self.search_query, name, colors)
            ]
        self._filter_cache = (self.search_query, result)
        return result

    def _invalidate_cache(self) -> None:
        self._filter_cache = None

    def _palette_names(self) -> list[str]:
        return [name for name, _ in self._filtered_list()]

    def _get_palette_colors(self, name: str) -> dict:
        if name in self.palettes:
            return self.palettes[name]
        if name in self.base16_schemes:
            return self.base16_schemes[name]
        return {}

    def _selected_name(self) -> str | None:
        filtered = self._filtered_list()
        if not filtered:
            return None
        idx = min(self.selected_index, len(filtered) - 1)
        return filtered[idx][0]

    # ── Virtualized rendering ─────────────────────────────────────

    def _visible_count(self) -> int:
        try:
            widget = self.query_one("#palette-list", Static)
            height = widget.size.height
            if height <= 0:
                height = 40
            return max(1, height // self.CARD_HEIGHT)
        except Exception:
            return 10

    def _render_list(self) -> None:
        """Render the visible window of palette cards into the Static widget."""
        try:
            widget = self.query_one("#palette-list", Static)
        except Exception:
            return

        filtered = self._filtered_list()
        total = len(filtered)

        if total == 0:
            widget.update(Text("[dim]No palettes match search[/]"))
            return
        if self.selected_index >= total:
            self.selected_index = total - 1
        if self.selected_index < 0:
            self.selected_index = 0

        vis = self._visible_count()
        if self.scroll_offset > self.selected_index:
            self.scroll_offset = self.selected_index
        elif self.scroll_offset + vis <= self.selected_index:
            self.scroll_offset = self.selected_index - vis + 1
        if self.scroll_offset < 0:
            self.scroll_offset = 0

        start = self.scroll_offset
        end = min(start + vis, total)

        text = Text()
        for i in range(start, end):
            name, colors = filtered[i]
            is_active = name == self.active_palette
            is_readonly = name in self.readonly
            is_selected = i == self.selected_index
            self._render_card(text, name, colors, is_active, is_readonly, is_selected)

        if total > vis:
            text.append(Text(f"\n  {start + 1}-{end} of {total}", style="dim"))

        widget.update(text)

    def _render_card(
        self,
        text: Text,
        name: str,
        colors: dict,
        is_active: bool,
        is_readonly: bool,
        is_selected: bool,
    ) -> None:
        """Append a single card to the text buffer."""
        prefix = "> " if is_selected else "  "
        marker = "  *" if is_active else ""
        lock = "  (lock)" if is_readonly else ""
        name_style = "bold" if is_selected else ""
        if is_readonly and not is_selected:
            name_style = "dim"
        text.append(Text(f"{prefix}{name}{marker}{lock}\n", style=name_style))

        text.append("  ")
        for key in BASE16_KEYS:
            hex_val = colors.get(key, "#000000")
            h = hex_val.lstrip("#")
            if len(h) == 8:
                h = h[:6]
            try:
                style = Style(bgcolor=f"#{h}")
            except Exception:
                style = Style()
            text.append(" " * 7, style=style)
            text.append("  ")
        text.append("\n")

        if self.display_mode == "base16":
            info = "  ".join(BASE16_KEYS)
        elif self.display_mode == "use":
            info = "  ".join(self.uses.get(k, k) for k in BASE16_KEYS)
        else:
            info = "  ".join(colors.get(k, "???") for k in BASE16_KEYS)
        text.append(Text(f"  {info}\n", style="dim"))
        text.append("\n")

    # ── Reactive watchers ─────────────────────────────────────────

    def watch_selected_index(self, _idx: int) -> None:
        self._render_list()

    def watch_scroll_offset(self, _idx: int) -> None:
        self._render_list()

    def watch_display_mode(self, _mode: str) -> None:
        self._render_list()

    # ── Actions: navigation ───────────────────────────────────────

    def action_navigate(self, delta: int) -> None:
        total = len(self._filtered_list())
        max_idx = max(total - 1, 0)
        self.selected_index = max(0, min(self.selected_index + delta, max_idx))

    def action_page_up(self) -> None:
        vis = self._visible_count()
        self.selected_index = max(0, self.selected_index - vis)

    def action_page_down(self) -> None:
        total = len(self._filtered_list())
        vis = self._visible_count()
        self.selected_index = min(total - 1, self.selected_index + vis)

    def action_scroll_top(self) -> None:
        self.selected_index = 0
        self.scroll_offset = 0

    def action_scroll_bottom(self) -> None:
        total = len(self._filtered_list())
        self.selected_index = max(0, total - 1)

    # ── Actions: search ───────────────────────────────────────────

    def action_focus_search(self) -> None:
        try:
            self.query_one("#search-input", Input).focus()
        except Exception:
            pass

    def action_blur_search(self) -> None:
        try:
            search_input = self.query_one("#search-input", Input)
            if search_input.focused:
                search_input.value = ""
                self.search_query = ""
                self.selected_index = 0
                self.scroll_offset = 0
                self._filter_cache = None
                self._render_list()
                self.query_one("#palette-list", Static).focus()
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input with 150ms debounce."""
        if event.input.id != "search-input":
            return
        self._search_counter += 1
        current = self._search_counter
        value = event.value
        self.set_timer(0.15, lambda: self._do_search(value, current))

    def _do_search(self, value: str, expected: int) -> None:
        if expected != self._search_counter:
            return
        self.search_query = value.strip()
        self.selected_index = 0
        self.scroll_offset = 0
        self._filter_cache = None
        self._render_list()

    # ── Actions: display mode ─────────────────────────────────────

    def action_cycle_display(self) -> None:
        idx = self.DISPLAY_MODES.index(self.display_mode)
        self.display_mode = self.DISPLAY_MODES[(idx + 1) % len(self.DISPLAY_MODES)]
        self.notify(f"View: {self.DISPLAY_LABELS[self.display_mode]}", timeout=2)

    # ── Actions: mouse ────────────────────────────────────────────

    def on_click(self, event) -> None:
        """Click on the palette list selects the card at that y position."""
        if event.widget and event.widget.id == "palette-list":
            try:
                rel_y = event.y - event.widget.gutter.top
            except Exception:
                rel_y = event.y
            card_idx = self.scroll_offset + rel_y // self.CARD_HEIGHT
            total = len(self._filtered_list())
            if 0 <= card_idx < total:
                self.selected_index = card_idx

    # ── Actions: palette management ───────────────────────────────

    def action_edit(self) -> None:
        name = self._selected_name()
        if name is None:
            return

        if name in self.readonly:
            self._duplicate_palette(name)
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
            self._invalidate_cache()
            save_palettes(self.palettes, self.active_palette, self.uses, self.config)
            self._render_list()
            self.notify(f"Saved '{new_name}'", timeout=2)

        self.push_screen(
            PaletteEditScreen(name, self.palettes[name], self.uses),
            on_result,
        )

    def _duplicate_palette(self, source_name: str) -> None:
        source_colors = self._get_palette_colors(source_name)
        base_name = f"{source_name} (copy)"
        new_name = base_name
        n = 2
        all_names = set(self._palette_names())
        while new_name in all_names:
            new_name = f"{base_name} {n}"
            n += 1

        def on_result(result):
            if result is None:
                return
            final_name, new_colors = result
            self.palettes[final_name] = new_colors
            self._invalidate_cache()
            save_palettes(self.palettes, self.active_palette, self.uses, self.config)
            self.selected_index = self._palette_names().index(final_name)
            self._render_list()
            self.notify(f"Duplicated '{source_name}' -> '{final_name}'", timeout=3)

        self.push_screen(
            PaletteEditScreen(new_name, source_colors, self.uses, is_new=True),
            on_result,
        )

    def action_new(self) -> None:
        default_colors = dict(SEED_PALETTES["Catppuccin Mocha"])
        base = "New Palette"
        name = base
        n = 2
        all_names = set(self._palette_names())
        while name in all_names:
            name = f"{base} {n}"
            n += 1

        def on_result(result):
            if result is None:
                return
            new_name, new_colors = result
            self.palettes[new_name] = new_colors
            self._invalidate_cache()
            save_palettes(self.palettes, self.active_palette, self.uses, self.config)
            self.selected_index = self._palette_names().index(new_name)
            self._render_list()
            self.notify(f"Created '{new_name}'", timeout=2)

        self.push_screen(
            PaletteEditScreen(name, default_colors, self.uses, is_new=True),
            on_result,
        )

    def action_delete(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if name in self.readonly:
            self.notify(
                "Cannot delete a built-in base16 scheme", severity="warning", timeout=3
            )
            return
        if len(self.palettes) + len(self.base16_schemes) <= 1:
            self.notify("Cannot delete the last palette", severity="error")
            return
        del self.palettes[name]
        if self.active_palette == name:
            all_palettes = {}
            all_palettes.update(self.base16_schemes)
            all_palettes.update(self.palettes)
            self.active_palette = next(iter(all_palettes)) if all_palettes else ""
        if self.selected_index >= len(self._palette_names()):
            self.selected_index = max(0, len(self._palette_names()) - 1)
        self._invalidate_cache()
        save_palettes(self.palettes, self.active_palette, self.uses, self.config)
        self._render_list()
        self.notify(f"Deleted '{name}'", timeout=2)

    def action_edit_uses(self) -> None:
        def on_result(result):
            if result is None:
                return
            self.uses = result
            save_palettes(self.palettes, self.active_palette, self.uses, self.config)
            self._render_list()
            self.notify("Updated use-names", timeout=2)

        self.push_screen(UsesEditScreen(self.uses), on_result)

    def action_activate(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        self.active_palette = name
        colors = self._get_palette_colors(name)
        if self.config.theme_file is not None:
            write_theme_colors(colors, self.config, self.uses)
        save_palettes(self.palettes, self.active_palette, self.uses, self.config)
        self._render_list()
        if self.config.apply_command:
            self.notify(
                f"Applied '{name}' — running {self.config.apply_command}...", timeout=3
            )
            ok, msg = run_apply_command(self.config)
            if ok and msg:
                self.notify(msg, timeout=3)
            elif not ok:
                self.notify(msg, timeout=5, severity="error")
        else:
            self.notify(f"Saved '{name}' as active", timeout=2)

    def action_noop(self) -> None:
        pass


# ── CLI entry points ─────────────────────────────────────────────


def check_palettes(config: Config) -> int:
    palettes, active, uses, base16 = load_palettes(config)
    print(f"\n  Palettes: {config.palettes_file}")
    if config.theme_file:
        print(
            f"  Theme:    {config.theme_file}"
            + (f" ({config.theme_path})" if config.theme_path else "")
        )
    if config.apply_command:
        print(f"  Apply:    {config.apply_command}")
    print(f"\n  Active: {active}\n")

    # User palettes
    if palettes:
        print("  ── User Palettes ──\n")
        for name, colors in palettes.items():
            marker = " ★" if name == active else ""
            print(f"  {name}{marker}")
            for k in BASE16_KEYS:
                use = uses.get(k, "")
                v = colors.get(k, "???")
                print(f"    {k} / {use:12s} {v}")
            print()

    # Base16 schemes
    if base16:
        print(f"  ── Base16 Schemes ({len(base16)}) ──\n")
        for name, colors in base16.items():
            marker = " ★" if name == active else ""
            print(f"  {name}{marker}  🔒")
            for k in BASE16_KEYS:
                use = uses.get(k, "")
                v = colors.get(k, "???")
                print(f"    {k} / {use:12s} {v}")
            print()

    return 0


def apply_noninteractive(config: Config) -> int:
    palettes, active, uses, base16 = load_palettes(config)
    all_palettes = {}
    all_palettes.update(base16)
    all_palettes.update(palettes)
    if not all_palettes or not active:
        print("No active palette found", file=sys.stderr)
        return 1
    colors = all_palettes.get(active, {})
    if config.theme_file is not None:
        write_theme_colors(colors, config, uses)
        print(f"Written '{active}' colors to {config.theme_file}")
    save_palettes(palettes, active, uses, config)
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
    parser.add_argument(
        "--update-base16",
        action="store_true",
        help="Force-update base16 schemes cache and exit",
    )
    args = parser.parse_args()

    if args.init:
        sys.exit(init_config(args.config))

    config = load_config(args.config)

    if args.update_base16:
        updated, count, err = update_base16_cache(config, force=True)
        if err:
            print(f"Failed: {err}", file=sys.stderr)
            sys.exit(1)
        print(f"{'Updated' if updated else 'Cache fresh'}: {count} base16 schemes")
        sys.exit(0)

    if args.check:
        sys.exit(check_palettes(config))

    if args.apply:
        sys.exit(apply_noninteractive(config))

    PaletteApp(config).run()
