# Install / update Token Master into the local Hermes home.
#
# Two halves, one plugin id:
#   plugin/desktop/plugin.js   ->  <hermes home>/desktop-plugins/token-master/plugin.js
#   plugin/{plugin.yaml,...}   ->  <hermes home>/plugins/token-master/
#
# The Desktop app hot-reloads the UI half; the backend router hot-mounts on first request.

$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$home_dir = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }

if (-not (Test-Path (Join-Path $home_dir 'state.db'))) {
    throw "No Hermes home at $home_dir (state.db missing). Set HERMES_HOME or install Hermes first."
}

$desktop_dir = Join-Path $home_dir 'desktop-plugins\token-master'
$plugin_dir = Join-Path $home_dir 'plugins\token-master'
$data_dir = Join-Path $home_dir 'plugin-data\token-master'

New-Item -ItemType Directory -Force -Path $desktop_dir, (Join-Path $plugin_dir 'dashboard'), $data_dir | Out-Null

Copy-Item (Join-Path $repo 'plugin\desktop\plugin.js') (Join-Path $desktop_dir 'plugin.js') -Force
Copy-Item (Join-Path $repo 'plugin\plugin.yaml') (Join-Path $plugin_dir 'plugin.yaml') -Force
Copy-Item (Join-Path $repo 'plugin\__init__.py') (Join-Path $plugin_dir '__init__.py') -Force
Copy-Item (Join-Path $repo 'plugin\dashboard\manifest.json') (Join-Path $plugin_dir 'dashboard\manifest.json') -Force
Copy-Item (Join-Path $repo 'plugin\dashboard\plugin_api.py') (Join-Path $plugin_dir 'dashboard\plugin_api.py') -Force

Write-Host "Copied plugin into $home_dir"

$hermes = Join-Path $home_dir 'bin\hermes.exe'
if (Test-Path $hermes) {
    & $hermes plugins enable token-master
    if ($LASTEXITCODE -ne 0) { Write-Warning "hermes plugins enable returned $LASTEXITCODE" }
} else {
    Write-Warning "hermes.exe not found at $hermes - enable the plugin yourself: hermes plugins enable token-master"
}

Write-Host ''
Write-Host 'Done. Open Hermes Desktop -> Token Master (sidebar), or command palette: "Open Token Master".'
