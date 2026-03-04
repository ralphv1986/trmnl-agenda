#!/usr/bin/env python3
"""
TRMNL Agenda Generator
Haalt agenda (iCal) + weer (Open-Meteo) op en genereert index.html.
Draai via cron 1-3x per dag, of handmatig.

Gebruik:
    python3 generate.py
"""

import os
import sys
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar
import recurring_ical_events

# === CONFIG ===
ICAL_URL = "https://calendar.google.com/calendar/ical/blc6jnoku2k2cfd6r1hi87mfu8%40group.calendar.google.com/private-b0b82c02a6f316b2940a3d0c02d55719/basic.ics"
WEATHER_LAT = 52.6958  # Meppel
WEATHER_LON = 6.1944
TIMEZONE = ZoneInfo("Europe/Amsterdam")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")
PAGE2_FILE = os.path.join(OUTPUT_DIR, "page2.html")

# === DUTCH HELPERS ===
DAGEN = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]
DAGEN_LANG = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
MAANDEN = ["", "Januari", "Februari", "Maart", "April", "Mei", "Juni",
           "Juli", "Augustus", "September", "Oktober", "November", "December"]
MAANDEN_KORT = ["", "jan", "feb", "mrt", "apr", "mei", "jun",
                "jul", "aug", "sep", "okt", "nov", "dec"]

WMO_CODES = {
    0: "onbewolkt", 1: "licht bewolkt", 2: "half bewolkt", 3: "bewolkt",
    45: "mist", 48: "ijsmist",
    51: "lichte motregen", 53: "motregen", 55: "zware motregen",
    56: "lichte ijzel", 57: "ijzel",
    61: "lichte regen", 63: "regen", 65: "zware regen",
    66: "lichte ijsregen", 67: "ijsregen",
    71: "lichte sneeuw", 73: "sneeuw", 75: "zware sneeuw", 77: "sneeuwkorrels",
    80: "lichte buien", 81: "buien", 82: "zware buien",
    85: "lichte sneeuwbuien", 86: "sneeuwbuien",
    95: "onweer", 96: "onweer + hagel", 99: "zwaar onweer + hagel",
}


def dag_kort(d):
    return DAGEN[d.weekday()]


def dag_lang(d):
    return DAGEN_LANG[d.weekday()]


def maand(d):
    return MAANDEN[d.month]


def begroeting():
    """Geef een begroeting op basis van het tijdstip."""
    uur = datetime.now(TIMEZONE).hour
    if uur < 12:
        return "goedemorgen"
    elif uur < 18:
        return "goedemiddag"
    else:
        return "goedenavond"


# === WEER ===
def fetch_weather():
    print("  Weer ophalen (Open-Meteo)...")
    resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "timezone": "Europe/Amsterdam", "forecast_days": 5,
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()["daily"]

    today = date.today()
    days = []
    for i in range(len(data["time"])):
        d = date.fromisoformat(data["time"][i])
        temp = round(data["temperature_2m_max"][i])
        temp_min = round(data["temperature_2m_min"][i])
        rain = data["precipitation_sum"][i]
        code = data["weathercode"][i]

        if d == today:
            label = f"{dag_kort(d)} {d.day:02d} {MAANDEN_KORT[d.month]}"
        elif d == today + timedelta(days=1):
            label = f"morgen {d.strftime('%d/%m')}"
        else:
            label = f"{dag_kort(d)} {d.strftime('%d/%m')}"

        rain_str = f"{rain:.2f}".replace(".", ",") if rain >= 1 else None
        days.append({
            "temp": temp, "temp_min": temp_min, "label": label,
            "desc": WMO_CODES.get(code, "onbekend"),
            "rain": rain_str, "is_today": d == today,
        })
    print(f"  → {len(days)} dagen weer opgehaald")
    return days


# === AGENDA ===
def fetch_ical():
    """Download en parse de iCal feed."""
    print("  Agenda ophalen (iCal)...")
    resp = requests.get(ICAL_URL, timeout=15)
    resp.raise_for_status()
    return Calendar.from_ical(resp.text)


