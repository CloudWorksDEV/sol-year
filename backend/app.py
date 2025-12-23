from flask import Flask, render_template, jsonify, request
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import math

app = Flask(__name__)

# ================= CONFIG =================
LATITUDE = 45.81    # Zagreb
LONGITUDE = 15.98   # Zagreb (east positive)
TZ = ZoneInfo("Europe/Zagreb")

WEEK = 7
FIXED_DAYS = 6 * WEEK  # 42
HARD_DAYS = 6 * WEEK   # 42

# --- SAFE TESTING OVERRIDE (set to None for real use) ---
TEST_DATE = None
# TEST_DATE = date(2025, 5, 21)

HARD_WEEK_NAMES = [
    "Pre-Low Week",
    "Pre-Mid Week",
    "Pre-Peak Week",
    "Post-Peak Week",
    "Post-Mid Week",
    "Post-Low Week",
]

# ================= SOLAR MATH (dashboard-grade) =================
def solar_declination(doy: int) -> float:
    return 23.44 * math.sin(math.radians((360 / 365) * (doy - 81)))

def sun_altitude(lat: float, dec: float) -> float:
    return round(90 - lat + dec, 1)

def sun_up_duration_hours(lat: float, dec: float) -> float:
    lat_r = math.radians(lat)
    dec_r = math.radians(dec)
    cos_h = -math.tan(lat_r) * math.tan(dec_r)
    cos_h = max(-1, min(1, cos_h))
    h = math.acos(cos_h)
    return (2 * h * 24) / (2 * math.pi)

# ================= SUNRISE / SUNSET (NOAA-style approximation, DST via zoneinfo) =================
def _frac_year_gamma(doy: int) -> float:
    return 2.0 * math.pi / 365.0 * (doy - 1)

def equation_of_time_minutes(doy: int) -> float:
    g = _frac_year_gamma(doy)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(g)
        - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g)
        - 0.040849 * math.sin(2 * g)
    )

def declination_radians(doy: int) -> float:
    g = _frac_year_gamma(doy)
    return (
        0.006918
        - 0.399912 * math.cos(g)
        + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g)
        + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g)
        + 0.00148 * math.sin(3 * g)
    )

def tz_offset_hours_for_date(d: date) -> float:
    # Use local noon to avoid DST transition edge cases around 02:00-03:00
    dt = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=TZ)
    off = dt.utcoffset()
    return off.total_seconds() / 3600.0 if off else 0.0

