$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = if ($env:CDSS_PYTHON) { $env:CDSS_PYTHON } else { 'C:\Users\wajda\AppData\Local\Programs\Python\Python313\python.exe' }
if (-not (Test-Path $python)) { throw "Python interpreter not found: $python. Set CDSS_PYTHON to its full path." }
Set-Location $root
& $python "$PSScriptRoot\run_all.py"