def fetch_events(cal):
    """Haal events op voor de komende 28 dagen en retourneer als chronologische lijst."""
    today = date.today()
    end_date = today + timedelta(days=27)

    # Haal events op voor 28 dagen (inclusief recurring)
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=TIMEZONE)
    end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=TIMEZONE)
    events = recurring_ical_events.of(cal).between(start, end)

    days_dict = {}

    for event in events:
        summary = str(event.get("SUMMARY", "Geen titel")).strip()
        dtstart = event.get("DTSTART").dt
        dtend = event.get("DTEND").dt if event.get("DTEND") else None

        # Bepaal of het een hele-dag event is
        if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
            is_allday = True
            # Meerdaagse events
            if dtend and (dtend - dtstart).days > 1:
                actual_end = dtend - timedelta(days=1)  # DTEND is exclusief bij hele-dag events
                # Toon op de eerste zichtbare dag (vandaag of later)
                event_date = max(dtstart, today)
                if event_date > actual_end:
                    continue  # Event is al voorbij
                # Als het de laatste dag is, toon "Hele dag", anders "t/m ..."
                if event_date >= actual_end:
                    time_str = "Hele dag"
                else:
                    time_str = f"t/m {dag_kort(actual_end).lower()} {actual_end.strftime('%d/%m')}"
            else:
                event_date = dtstart
                time_str = "Hele dag"
        else:
            if dtstart.tzinfo is None:
                dtstart = dtstart.replace(tzinfo=TIMEZONE)
            if dtend and dtend.tzinfo is None:
                dtend = dtend.replace(tzinfo=TIMEZONE)
            dtstart = dtstart.astimezone(TIMEZONE)
            event_date = dtstart.date()
            is_allday = False
            start_str = dtstart.strftime("%H:%M")
            if dtend:
                dtend = dtend.astimezone(TIMEZONE)
                end_str = dtend.strftime("%H:%M")
                time_str = f"{start_str} - {end_str}"
            else:
                time_str = start_str

        if not (today <= event_date <= end_date):
            continue

        evt = {
            "summary": summary,
            "time": time_str,
            "is_allday": is_allday,
            "sort_key": "00:00" if is_allday else time_str[:5],
        }

        if event_date not in days_dict:
            days_dict[event_date] = []
        days_dict[event_date].append(evt)

    # Sorteer events binnen elke dag (hele dag eerst, dan op tijd)
    def sort_events(events_list):
        return sorted(events_list, key=lambda e: ("1" + e["sort_key"] if not e["is_allday"] else "0"))

    all_days = []
    for d in sorted(days_dict.keys()):
        all_days.append({
            "date": d,
            "label": f"{dag_kort(d)} {d.day} {maand(d)}",
            "events": sort_events(days_dict[d]),
            "week_num": d.isocalendar()[1],
        })

    total = sum(len(d["events"]) for d in all_days)
    print(f"  → {total} events in {len(all_days)} dagen (komende 28 dagen)")
    return all_days


# === KOLOM LAYOUT ===
# Geschatte pixel-hoogtes voor de kolom-vulling
COL_HEIGHT = 340    # 360px kolom - 20px padding
DAY_HEADER_H = 24   # dag-label + border + marge
EVENT_H = 30        # event-rij hoogte (incl. mogelijke 2-regels titel)
DAY_MARGIN = 10     # marge onder dag-sectie
WEEK_HEADER_H = 34  # week-scheiding label


def estimate_day_height(day):
    """Schat de hoogte van een dag-sectie in pixels."""
    return DAY_HEADER_H + len(day["events"]) * EVENT_H + DAY_MARGIN


def split_into_columns(all_days):
    """Verdeel dagen over twee kolommen zodat het scherm gevuld wordt."""
    left = []
    right = []
    left_h = 0
    right_h = 0
    filling_left = True
    last_week = None

    for day in all_days:
        day_h = estimate_day_height(day)

        # Check of er een week-scheiding nodig is
        week_sep_h = 0
        if last_week is not None and day["week_num"] != last_week:
            week_sep_h = WEEK_HEADER_H

        if filling_left:
            if left_h + week_sep_h + day_h <= COL_HEIGHT:
                left.append(day)
                left_h += week_sep_h + day_h
                last_week = day["week_num"]
            else:
                # Wissel naar rechterkolom
                filling_left = False
                right_h = 0
                # Week-header als de rechterkolom in een andere week begint
                if last_week is not None and day["week_num"] != last_week:
                    right_h += WEEK_HEADER_H
                if right_h + day_h <= COL_HEIGHT:
                    right.append(day)
                    right_h += day_h
                    last_week = day["week_num"]
        else:
            total_h = day_h
            if day["week_num"] != last_week:
                total_h += WEEK_HEADER_H
            if right_h + total_h <= COL_HEIGHT:
                right.append(day)
                right_h += total_h
                last_week = day["week_num"]
            else:
                break  # Beide kolommen vol

    return left, right