def sunrise_sunset_local(d: date, lat: float, lon: float):
    """
    Returns (sunrise_str, sunset_str) in local Zagreb clock time (DST-aware).
    Approximation uses zenith 90.833° (includes refraction).
    """
    doy = d.timetuple().tm_yday
    lat_r = math.radians(lat)
    dec = declination_radians(doy)
    eqt = equation_of_time_minutes(doy)

    zenith = math.radians(90.833)
    cos_ha = (math.cos(zenith) - math.sin(lat_r) * math.sin(dec)) / (math.cos(lat_r) * math.cos(dec))
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha_deg = math.degrees(math.acos(cos_ha))

    tz_hours = tz_offset_hours_for_date(d)

    # Solar noon in minutes (local clock). Longitude east-positive.
    solar_noon_min = 720 - 4 * lon - eqt + 60 * tz_hours
    sunrise_min = solar_noon_min - 4 * ha_deg
    sunset_min = solar_noon_min + 4 * ha_deg

    def fmt(minutes):
        minutes = minutes % (24 * 60)
        hh = int(minutes // 60)
        mm = int(round(minutes % 60))
        if mm == 60:
            hh = (hh + 1) % 24
            mm = 0
        return f"{hh:02d}:{mm:02d}"

    return fmt(sunrise_min), fmt(sunset_min)

# ================= SOLSTICES (calendar truth) =================
def winter_solstice(y: int) -> date:
    return date(y, 12, 21)

def summer_solstice(y: int) -> date:
    return date(y, 6, 21)

def last_next_solstice(today: date):
    sols = [
        date(today.year - 1, 6, 21), date(today.year - 1, 12, 21),
        date(today.year, 6, 21),     date(today.year, 12, 21),
        date(today.year + 1, 6, 21), date(today.year + 1, 12, 21),
    ]
    last_sol = max(s for s in sols if s <= today)
    next_sol = min(s for s in sols if s > today)
    return last_sol, next_sol

def solstice_name(d: date) -> str:
    return "Summer" if d.month == 6 else "Winter"

# ================= PHASE MODEL (your state machine, no gaps) =================
def build_cycle(winter_year: int):
    ws = winter_solstice(winter_year)
    ss = summer_solstice(winter_year + 1)
    ws_next = winter_solstice(winter_year + 1)

    winter_hard_start = ws - timedelta(days=21)
    winter_hard_end = winter_hard_start + timedelta(days=HARD_DAYS - 1)

    summer_hard_start = ss - timedelta(days=21)
    summer_hard_end = summer_hard_start + timedelta(days=HARD_DAYS - 1)

    next_winter_hard_start = ws_next - timedelta(days=21)

    phases = []

    def add(name, season, kind, start, end, pos=None, variable=False):
        if start > end:
            return
        phases.append({
            "name": name,
            "season": season,
            "kind": kind,
            "start": start,
            "end": end,
            "pos": pos,          # Winter transits: "after" or "before"
            "variable": variable
        })

    add("Winter Hard", "Winter", "hard", winter_hard_start, winter_hard_end)

    p = winter_hard_end + timedelta(days=1)
    add("Winter Transit 1", "Winter", "transit", p, p + timedelta(days=FIXED_DAYS - 1), pos="after")
    p += timedelta(days=FIXED_DAYS)
    add("Winter Transit 2", "Winter", "transit", p, p + timedelta(days=FIXED_DAYS - 1), pos="after")
    p += timedelta(days=FIXED_DAYS)

    add("Summer Transit 1", "Summer", "transit", p, p + timedelta(days=FIXED_DAYS - 1))
    p += timedelta(days=FIXED_DAYS)
    add("Summer Transit 2", "Summer", "transit", p, summer_hard_start - timedelta(days=1), variable=True)

    add("Summer Hard", "Summer", "hard", summer_hard_start, summer_hard_end)

    p = summer_hard_end + timedelta(days=1)
    add("Summer Transit 1", "Summer", "transit", p, p + timedelta(days=FIXED_DAYS - 1))
    p += timedelta(days=FIXED_DAYS)
    add("Summer Transit 2", "Summer", "transit", p, p + timedelta(days=FIXED_DAYS - 1))
    p += timedelta(days=FIXED_DAYS)

    add("Winter Transit 1", "Winter", "transit", p, p + timedelta(days=FIXED_DAYS - 1), pos="before")
    p += timedelta(days=FIXED_DAYS)
    add("Winter Transit 2", "Winter", "transit", p, next_winter_hard_start - timedelta(days=1), pos="before", variable=True)

    return phases

def find_phase(today: date):
    for wy in (today.year - 1, today.year, today.year + 1):
        for ph in build_cycle(wy):
            if ph["start"] <= today <= ph["end"]:
                return ph
    raise RuntimeError(f"No phase found for {today} (should never happen).")

# ================= UI COLORS =================
def bar_class(ph):
    if ph["kind"] == "hard" and ph["season"] == "Winter":
        return "winter"
    if ph["kind"] == "hard" and ph["season"] == "Summer":
        return "summer"
    if ph["season"] == "Winter":
        return "winter-transit"
    return "summer-transit"

def bg_class(ph):
    if ph["kind"] == "hard" and ph["season"] == "Winter":
        return "bg-winter-hard"
    if ph["kind"] == "hard" and ph["season"] == "Summer":
        return "bg-summer-hard"
    if ph["season"] == "Summer":
        return "bg-summer-transit"
    return "bg-winter-transit-after" if ph.get("pos") == "after" else "bg-winter-transit-before"

# ================= ROUTES =================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def data():
    if TEST_DATE is not None:
        today = TEST_DATE
    else:
        override = request.args.get("date")
        if override:
            try:
                today = date.fromisoformat(override)
            except ValueError:
                today = date.today()
        else:
            today = date.today()

    ph = find_phase(today)

    # Solar
    doy = today.timetuple().tm_yday
    dec_deg = solar_declination(doy)
    alt = sun_altitude(LATITUDE, dec_deg)
    sun_up_h = sun_up_duration_hours(LATITUDE, dec_deg)
    hh = int(sun_up_h)
    mm = int(round((sun_up_h - hh) * 60))
    if mm == 60:
        hh = (hh + 1) % 24
        mm = 0

    sunrise, sunset = sunrise_sunset_local(today, LATITUDE, LONGITUDE)

    # Progress
    total_days = (ph["end"] - ph["start"]).days + 1
    day_index = (today - ph["start"]).days

    if ph["kind"] == "hard":
        week_idx = day_index // WEEK
        week_name = HARD_WEEK_NAMES[week_idx]
        title = f"{ph['season']} · {week_name}"
        progress = ((day_index % WEEK) + 1) / WEEK * 100.0
    else:
        title = ph["name"]
        progress = ((day_index + 1) / total_days) * 100.0

    # Solstice counters (pure calendar)
    last_sol, next_sol = last_next_solstice(today)
    from_days = (today - last_sol).days
    to_days = (next_sol - today).days
    sol_line = f"{from_days} days from {solstice_name(last_sol)} solstice · {to_days} days to {solstice_name(next_sol)} solstice"

    return jsonify({
        "date": today.strftime("%d %B %Y"),
        "title": title,
        "sun_altitude": alt,
        "sun_up": f"{hh} h {mm:02d} min",
        "sunrise": sunrise,
        "sunset": sunset,
        "progress": round(progress, 1),
        "bar": bar_class(ph),
        "bg": bg_class(ph),
        "solstice": sol_line,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
