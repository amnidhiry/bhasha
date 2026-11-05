# Install the bhasha speech service on a Windows PC with an NVIDIA GPU.
# Run in PowerShell from the speech\ folder:  powershell -ExecutionPolicy Bypass -File windows\install.ps1
# Needs Python 3.11 or 3.12 from python.org (tick "Add to PATH") and a current NVIDIA driver.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
# CUDA build of PyTorch (works with any recent NVIDIA driver). Use .../whl/cpu for CPU only.
.\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python -m pip install -e ".[kokoro]"
.\.venv\Scripts\python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
Write-Host "Installed. Next: windows\run.ps1 (and windows\firewall.ps1 once, as Administrator)."
