# API voorbeelden

## Serial registreren

```bash
curl -X POST http://localhost:8080/api/serials \
  -H 'content-type: application/json' \
  -d '{"serial":"QBX-2026-0001","name":"Q-Box Demo","claim_token":"dev-claim-token"}'
```

## Provisioning request

```bash
curl -X POST http://localhost:8080/api/provision/request \
  -H 'content-type: application/json' \
  -d '{"serial":"QBX-2026-0001","claim_token":"dev-claim-token","hostname":"qbox-test"}'
```

## OTA job aanmaken

```bash
curl -X POST 'http://localhost:8080/api/ota/deploy?serial=QBX-2026-0001&target_firmware=2026.05.1'
```
