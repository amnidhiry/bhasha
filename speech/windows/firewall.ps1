# Allow bhasha (on the LAN) to reach the speech service. Run once as Administrator.
New-NetFirewallRule -DisplayName "bhasha speech (8790)" -Direction Inbound -Protocol TCP -LocalPort 8790 `
  -Profile Private -Action Allow
