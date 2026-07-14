--[[
            _     _   _                                             
 _ __  __ _| |___| |_| |_ ___ ___ _ __  __ _ _ _  __ _ __ _ ___ _ _ 
| '_ \/ _` | / -_)  _|  _/ -_)___| '  \/ _` | ' \/ _` / _` / -_) '_|
| .__/\__,_|_\___|\__|\__\___|   |_|_|_\__,_|_||_\__,_\__, \___|_|  
|_|                                                   |___/        

Colorscheme entry point — sourced by `:colorscheme palette-manager`.

Clears cached palette-manager modules so re-sourcing picks up palette
changes (e.g. after the theme file is regenerated on disk).
]]

for k in pairs(package.loaded) do
  if k:match('^palette%-manager') then
    package.loaded[k] = nil
  end
end

vim.o.background = 'dark'
require('palette-manager').colorscheme()
