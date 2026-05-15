# Q-Central architecture

Q-Central is the control plane. Q-Box devices are data-plane nodes.

## Flow

1. Serial is registered in Central with a generated one-time claim token.
2. Q-Box boots and installs the agent.
3. Agent calls `/api/provision` over the ZeroTier overlay.
4. Central validates serial + claim token.
5. Central optionally authorizes the ZeroTier member.
6. Central returns a per-device agent token.
7. Agent sends periodic heartbeats and receives jobs.

## Core modules

- Provisioning API
- Serial registry
- Auto authorization
- Customer mapping
- OTA/job management
- App manager
- Device inventory
- Audit log
