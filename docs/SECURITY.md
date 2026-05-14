# Security todo voor productie

- Gebruik unieke claim tokens per Q-Box.
- Zet `QBOX_AUTO_AUTHORIZE=false` buiten testomgevingen.
- Gebruik HTTPS, ook binnen ZeroTier.
- Voeg admin-authenticatie toe aan Central API en dashboard.
- Beperk API toegang tot ZeroTier subnet en/of reverse proxy ACL.
- Laat agent alleen gesigneerde OTA bundles uitvoeren.
- Gebruik audit logs voor authorization, OTA en app installs.