# === HTML GENEREREN ===
def generate_html(weather, all_days):
    today = date.today()

    # Verdeel over twee kolommen
    left_col, right_col = split_into_columns(all_days)

    # Bepaal of rechterkolom een week-header nodig heeft
    right_week_num = None
    if left_col and right_col:
        left_last_week = left_col[-1]["week_num"]
        right_first_week = right_col[0]["week_num"]
        if right_first_week != left_last_week:
            right_week_num = right_first_week

    # Weer blokken
    weather_html = ""
    for day in weather:
        if day["is_today"]:
            weather_html += f"""    <div class="weather-day today">
      <div class="weather-temp-wrap">
        <div class="weather-max">max</div>
        <div class="weather-temp">{day['temp']}<sup>&deg;C</sup></div>
      </div>
      <div class="weather-today-info">
        <div class="weather-today-title">{begroeting()}</div>
        <div class="weather-label">{day['label']}</div>
        <div class="weather-detail">{day['desc']}{f" &middot; &loz; {day['rain']} mm" if day['rain'] else ''}</div>
      </div>
    </div>\n"""
        else:
            weather_html += f"""    <div class="weather-day">
      <div class="weather-temp">{day['temp']}<sup>&deg;C</sup></div>
      <div class="weather-label">{day['label']}</div>
      <div class="weather-detail">{day['desc']}{f" &middot; &loz; {day['rain']} mm" if day['rain'] else ''}</div>
    </div>\n"""

    # Agenda kolom helper
    def render_col(days, empty_msg="Geen afspraken"):
        if not days:
            return f'      <div class="day-section">\n        <div class="no-events">{empty_msg}</div>\n      </div>\n'
        html = ""
        for day in days:
            html += f'      <div class="day-section">\n'
            html += f'        <div class="day-label">{day["label"]}</div>\n'
            for evt in day["events"]:
                allday_cls = " event-allday" if evt["is_allday"] else ""
                summary = evt["summary"].replace("&", "&amp;").replace("<", "&lt;")
                html += f'        <div class="event{allday_cls}">\n'
                html += f'          <div class="event-time">{evt["time"]}</div>\n'
                html += f'          <div class="event-title">{summary}</div>\n'
                html += f'        </div>\n'
            html += f'      </div>\n'
        return html

    # Week-header voor rechterkolom
    right_header = ""
    if right_week_num:
        right_header = f'      <div class="day-section">\n        <div class="day-label">Week {right_week_num}</div>\n      </div>\n'

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=800, height=480, initial-scale=1">
  <title>TRMNL Agenda</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{
      width: 800px; height: 480px; overflow: hidden;
      background: #fff; color: #000;
      font-family: 'Inter', -apple-system, sans-serif;
      -webkit-font-smoothing: none;
    }}
    .weather-bar {{ width: 800px; height: 104px; display: flex; border-bottom: 2px solid #000; margin-bottom: 8px; }}
    .weather-day {{
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 6px 4px; border-right: 1px solid #ddd;
    }}
    .weather-day:last-child {{ border-right: none; }}
    .weather-day.today {{ flex: none; width: 240px; flex-direction: row; align-items: center; justify-content: center; background: #000; color: #fff; border-right-color: #000; padding: 0; gap: 0; }}
    .weather-temp-wrap {{ display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 10px; }}
    .weather-max {{ font-size: 10px; font-weight: 600; letter-spacing: 1px; opacity: 0.7; margin-bottom: -4px; }}
    .weather-day.today .weather-temp {{ font-size: 60px; font-weight: 900; display: flex; align-items: center; justify-content: center; padding: 0; margin: 0; }}
    .weather-day.today .weather-temp sup {{ font-size: 22px; }}
    .weather-today-info {{ display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 1px; }}
    .weather-today-title {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; text-align: left; }}
    .weather-day.today .weather-label {{ font-size: 15px; font-weight: 700; text-align: left; }}
    .weather-day.today .weather-detail {{ font-size: 14px; text-align: left; font-style: italic; }}
    .weather-temp {{ font-size: 28px; font-weight: 600; line-height: 1; margin-bottom: 3px; }}
    .weather-temp sup {{ font-size: 16px; font-weight: 700; vertical-align: super; line-height: 1; }}
    .weather-night {{ font-size: 19px; font-weight: 500; color: #777; }}
    .weather-label {{ font-size: 14px; font-weight: 600; text-align: center; line-height: 1.2; }}
    .weather-detail {{ font-size: 13px; font-weight: 500; text-align: center; line-height: 1.2; font-style: italic; }}
    .agenda-columns {{ width: 800px; height: 368px; display: flex; }}
    .agenda-col {{ flex: 1; padding: 10px 16px; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }}
    .agenda-col:first-child {{ border-right: 2px solid #000; }}
    .day-section {{ margin-bottom: 10px; }}
    .day-label {{
      font-size: 12px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 1.5px; margin-bottom: 3px; padding-bottom: 3px;
      border-bottom: 1px solid #000;
    }}
    .event {{ display: flex; align-items: baseline; padding: 4px 0; gap: 10px; }}
    .event + .event {{ border-top: 1px dashed #ccc; }}
    .event-time {{ font-size: 14px; font-weight: 700; white-space: nowrap; min-width: 82px; }}
    .event-title {{
      font-size: 14px; font-weight: 500; line-height: 1.3;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }}
    .event-allday {{ background: #000; color: #fff; padding: 3px 8px; margin: 1px -8px; }}
    .event-allday .event-title, .event-allday .event-time {{ color: #fff; }}
    .event-allday .event-time {{ font-size: 12px; }}
    .no-events {{ font-size: 12px; font-style: italic; padding: 3px 0; color: #666; }}
  </style>
</head>
<body>
  <div class="weather-bar">
{weather_html}  </div>
  <div class="agenda-columns">
    <div class="agenda-col">
{render_col(left_col)}    </div>
    <div class="agenda-col">
{right_header}{render_col(right_col)}    </div>
  </div>
</body>
</html>"""

    return html


# === PAGE 2: KALENDER GRID (3 WEKEN) ===

def build_calendar_grid(cal, start_date, num_days=21):
    """Bouw events-per-dag dict voor kalendergrid. Multi-day events op elke dag."""
    end_date = start_date + timedelta(days=num_days - 1)
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=TIMEZONE)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=TIMEZONE)

    events = recurring_ical_events.of(cal).between(start_dt, end_dt)

    # Initialiseer alle dagen
    days_dict = {}
    for i in range(num_days):
        days_dict[start_date + timedelta(days=i)] = []

    for event in events:
        summary = str(event.get("SUMMARY", "Geen titel")).strip()
        dtstart = event.get("DTSTART").dt
        dtend = event.get("DTEND").dt if event.get("DTEND") else None

        if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
            # Hele-dag event — toon op elke dag in het bereik
            evt_start = dtstart
            evt_end = (dtend - timedelta(days=1)) if dtend else dtstart
            d = max(evt_start, start_date)
            while d <= min(evt_end, end_date):
                days_dict[d].append({
                    "summary": summary,
                    "is_allday": True,
                    "sort_key": "0",
                })
                d += timedelta(days=1)
        else:
            # Getimed event
            if dtstart.tzinfo is None:
                dtstart = dtstart.replace(tzinfo=TIMEZONE)
            dtstart = dtstart.astimezone(TIMEZONE)
            evt_date = dtstart.date()
            if not (start_date <= evt_date <= end_date):
                continue
            days_dict[evt_date].append({
                "summary": summary,
                "time": dtstart.strftime("%H:%M"),
                "is_allday": False,
                "sort_key": "1" + dtstart.strftime("%H:%M"),
            })

    # Sorteer events per dag (hele dag eerst, dan op tijd)
    for d in days_dict:
        days_dict[d].sort(key=lambda e: e["sort_key"])

    total = sum(len(v) for v in days_dict.values())
    print(f"  → {total} kalender-events over {num_days} dagen")
    return days_dict


def generate_calendar_page(weather, cal_data, start_date):
    """Genereer page2.html met weerbalk + 3-weken kalendergrid."""
    today = date.today()
    num_days = len(cal_data)
    num_weeks = num_days // 7

    # Layout constanten (480 - 104 weerbalk - 16 marge = 360 voor grid)
    CAL_H = 368
    HDR_H = 22
    MAX_EVENTS = 5

    # Bereken dynamische weekhoogtes op basis van max events per dag per week
    ROWS_H = CAL_H - HDR_H  # beschikbare hoogte voor weekrijen
    week_weights = []
    for w in range(num_weeks):
        week_start = start_date + timedelta(days=w * 7)
        max_evts = 0
        for d_off in range(7):
            d = week_start + timedelta(days=d_off)
            n = len(cal_data.get(d, []))
            if n > max_evts:
                max_evts = n
        # Minimaal gewicht 1 (voor dag-nummer), anders max events + 1 (voor dag-nummer)
        week_weights.append(max(1, max_evts + 1))

    total_weight = sum(week_weights)
    week_heights = [round(ROWS_H * w / total_weight) for w in week_weights]
    # Corrigeer afrondingsverschil op laatste rij
    week_heights[-1] = ROWS_H - sum(week_heights[:-1])
    row_template = " ".join(f"{h}px" for h in week_heights)

    # Weer blokken (zelfde als pagina 1)
    weather_html = ""
    for day in weather:
        if day["is_today"]:
            weather_html += f"""    <div class="weather-day today">
      <div class="weather-temp-wrap">
        <div class="weather-max">max</div>
        <div class="weather-temp">{day['temp']}<sup>&deg;C</sup></div>
      </div>
      <div class="weather-today-info">
        <div class="weather-today-title">{begroeting()}</div>
        <div class="weather-label">{day['label']}</div>
        <div class="weather-detail">{day['desc']}{f" &middot; &loz; {day['rain']} mm" if day['rain'] else ''}</div>
      </div>
    </div>\n"""
        else:
            weather_html += f"""    <div class="weather-day">
      <div class="weather-temp">{day['temp']}<sup>&deg;C</sup></div>
      <div class="weather-label">{day['label']}</div>
      <div class="weather-detail">{day['desc']}{f" &middot; &loz; {day['rain']} mm" if day['rain'] else ''}</div>
    </div>\n"""

    # Dag-naam headers
    headers_html = ""
    for name in ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]:
        headers_html += f'    <div class="ch">{name}</div>\n'

    # Cellen genereren
    cells_html = ""
    for i in range(num_days):
        d = start_date + timedelta(days=i)
        evts = cal_data.get(d, [])
        is_today = d == today
        is_past = d < today

        cls = "cc"
        if is_today:
            cls += " ct"
        elif is_past:
            cls += " cp"

        cells_html += f'    <div class="{cls}">\n'

        # Dag nummer (bij 1e van maand of 1e cel: toon maandnaam)
        if d.day == 1 or i == 0:
            day_str = f"{d.day} {MAANDEN_KORT[d.month]}"
        else:
            day_str = str(d.day)

        if is_today:
            cells_html += f'      <div class="cn"><span class="ctn">{day_str}</span></div>\n'
        else:
            cells_html += f'      <div class="cn">{day_str}</div>\n'

        # Events
        shown = 0
        for evt in evts:
            if shown >= MAX_EVENTS:
                rem = len(evts) - shown
                cells_html += f'      <div class="cm">+{rem}</div>\n'
                break

            name = evt["summary"].replace("&", "&amp;").replace("<", "&lt;")

            if evt["is_allday"]:
                cells_html += f'      <div class="ca">{name}</div>\n'
            else:
                t = evt.get("time", "")
                cells_html += f'      <div class="ce"><b>{t}</b> {name}</div>\n'
            shown += 1

        cells_html += '    </div>\n'

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=800, height=480, initial-scale=1">
  <title>TRMNL Kalender</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{
      width: 800px; height: 480px; overflow: hidden;
      background: #fff; color: #000;
      font-family: 'Inter', -apple-system, sans-serif;
      -webkit-font-smoothing: none;
    }}
    .weather-bar {{ width: 800px; height: 104px; display: flex; border-bottom: 2px solid #000; margin-bottom: 8px; }}
    .weather-day {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 6px 4px; border-right: 1px solid #ddd; }}
    .weather-day:last-child {{ border-right: none; }}
    .weather-day.today {{ flex: none; width: 240px; flex-direction: row; align-items: center; justify-content: center; background: #000; color: #fff; border-right-color: #000; padding: 0; gap: 0; }}
    .weather-temp-wrap {{ display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 10px; }}
    .weather-max {{ font-size: 10px; font-weight: 600; letter-spacing: 1px; opacity: 0.7; margin-bottom: -4px; }}
    .weather-day.today .weather-temp {{ font-size: 60px; font-weight: 900; display: flex; align-items: center; justify-content: center; padding: 0; margin: 0; }}
    .weather-day.today .weather-temp sup {{ font-size: 22px; }}
    .weather-today-info {{ display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 1px; }}
    .weather-today-title {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; text-align: left; }}
    .weather-day.today .weather-label {{ font-size: 15px; font-weight: 700; text-align: left; }}
    .weather-day.today .weather-detail {{ font-size: 14px; text-align: left; font-style: italic; }}
    .weather-temp {{ font-size: 28px; font-weight: 600; line-height: 1; margin-bottom: 3px; }}
    .weather-temp sup {{ font-size: 16px; font-weight: 700; vertical-align: super; line-height: 1; }}
    .weather-night {{ font-size: 19px; font-weight: 500; color: #777; }}
    .weather-label {{ font-size: 14px; font-weight: 600; text-align: center; line-height: 1.2; }}
    .weather-detail {{ font-size: 13px; font-weight: 500; text-align: center; line-height: 1.2; font-style: italic; }}
    .cal {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      grid-template-rows: {HDR_H}px {row_template};
      width: 800px; height: {CAL_H}px;
    }}
    .ch {{
      font-size: 11px; font-weight: 700;
      text-align: center; line-height: {HDR_H}px;
      text-transform: uppercase; letter-spacing: 1px;
      background: #fff; color: #000;
      border-bottom: 2px solid #000;
      border-right: 1px solid #ddd;
    }}
    .ch:nth-child(7) {{ border-right: none; }}
    .cc {{
      border-right: 1px solid #ddd;
      border-bottom: 1px solid #ddd;
      padding: 3px 4px;
      overflow: hidden;
    }}
    .ct {{
      border: 2px solid #000;
    }}
    .cp {{
      color: #999;
    }}
    .cn {{
      font-size: 14px; font-weight: 700;
      line-height: 1.2; margin-bottom: 2px;
    }}
    .ctn {{
      background: #000; color: #fff;
      padding: 1px 5px; font-weight: 900;
    }}
    .ce {{
      font-size: 14px; line-height: 1.3;
      padding: 1px 0;
      hyphens: none; -webkit-hyphens: none;
    }}
    .ca {{
      background: #000; color: #fff;
      font-size: 14px; font-weight: 600;
      padding: 1px 3px; margin: 1px -4px;
      hyphens: none; -webkit-hyphens: none;
    }}
    .cm {{
      font-size: 8px; font-style: italic; color: #888;
    }}
  </style>
</head>
<body>
  <div class="weather-bar">
{weather_html}  </div>
  <div class="cal">
{headers_html}{cells_html}  </div>
</body>
</html>"""

    return html


# === MAIN ===
def main():
    print(f"\n=== TRMNL Agenda Generator ===")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        weather = fetch_weather()
    except Exception as e:
        print(f"  [FOUT] Weer ophalen mislukt: {e}")
        weather = []

    try:
        cal = fetch_ical()
    except Exception as e:
        print(f"  [FOUT] Agenda ophalen mislukt: {e}")
        cal = None

    # === Pagina 1: Afspraken lijst ===
    all_days = []
    if cal:
        try:
            all_days = fetch_events(cal)
        except Exception as e:
            print(f"  [FOUT] Events verwerken mislukt: {e}")

    html = generate_html(weather, all_days)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ {OUTPUT_FILE} gegenereerd")

    # === Pagina 2: Kalender grid (3 weken) ===
    if cal:
        try:
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            cal_data = build_calendar_grid(cal, monday, 21)
            page2 = generate_calendar_page(weather, cal_data, monday)
            with open(PAGE2_FILE, "w", encoding="utf-8") as f:
                f.write(page2)
            print(f"  ✓ {PAGE2_FILE} gegenereerd")
        except Exception as e:
            print(f"  [FOUT] Kalender pagina mislukt: {e}")

    print(f"\n  Open in browser of laat TRMNL een screenshot maken\n")


if __name__ == "__main__":
    main()
