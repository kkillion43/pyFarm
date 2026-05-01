# Greenhouse Pi

Autonomous greenhouse monitoring and watering system running on a Raspberry Pi Zero W.
Reads RS-485 soil sensors and a DHT11 air sensor, controls an 8-relay board, stores all
readings in SQLite, serves a REST + WebSocket API via FastAPI, and displays a live
dashboard in Node-RED — accessible remotely over Tailscale VPN.

---

## Features

- **Soil monitoring** — pH, EC, moisture, N/P/K, soil temperature via RS-485 Modbus sensor
- **Air monitoring** — temperature, humidity, VPD via DHT11/22
- **Automated watering** — hysteresis-band logic (lower threshold → start, upper target → stop)
- **8-relay control** — manual toggle via dashboard or API; automation controls one relay
- **Live dashboard** — Node-RED with 5 tabs: Live Readings, Soil Data, Relays, Sensor History, Daily Summary
- **REST + WebSocket API** — FastAPI served on port 8000; WS pushes live data every 10 s
- **Remote access** — Tailscale VPN; accessible at `http://<tailscale-ip>:8000` from anywhere
- **Auto-restart** — systemd services for both FastAPI and Node-RED restart on failure / power outage
- **Mock mode** — run without hardware for development and testing

---

## Hardware

| Component | Detail |
|---|---|
| Controller | Raspberry Pi Zero W (armv6l) |
| Soil sensor | RS-485 Modbus NPK sensor (address 1, `/dev/ttyS0`, 9600 baud) |
| Air sensor | DHT11 on BCM pin 24 (optional — system runs without it) |
| Relay board | 8-channel active-LOW relay board |
| Relay 1 `p_pump_1` | BCM 5 — Pump 1 |
| Relay 2 `p_pump_2` | BCM 13 — Pump 2 |
| Relay 3 `main_water_pump` | BCM 20 — Main water pump |
| Relay 4 `trashcan` | BCM 26 — Auto-watering relay |
| Relays 5–8 | TBD — Expansion slots |

---

## Project Structure

```
greenhouse/
├── main.py                   # Entry point — wires up all components and starts uvicorn
├── config.yaml               # Central config — hardware, thresholds, service settings
├── config_loader.py          # Loads config.yaml + overrides from .env
├── logging_config.py         # Rotating file + stdout logging setup
├── .env                      # Secrets and env-specific paths (never committed)
├── .env.example              # Template — copy to .env and fill in values
│
├── api/
│   ├── main.py               # FastAPI app, CORS, WebSocket /ws/live broadcast loop
│   └── routes/
│       ├── sensors.py        # GET /sensors/{id}/history, GET /sensors/live
│       ├── relays.py         # POST /relays/{name}/on|off|pulse, GET /relays
│       └── automation.py     # GET/PATCH /automation/config
│
├── automation/
│   └── watering.py           # Background polling thread — reads sensors, triggers pump
│
├── controllers/
│   ├── relay_controller.py   # GPIO relay control, thread-safe, active-LOW
│   └── mock_relay.py         # No-op relay for mock_mode
│
├── database/
│   ├── models.py             # SQLAlchemy ORM — SensorReading, RelayEvent, AutomationConfig
│   └── db.py                 # Engine, session, CRUD helpers, DB init/seed
│
├── sensors/
│   ├── soil_sensor.py        # RS-485 Modbus soil sensor (minimalmodbus)
│   ├── dht_sensor.py         # DHT11/22 air sensor (adafruit-circuitpython-dht)
│   └── mock_sensors.py       # Sine-wave mock sensors for testing
│
└── wifi/
    ├── portal.py             # Captive portal for first-run WiFi provisioning
    ├── provisioning.py       # nmcli-based WiFi + Tailscale enrolment helpers
    ├── nodered_flow.json     # Node-RED dashboard flow (import via API or editor)
    ├── greenhouse.service    # systemd unit for FastAPI server
    ├── nodered.service       # systemd unit for Node-RED
    └── wifi_setup.service    # systemd unit for captive portal
```

---

## Quick Start

### 1. Clone and set up the environment

```bash
git clone https://github.com/YOUR_USERNAME/greenhouse-pi.git
cd greenhouse-pi
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
nano .env                  # fill in TAILSCALE_AUTH_KEY, TAILSCALE_IP, paths
nano config.yaml           # adjust pins, thresholds, sensor addresses if needed
```

### 3. Run manually (for testing)

```bash
venv/bin/python main.py
```

