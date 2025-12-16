## Object Counting & Impression Collector

This repository contains scripts to count objects crossing configured lines in a video/stream, store impressions in a local SQLite database, and transmit counts via MQTT. It also supports uploading screenshots to an HTTP endpoint when requested.

- Language: Python 3.8+

---

## Key features

- Per-object detection and tracking with unique object IDs.
- Directional line counting per line (R->B and B->R).
- Persistence of impressions in SQLite and a resend mechanism for pending data.
- MQTT integration for device registration, line configuration, screenshot requests, and count publishing.
- HTTP integration for uploading screenshots.
- Daily log files and a saved snapshot of the last counters.

---

## Repository overview

- `count.py` — main entrypoint that runs the detection pipeline and callback.
- `mqtt_client.py` — MQTT client initialization and handlers (connect, subscribe, on_message, on_publish).
- `http_client.py` — helper for uploading screenshots to an HTTP endpoint.
- `database.py` — SQLite helper for tables: `device_info`, `line`, `impression`, `class_detection`.
- `save_data/last_data_count.json` — snapshot of the latest counters saved automatically.
- `log/` — daily log folder.
- `dynamic/screenshoot/count/` — temporary screenshot storage prior to upload.

---

## Requirements

- Python 3.8 or newer
- Recommended packages: `numpy`, `opencv-python`, `paho-mqtt`, `python-dotenv`, `requests`, `certifi`
- Additional external dependencies may be required depending on the detection pipeline implementation.

---

## Configuration (.env)

Place the `.env` file under `basic_pipelines/.env` (this path is used by the scripts).
Important environment variables:

```text
MQTT_BROKER=your.mqtt.broker.host
MQTT_PORT=1883
MQTT_USER=username
MQTT_PASS=password
DEVICE_ID=unique-device-id
AUTHORIZATION_TOKEN=Bearer <token>      # used for screenshot upload authorization
```

Note: ensure your MQTT broker supports the type of connection you intend to use (TCP or WebSocket).

---

## MQTT topics (summary)

- Publish events / counts: `carcamera/publish`
- Subscribe for configuration & registration: `carcamera/subscribe/{DEVICE_ID}`
- Subscribe for screenshot request: `carcamera/{DEVICE_ID}/screenshoot`
- Configuration topic: `carcamera/config/{DEVICE_ID}` (for class changes)

JSON payloads follow action patterns such as `send_data_count`, `new_carcamera`, `device_status`, etc.

---

## Running the application

1. Create and activate a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\\Scripts\\activate on Windows
pip install -r requirements.txt   # create this file if not present
```

2. Edit `basic_pipelines/.env` and set required variables.

3. Start the application:

```bash
python count.py
```

The app will create/connect to the SQLite database (default `count.db`) and start the detection loop and MQTT client.

---

## Database & migrations

- On startup `database.py` will create required tables if they are missing:
  `device_info`, `line`, `impression`, `class_detection`.
- Use methods on `InitDatabase` to inspect or seed initial values (e.g., `insert_line`, `insert_class_detection`).

---

## File locations

- Temporary screenshot file: `dynamic/screenshoot/count/screenshot_count.jpg`
- Last-saved counter snapshot: `save_data/last_data_count.json`
- Daily log files: `log/YYYY-MM-DD.txt`

---

## Troubleshooting

- MQTT connection issues: verify `MQTT_BROKER`, `MQTT_PORT`, credentials, and whether TLS/WebSocket is required.
- Unacknowledged publishes: impressions are stored locally and a resend mechanism attempts to deliver pending records.
- Screenshot upload failures: verify `AUTHORIZATION_TOKEN` and the `url` provided in MQTT payloads.

---




