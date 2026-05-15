# Q-Central Portal API v1

Q-Central exposes a read-only API for Q-Portal so customer-facing applications can query Q-Box device information by serial number, customer or site.

## Swagger / OpenAPI

After deployment, the interactive API documentation is available at:

```text
https://central.q-home.be/docs
```

The raw OpenAPI schema is available at:

```text
https://central.q-home.be/openapi.json
```

## Authentication

Portal API calls use a dedicated bearer token. This is separate from the Q-Central admin session.

Use either:

```http
Authorization: Bearer <portal-token>
```

or:

```http
X-Portal-Token: <portal-token>
```

The token is stored server-side as a bcrypt hash in the production `.env` file:

```env
Q_CENTRAL_PORTAL_TOKEN_HASH=$2b$...
```

## Endpoints

### Lookup device by serial

```http
GET /api/portal/device/{serial}
Authorization: Bearer <portal-token>
```

Example:

```bash
curl -H "Authorization: Bearer $PORTAL_TOKEN" \
  https://central.q-home.be/api/portal/device/QBX-TEST-0002
```

Response:

```json
{
  "serial": "QBX-TEST-0002",
  "name": "Test Q-Box 2",
  "customer": "Q-Home",
  "site": "Testsite",
  "model": "Q-Box ARM64",
  "status": "online",
  "authorized": true,
  "firmware": "dev",
  "target_firmware": null,
  "agent_version": "1.0.2",
  "hostname": "loxberry",
  "ip_address": "10.121.15.12",
  "last_seen": "2026-05-15T08:12:00",
  "apps": ["qbox-agent", "mqtt", "homeassistant"],
  "metrics": {
    "cpu_percent": 17,
    "mem_percent": 15,
    "disk_percent": 62
  },
  "zerotier": {
    "node_id": "8056c2e21c",
    "network_id": "xxxxxxxxxxxxxxxx"
  }
}
```

### List devices

```http
GET /api/portal/devices
Authorization: Bearer <portal-token>
```

Optional filters:

```http
GET /api/portal/devices?customer=Q-Home
GET /api/portal/devices?site=Testsite
GET /api/portal/devices?customer=Q-Home&site=Testsite
```

### List devices for customer

```http
GET /api/portal/customer/{customer}/devices
Authorization: Bearer <portal-token>
```

Example:

```bash
curl -H "Authorization: Bearer $PORTAL_TOKEN" \
  https://central.q-home.be/api/portal/customer/Q-Home/devices
```

## Device status semantics

| Status | Meaning |
|---|---|
| `online` | Device has online state and a recent heartbeat. |
| `stale` | Device is known as online, but last heartbeat is older than the live threshold. |
| `pending` | Device exists but is not fully authorized/provisioned. |
| `offline` | Device is offline. |
| `disabled` | Device is administratively disabled. |

## Notes

- Portal endpoints are read-only.
- Every portal lookup is audit logged.
- Rate limiting is applied by Q-Central.
- Q-Portal should never store Q-Central admin credentials.
- Keep the portal bearer token secret and rotate it periodically.
