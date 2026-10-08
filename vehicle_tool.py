"""Car tax, MOT, insurance and service due dates.

Dates are kept in config.json under "vehicles" (git-ignored), e.g.
  "vehicles": [{"name": "Car", "reg": "", "tax": "2027-03-01", "mot": "2027-05-10",
                "insurance": "2027-02-14", "service": "2027-04-01"}]
The UK DVLA/MOT lookup APIs need an approved API key, so dates are entered by you ("set my car MOT date to ...").
"""
import json
from datetime import date, datetime

import config

KEYWORDS = ["car", "mot", "road tax", "car tax", "insurance", "service due", "vehicle", "tax due"]
ITEMS = ("tax", "mot", "insurance", "service")
ALERT_DAYS = (30, 14, 7, 3, 1, 0)


def _vehicles() -> list[dict]:
    return config.load().get("vehicles", [])


def due_items() -> list[tuple[str, str, date, int]]:
    """(vehicle, item, due date, days left) for every date that is set, soonest first."""
    today, out = date.today(), []
    for v in _vehicles():
        for item in ITEMS:
            raw = v.get(item)
            if not raw:
                continue
            try:
                d = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                continue
            out.append((v.get("name", "Car"), item, d, (d - today).days))
    return sorted(out, key=lambda x: x[3])


def vehicle_status() -> str:
    """Days left until car tax, MOT, insurance and service for each vehicle."""
    rows = due_items()
    if not _vehicles():
        return "No vehicles set up. Tell me the dates, e.g. 'set my car MOT date to 2027-05-10'."
    if not rows:
        return "Vehicles are set up but no due dates are recorded yet."
    lines = []
    for name, item, d, left in rows:
        when = "OVERDUE by %d day(s)" % -left if left < 0 else "today" if left == 0 else f"in {left} day(s)"
        lines.append(f"- {name} {item.upper() if item == 'mot' else item}: due {d.strftime('%d %b %Y')} ({when})")
    return "\n".join(lines)


def set_vehicle_date(vehicle: str, item: str, due: str) -> str:
    """Record a due date (YYYY-MM-DD) for tax, mot, insurance or service. Creates the vehicle if new."""
    item = item.lower().replace("road ", "").replace("car ", "").strip()
    if item not in ITEMS:
        return f"ERROR: item must be one of {', '.join(ITEMS)}."
    try:
        datetime.strptime(due, "%Y-%m-%d")
    except ValueError:
        return "ERROR: Date must be YYYY-MM-DD, e.g. 2027-05-10."
    cfg = config.load()
    vehicles = cfg.setdefault("vehicles", [])
    v = next((x for x in vehicles if x.get("name", "").lower() == vehicle.strip().lower()), None)
    if not v:
        v = {"name": vehicle.strip()[:40] or "Car"}
        vehicles.append(v)
    v[item] = due
    with open(config.PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return f"Saved: {v['name']} {item} due {due}."


def _t(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOLS = [
    _t("vehicle_status", "Days left until the user's car tax, MOT, insurance and service are due."),
    _t("set_vehicle_date", "Record a due date for a vehicle. item is tax, mot, insurance or service; due is YYYY-MM-DD.",
       {"vehicle": {"type": "string"}, "item": {"type": "string"}, "due": {"type": "string"}}, ["vehicle", "item", "due"]),
]
FUNCTIONS = {"vehicle_status": vehicle_status, "set_vehicle_date": set_vehicle_date}