### 4. Install systemd services (auto-start on boot / power outage)

```bash
sudo cp wifi/greenhouse.service /etc/systemd/system/
sudo cp wifi/nodered.service    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now greenhouse nodered
```

---

## Configuration Reference (`config.yaml`)

| Key | Default | Description |
|---|---|---|
| `mock_mode` | `false` | Run with simulated sensors — no hardware required |
| `automation.enabled` | `true` | Enable automatic watering |
| `automation.poll_interval_seconds` | `300` | How often sensors are read |
| `automation.moisture_threshold` | `12` | Start watering at or below this moisture % |
| `automation.moisture_target` | `18` | Stop watering once moisture exceeds this % |
| `automation.water_relay` | `"trashcan"` | Relay name activated during auto-watering |
| `automation.water_duration_seconds` | `15` | Pump run time per watering cycle |
| `automation.oscillate_readings` | `6` | Rolling window depth for moisture trend |
| `api.ws_push_interval_seconds` | `10` | WebSocket live-data push interval |

Secrets and paths are overridden by `.env` — see `.env.example` for the full list.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/sensors/{id}/history` | Paginated sensor reading history (`?limit=200`) |
| `GET` | `/relays` | Current on/off state of all relays |
| `GET` | `/relays/manifest` | Full 8-position relay board map |
| `POST` | `/relays/{name}/on` | Turn relay ON |
| `POST` | `/relays/{name}/off` | Turn relay OFF |
| `POST` | `/relays/{name}/pulse?duration=15` | Pulse relay for N seconds |
| `GET` | `/automation/config` | Read automation thresholds and state |
| `PATCH` | `/automation/config` | Update thresholds / enable / override |
| `WS` | `/ws/live` | Live sensor push every 10 s |

Interactive docs: `http://<pi-ip>:8000/docs`

---

## Dashboard (Node-RED)

URL: `http://<tailscale-ip>:1880/ui`

| Tab | Contents |
|---|---|
| **Live Readings** | Air temp, humidity, VPD gauges (WebSocket-fed, updates every 10 s) |
| **Soil Data** | pH, EC, N/P/K, soil temp, moisture gauges + 4 history line charts |
| **Relays** | Toggle switches for all 4 active relays (reflect live hardware state) |
| **Sensor History** | Multi-series line chart — pH, soil temp, moisture, EC |
| **Daily Summary** | Bar charts — moisture, pH, EC, soil temp aggregated by day (Avg/Min/Max) |

### Importing the flow on a fresh Node-RED install

```bash
curl -s -X POST http://127.0.0.1:1880/flows \
  -H "Content-Type: application/json" \
  -H "Node-RED-Deployment-Type: full" \
  --data-binary @wifi/nodered_flow.json
```

Update the Tailscale IP throughout the flow after importing:

```bash
sed -i 's/100\.x\.x\.x/<YOUR_TAILSCALE_IP>/g' wifi/nodered_flow.json
```

---

## Systemd Service Management

```bash
# Status
sudo systemctl status greenhouse
sudo systemctl status nodered

# Logs
sudo journalctl -u greenhouse -f
sudo journalctl -u nodered -f

# Restart
sudo systemctl restart greenhouse
sudo systemctl restart nodered
```

---

## Development — Mock Mode

Set `mock_mode: true` in `config.yaml` to run without any hardware. Sensors return
sine-wave values that cycle over time. Relays log activations but do not touch GPIO.

```bash
# Quick test
venv/bin/python main.py
curl http://localhost:8000/sensors/1/history?limit=5
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | REST API and WebSocket server |
| `SQLAlchemy` | ORM — SQLite database |
| `minimalmodbus` | RS-485 Modbus communication with soil sensor |
| `adafruit-circuitpython-dht` | DHT11/22 air sensor driver |
| `RPi.GPIO` | GPIO relay control |
| `PyYAML` | config.yaml parsing |
| `pydantic` | Request/response validation |

Full pinned list: `requirements.txt`

Generate / update:
```bash
venv/bin/pip freeze > requirements.txt
```

---

## Security Notes

- The FastAPI server binds to `0.0.0.0:8000` — on a LAN/Tailscale-only network this is acceptable. Do not expose port 8000 to the public internet without adding authentication.
- **Rotate your Tailscale auth key** after initial setup at [login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys). The key in `.env` is only needed for first enrolment.
- `config.yaml` is safe to commit — secrets are loaded exclusively from `.env`.
