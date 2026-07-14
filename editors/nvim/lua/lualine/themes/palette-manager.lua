--[[
            _     _   _                                             
 _ __  __ _| |___| |_| |_ ___ ___ _ __  __ _ _ _  __ _ __ _ ___ _ _ 
| '_ \/ _` | / -_)  _|  _/ -_)___| '  \/ _` | ' \/ _` / _` / -_) '_|
| .__/\__,_|_\___|\__|\__\___|   |_|_|_\__,_|_||_\__,_\__, \___|_|  
|_|                                                   |___/        

Lualine theme for palette-manager — reads from the palette-manager color
table (which resolves base16 colors from theme.lua at runtime).

Used by lualine.lua: `theme = 'palette-manager'`
]]

local c = require('palette-manager.colors')

return {
  normal = {
    a = { fg = c.bg0, bg = c.blue, gui = 'bold' },
    b = { fg = c.fg, bg = c.bg2 },
    c = { fg = c.fg, bg = c.bg1 },
  },
  insert = {
    a = { fg = c.bg0, bg = c.green, gui = 'bold' },
    b = { fg = c.fg, bg = c.bg2 },
    c = { fg = c.fg, bg = c.bg1 },
  },
  visual = {
    a = { fg = c.bg0, bg = c.purple, gui = 'bold' },
    b = { fg = c.fg, bg = c.bg2 },
    c = { fg = c.fg, bg = c.bg1 },
  },
  replace = {
    a = { fg = c.bg0, bg = c.red, gui = 'bold' },
    b = { fg = c.fg, bg = c.bg2 },
    c = { fg = c.fg, bg = c.bg1 },
  },
  command = {
    a = { fg = c.bg0, bg = c.yellow, gui = 'bold' },
    b = { fg = c.fg, bg = c.bg2 },
    c = { fg = c.fg, bg = c.bg1 },
  },
  inactive = {
    a = { fg = c.grey, bg = c.bg1 },
    b = { fg = c.grey, bg = c.bg1 },
    c = { fg = c.grey, bg = c.bg1 },
  },
}
