# Architectuur

## Flow

1. Serienummer wordt geregistreerd in Q-Box Central.
2. Q-Box krijgt bij productie of installatie een serial en claim token.
3. Agent start na boot en bereikt Central via ZeroTier overlay.
4. Agent roept `/api/provision/request` aan.
5. Central valideert serial + claim token.
6. Central autoriseert automatisch of zet device op pending.
7. Agent stuurt heartbeat, apps en metrics.
8. Central kan OTA jobs of app installs klaarzetten.

## Modules

### Provisioning API
Verwerkt eerste boot, claim token validatie, deviceconfig en heartbeat interval.

### Serial registry
Bron van waarheid voor serials, tokens, model en initiële klantgegevens.

### Auto authorization
Testmodus autoriseert automatisch. Productiemodus moet policy-based werken: gekend serial, correct claim token, eventueel ZeroTier node-id allowlist.

### Customer mapping
Koppelt device aan klant, site en installatienaam.

### OTA management
Queue met firmware/app opdrachten. De test-agent markeert jobs als uitgevoerd. Command execution staat standaard uit.

### App manager
Houdt bij welke apps de agent rapporteert. Installatie/update via jobqueue kan later worden uitgebreid met Docker Compose bundles.

### Device inventory
Overzicht van serial, klant, site, firmware, apps, status, laatste heartbeat en ZeroTier informatie.
