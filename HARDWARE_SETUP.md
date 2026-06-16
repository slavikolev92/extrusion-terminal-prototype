# Hardware Setup

This file records the confirmed physical hardware for the extrusion terminal pilot infrastructure.

## Server PC

Confirmed from the physical machine label:

| Item | Value |
| --- | --- |
| Model | Dell OptiPlex 7080 Micro |
| CPU | Intel Core i3-10100 |
| CPU speed | Up to 4.30 GHz |
| CPU cache | 6 MB |
| RAM | 16 GB DDR4 SO-DIMM |
| Storage | 512 GB M.2 NVMe SSD |
| Form factor | Micro PC |
| Ethernet | Present; wired LAN will be used |
| Wi-Fi | Present on label, but not planned for server connectivity |
| Code | 80128970 |
| Serial number | FJ3K8F3 |
| Grade | A |

Planned role:

- Install Proxmox VE bare metal.
- Run one Linux VM for the FastAPI/SQLite prototype app.
- Use wired LAN connectivity.
- Do not expose the app directly to the public internet.
- Use Tailscale for remote maintenance if remote access is needed.

Notes:

- This is not server-class hardware, but it is sufficient for the bounded pilot workload.
- The single NVMe SSD means there is no local disk redundancy. Off-machine backups should be treated as important before pilot use.

## Terminal Workstation

Confirmed:

| Item | Value |
| --- | --- |
| RAM | 4 GB |
| Input | Keyboard and mouse |
| Touchscreen | No |
| Display | Approximately 24 inches; exact resolution not confirmed |
| Network | Wired LAN only; no Wi-Fi requirement |
| Operating system | Linux only; no Windows OS |

Planned role:

- Run a Linux desktop or kiosk-capable Linux setup.
- Open the app terminal route in browser kiosk mode:

```text
http://APP-VM-IP:8000/terminal
```

Notes:

- Further workstation hardware details are not currently needed unless kiosk performance or display scaling becomes a problem during testing.
