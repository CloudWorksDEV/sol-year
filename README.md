# Solar Year Dashboard (Zagreb)

A small Flask web app that visualizes a **custom “solar year” phase model** for Zagreb, Croatia, and displays **solar metrics** for the selected date (today by default).

It’s designed as a clean, always-on **status card** with a progress bar and season-themed backgrounds.

---

## What it shows

For the current date (or a test date), the dashboard displays:

- **Current phase** according to your custom model:
  - **Winter Hard** (6 weeks) and **Summer Hard** (6 weeks), each split into 6 named weeks  
    `Pre-Low → Pre-Mid → Pre-Peak → Post-Peak → Post-Mid → Post-Low`
  - **Transits** between hard periods:
    - Transit 1: fixed 6 weeks
    - Transit 2 after hard: fixed 6 weeks
    - Transit 2 before hard: variable length, ending the day before the next hard period starts
- **Progress bar**
  - During **Hard** periods: progress within the **current 7‑day week**
  - During **Transit** periods: progress across the **full transit duration** (fixed or variable)
- **Sun altitude (°)** (dashboard-grade approximation)
- **Sun above horizon** (daylight duration, hours/minutes)
- **Sunrise / Sunset** for Zagreb, **DST-aware** (Europe/Zagreb via `zoneinfo`)
- **Days from last solstice / to next solstice**
  - Solstices are fixed calendar anchors: **21 June** and **21 December**
  - This calculation is **independent** of your custom phase model

---

## UI behavior

- The **card styling never changes**
- The **page background** changes by phase:
  - Winter Hard: dark cold gradient
  - Winter Transit (after winter solstice): light green tone
  - Winter Transit (before winter solstice): light blue tone
  - Summer Transit (before/after): yellow tone
  - Summer Hard: orange tone
- Auto-refreshes every minute.

---

## Repository layout

```
.
├─ app.py
└─ templates/
   └─ index.html
```

---

## Requirements

- Python 3.10+ (recommended 3.11+)
- Flask

`zoneinfo` is part of the Python standard library (no extra pip package needed).

---

## Quick start (venv)

From the repo root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask
python app.py
```

Then open:

- `http://<server>:8080/`

---

## Running in production (systemd)

Example install path: `/opt/solyear`

```bash
sudo mkdir -p /opt/solyear
sudo rsync -a ./ /opt/solyear/
cd /opt/solyear
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install flask
```

### systemd unit

Create: `/etc/systemd/system/solyear.service`

```ini
[Unit]
Description=Solar Week Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/solyear
ExecStart=/opt/solyear/venv/bin/python /opt/solyear/app.py
Restart=always
RestartSec=3

# Optional hardening (enable if you want)
# NoNewPrivileges=true
# PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now solyear
sudo systemctl status solyear --no-pager
```

---

## Testing any date (without changing system time)

### Option A: URL override (recommended)
Open:

```
/?date=YYYY-MM-DD
```

Examples:

- `/?date=2025-06-10`
- `/?date=2025-10-07`

The UI forwards the querystring to `/data`, so the page updates instantly.

### Option B: Server-side override
In `app.py` set:

```python
TEST_DATE = date(2025, 6, 10)
```

Restart the service, then refresh the page.

---

## Timezone / DST notes

Sunrise/sunset uses:

- `ZoneInfo("Europe/Zagreb")` (DST aware)

Make sure the host has correct tzdata and timezone set:

```bash
timedatectl set-timezone Europe/Zagreb
```

If sunrise/sunset look off by 1 hour, install/update tzdata:

- Debian/Ubuntu: `apt-get install -y tzdata`
- RHEL/Rocky: `dnf install -y tzdata`

---

## How sunrise/sunset is computed

Sunrise/sunset times are calculated using a common **NOAA-style approximation** (zenith 90.833°, includes refraction).  
This is accurate enough for dashboards and planning, but it is not an astronomical ephemeris.

---

## License

Add your preferred license here (MIT/Apache-2.0/etc.).
