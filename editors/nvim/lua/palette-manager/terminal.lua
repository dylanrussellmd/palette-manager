--[[
            _     _   _                                             
 _ __  __ _| |___| |_| |_ ___ ___ _ __  __ _ _ _  __ _ __ _ ___ _ _ 
| '_ \/ _` | / -_)  _|  _/ -_)___| '  \/ _` | ' \/ _` / _` / -_) '_|
| .__/\__,_|_\___|\__|\__\___|   |_|_|_\__,_|_||_\__,_\__, \___|_|  
|_|                                                   |___/        

Terminal ANSI 16-color palette — maps base16 colors to terminal color slots.
]]

local M = {}
local cfg = vim.g.palette_manager_config
local c = require('palette-manager.colors')

function M.setup()
  if not cfg.term_colors then
    return
  end
  vim.g.terminal_color_0 = c.contrast
  vim.g.terminal_color_1 = c.red
  vim.g.terminal_color_2 = c.green
  vim.g.terminal_color_3 = c.yellow
  vim.g.terminal_color_4 = c.blue
  vim.g.terminal_color_5 = c.purple
  vim.g.terminal_color_6 = c.cyan
  vim.g.terminal_color_7 = c.fg
  vim.g.terminal_color_8 = c.grey
  vim.g.terminal_color_9 = c.red
  vim.g.terminal_color_10 = c.green
  vim.g.terminal_color_11 = c.yellow
  vim.g.terminal_color_12 = c.blue
  vim.g.terminal_color_13 = c.purple
  vim.g.terminal_color_14 = c.cyan
  vim.g.terminal_color_15 = c.fg
end

return M
