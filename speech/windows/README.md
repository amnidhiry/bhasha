# Speech service on a Windows PC with an NVIDIA GPU

bhasha stays on the homelab; only this small service runs on the PC. bhasha calls it over the
LAN, caches every clip, and falls back to the homelab's CPU service or the device voice when the
PC is off.

1. Install Python 3.12 from python.org (tick "Add python.exe to PATH") and a current NVIDIA driver.
2. Copy or clone this repo's `speech\` folder onto the PC, then in PowerShell from that folder:
   ```powershell
   powershell -ExecutionPolicy Bypass -File windows\install.ps1
   ```
   It should print `CUDA available: True`.
3. Open the firewall port once, in an Administrator PowerShell:
   ```powershell
   powershell -ExecutionPolicy Bypass -File windows\firewall.ps1
   ```
4. Pick a token (`openssl rand -hex 24` on the homelab) and start the service:
   ```powershell
   powershell -ExecutionPolicy Bypass -File windows\run.ps1 -Token <token>
   ```
   The first request downloads the Kokoro weights (~330 MB) from Hugging Face.
5. Optional: start it at logon with `windows\autostart.ps1 -Token <token>`.
6. On the homelab, in bhasha's `.env`:
   ```
   BHASHA_SPEECH_URL=http://<pc-name-or-ip>:8790
   BHASHA_SPEECH_TOKEN=<token>
   ```
   then `docker compose up -d`. Progress → Voice shows the engine and device (`cuda`) and runs the
   tone check.

Untested on Windows so far; please report what breaks.
