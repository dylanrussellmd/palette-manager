--[[
            _     _   _                                             
 _ __  __ _| |___| |_| |_ ___ ___ _ __  __ _ _ _  __ _ __ _ ___ _ _ 
| '_ \/ _` | / -_)  _|  _/ -_)___| '  \/ _` | ' \/ _` / _` / -_) '_|
| .__/\__,_|_\___|\__|\__\___|   |_|_|_\__,_|_||_\__,_\__, \___|_|  
|_|                                                   |___/        

Color resolution — reads the 16 base16 colors from the external theme file
(default: ~/.config/palette-manager/theme.lua) and derives the 24+ internal
color names that the highlight groups reference.

The theme file is a plain Lua file returning a table with:
  - base16 names: base00–base0F
  - use-name aliases: bg, surface, text, accent, red, green, blue, etc.

This module supports both naming schemes — use-name aliases take priority,
falling back to base16 names. Any external tool can write the theme file
as long as it returns a valid Lua table.
]]

local util = require('palette-manager.util')

---Get theme file path from config
---@return string
local function get_theme_path()
	local config = vim.g.palette_manager_config or {}
	return config.theme_file
		or (os.getenv('XDG_CONFIG_HOME') or vim.fn.expand('~/.config')) .. '/palette-manager/theme.lua'
end

---Load the theme file from disk
---Uses loadfile (returns nil on error instead of throwing)
---@return table
local function load_theme()
	local path = get_theme_path()
	local fn = loadfile(path)
	if not fn then
		vim.schedule(function()
			vim.notify(
				'palette-manager: theme file not found at ' .. path,
				vim.log.levels.WARN
			)
		end)
		return {}
	end
	local ok, theme = pcall(fn)
	if not ok or type(theme) ~= 'table' then
		vim.schedule(function()
			vim.notify('palette-manager: invalid theme file at ' .. path, vim.log.levels.ERROR)
		end)
		return {}
	end
	return theme
end

local theme = load_theme()

---Resolve a color by use-name, falling back to base16 name, then default
---@param use_name string: e.g. 'bg', 'surface', 'text'
---@param base16_name string: e.g. 'base00', 'base01', 'base05'
---@param fallback string: hex color used if neither is found
---@return string
local function color(use_name, base16_name, fallback)
	return theme[use_name] or theme[base16_name] or fallback or '#000000'
end

-- Derived color table — internal 24+ color names resolved from base16
local derived = {
	none = 'none',

	-- Direct base16 mappings (use-name → internal name)
	bg0 = color('bg', 'base00'),
	bg1 = color('surface', 'base01'),
	bg2 = color('selection', 'base02'),
	bg_blue = color('blue', 'base0D'),
	bg_yellow = color('yellow', 'base0A'),
	fg = color('text', 'base05'),
	grey = color('muted', 'base03'),
	light_grey = color('border', 'base04'),
	purple = color('magenta', 'base0E'),
	green = color('green', 'base0B'),
	orange = color('orange', 'base09'),
	blue = color('blue', 'base0D'),
	yellow = color('yellow', 'base0A'),
	cyan = color('cyan', 'base0C'),
	red = color('red', 'base08'),

	-- Derived shades (no base16 equivalent — computed via util.darken/lighten)
	bg_d = util.darken(color('bg', 'base00'), 0.3),
	bg3 = util.lighten(color('selection', 'base02'), 0.1),
	bright_purple = util.lighten(color('magenta', 'base0E'), 0.3),
	light_blue = util.lighten(color('blue', 'base0D'), 0.3),
	coral = util.lighten(color('red', 'base08'), 0.2),
	contrast = util.darken(color('bg', 'base00'), 0.6),
	inverse = util.lighten(color('text', 'base05'), 1.0),

	-- Diff colors (darkened accents for diff backgrounds)
	diff_add = util.darken(color('green', 'base0B'), 0.6),
	diff_delete = util.darken(color('red', 'base08'), 0.6),
	diff_change = util.darken(color('blue', 'base0D'), 0.6),
	diff_text = util.darken(color('blue', 'base0D'), 0.4),
}

local function select_colors()
	local selected = { none = 'none' }
	selected = vim.tbl_extend('force', selected, derived)
	-- Merge user overrides from config
	if vim.g.palette_manager_config and vim.g.palette_manager_config.colors then
		selected = vim.tbl_extend('force', selected, vim.g.palette_manager_config.colors)
	end
	return selected
end

return select_colors()
