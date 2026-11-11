"""Energy audit engine: pure Python, no dependencies.

Takes a list of machines plus energy-supply settings and returns usage,
cost (grid + diesel generator), CO2, and an efficiency/solar what-if.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass

MAX_MACHINES = 5000


class ValidationError(ValueError):
    """Raised when user input is missing or out of range."""


def _num(value, label, lo=None, hi=None, lo_exclusive=False):
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a number.")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a number.") from None
    if not math.isfinite(v):
        raise ValidationError(f"{label} must be a finite number.")
    if lo is not None and (v <= lo if lo_exclusive else v < lo):
        word = "greater than" if lo_exclusive else "at least"
        raise ValidationError(f"{label} must be {word} {lo}.")
    if hi is not None and v > hi:
        raise ValidationError(f"{label} must not be more than {hi}.")
    return v


def _get(d, key, default):
    v = d.get(key)
    return default if v is None or v == "" else v


@dataclass
class Machine:
    name: str
    power_watts: float
    hours_per_day: float
    quantity: int = 1
    load_factor: float = 1.0      # 0-1: average fraction of rated power drawn
    days_per_month: float = 30.0

    @classmethod
    def from_dict(cls, d, index=0):
        if not isinstance(d, dict):
            raise ValidationError(f"Machine {index + 1} is not valid.")
        name = str(_get(d, "name", "")).strip()[:80] or f"Machine {index + 1}"
        tag = f"'{name}'"
        return cls(
            name=name,
            power_watts=_num(d.get("power_watts"), f"{tag} power (watts)", 0, 1e8, True),
            hours_per_day=_num(d.get("hours_per_day"), f"{tag} hours per day", 0, 24),
            quantity=int(_num(_get(d, "quantity", 1), f"{tag} quantity", 1, 100000)),
            load_factor=_num(_get(d, "load_factor", 1.0), f"{tag} load factor", 0, 1),
            days_per_month=_num(_get(d, "days_per_month", 30), f"{tag} days per month", 1, 31),
        )


@dataclass
class Settings:
    tariff: float = 209.5            # naira per kWh from the grid (edit to match your bill)
    generator_share: float = 0.0     # % of energy supplied by diesel generator
    diesel_price: float = 1200.0     # naira per litre
    kwh_per_litre: float = 3.0       # generator output per litre of diesel
    grid_co2: float = 0.43           # kg CO2 per grid kWh (assumption, editable)
    diesel_co2: float = 2.68         # kg CO2 per litre diesel
    efficiency_gain: float = 0.0     # % energy saved by upgrades (what-if)
    solar_share: float = 0.0         # % of remaining energy covered by solar (what-if)

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        dflt = cls()
        return cls(
            tariff=_num(_get(d, "tariff", dflt.tariff), "Grid tariff", 0, 1e6, True),
            generator_share=_num(_get(d, "generator_share", 0), "Generator share (%)", 0, 100),
            diesel_price=_num(_get(d, "diesel_price", dflt.diesel_price), "Diesel price", 0, 1e6),
            kwh_per_litre=_num(_get(d, "kwh_per_litre", dflt.kwh_per_litre), "kWh per litre", 0, 20, True),
            grid_co2=_num(_get(d, "grid_co2", dflt.grid_co2), "Grid CO2 factor", 0, 5),
            diesel_co2=_num(_get(d, "diesel_co2", dflt.diesel_co2), "Diesel CO2 factor", 0, 10),
            efficiency_gain=_num(_get(d, "efficiency_gain", 0), "Efficiency gain (%)", 0, 90),
            solar_share=_num(_get(d, "solar_share", 0), "Solar share (%)", 0, 100),
        )


def _supply(kwh, s: Settings):
    """Split energy between grid and generator and price it."""
    gen_kwh = kwh * s.generator_share / 100
    grid_kwh = kwh - gen_kwh
    litres = gen_kwh / s.kwh_per_litre
    grid_cost = grid_kwh * s.tariff
    gen_cost = litres * s.diesel_price
    return {
        "grid_kwh": grid_kwh,
        "gen_kwh": gen_kwh,
        "diesel_litres": litres,
        "grid_cost": grid_cost,
        "gen_cost": gen_cost,
        "cost": grid_cost + gen_cost,
        "co2_kg": grid_kwh * s.grid_co2 + litres * s.diesel_co2,
    }


def calculate(machines, s: Settings):
    if not machines:
        raise ValidationError("Add at least one machine.")
    if len(machines) > MAX_MACHINES:
        raise ValidationError(f"At most {MAX_MACHINES} machines are allowed.")

    rows = []
    for m in machines:
        kwh_day = m.power_watts * m.quantity * m.hours_per_day * m.load_factor / 1000
        rows.append({
            "name": m.name,
            "quantity": m.quantity,
            "connected_kw": m.power_watts * m.quantity / 1000,
            "kwh_day": kwh_day,
            "kwh_month": kwh_day * m.days_per_month,
        })

    kwh_month = sum(r["kwh_month"] for r in rows)
    kwh_day_total = sum(r["kwh_day"] for r in rows)
    now = _supply(kwh_month, s)
    rate = now["cost"] / kwh_month if kwh_month > 0 else 0.0

    for r in rows:
        r["cost_month"] = r["kwh_month"] * rate
        r["share_pct"] = 100 * r["kwh_month"] / kwh_month if kwh_month > 0 else 0.0

    # What-if: efficiency upgrades first, then solar covers part of what is left.
    kwh_after = kwh_month * (1 - s.efficiency_gain / 100) * (1 - s.solar_share / 100)
    after = _supply(kwh_after, s)

    grid_rate, gen_rate = s.tariff, s.diesel_price / s.kwh_per_litre
    insights = []
    top = max(rows, key=lambda r: r["kwh_month"])
    if kwh_month > 0:
        insights.append(f"{top['name']} uses {top['share_pct']:.0f}% of your energy: start efficiency work there.")
    if s.generator_share > 0:
        insights.append(
            f"Generator power costs N{gen_rate:,.0f}/kWh versus N{grid_rate:,.0f}/kWh from the grid "
            f"({gen_rate / grid_rate:.1f}x). Shifting load to the grid or solar is the biggest saving."
        )

    result = {
        "machines": rows,
        "totals": {
            "connected_kw": sum(r["connected_kw"] for r in rows),
            "kwh_day": kwh_day_total,
            "kwh_month": kwh_month,
            "blended_rate": rate,
            "cost_day": now["cost"] / 30,
            "cost_month": now["cost"],
            "cost_year": now["cost"] * 12,
            **{k: now[k] for k in ("grid_kwh", "gen_kwh", "diesel_litres", "grid_cost", "gen_cost", "co2_kg")},
        },
        "scenario": {
            "kwh_month": kwh_after,
            "cost_month": after["cost"],
            "saving_month": now["cost"] - after["cost"],
            "saving_year": (now["cost"] - after["cost"]) * 12,
            "co2_kg": after["co2_kg"],
            "co2_saved_kg": now["co2_kg"] - after["co2_kg"],
        },
        "insights": insights,
    }
    return result


def calculate_from_payload(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Request must be a JSON object.")
    raw = payload.get("machines")
    if not isinstance(raw, list):
        raise ValidationError("'machines' must be a list.")
    if len(raw) > MAX_MACHINES:
        raise ValidationError(f"At most {MAX_MACHINES} machines are allowed.")
    machines = [Machine.from_dict(m, i) for i, m in enumerate(raw)]
    return calculate(machines, Settings.from_dict(payload.get("settings")))


def _safe_cell(text):
    """Stop spreadsheet formula injection when a name starts with = + - @."""
    text = str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def to_csv(result, org=""):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Energy report", _safe_cell(org)])
    w.writerow([])
    w.writerow(["Machine", "Quantity", "Connected kW", "kWh/day", "kWh/month", "Cost/month (N)", "Share %"])
    for r in result["machines"]:
        w.writerow([_safe_cell(r["name"]), r["quantity"], f"{r['connected_kw']:.2f}",
                    f"{r['kwh_day']:.2f}", f"{r['kwh_month']:.2f}",
                    f"{r['cost_month']:.2f}", f"{r['share_pct']:.1f}"])
    t, sc = result["totals"], result["scenario"]
    w.writerow([])
    w.writerow(["Total kWh/month", f"{t['kwh_month']:.2f}"])
    w.writerow(["Total cost/month (N)", f"{t['cost_month']:.2f}"])
    w.writerow(["Total cost/year (N)", f"{t['cost_year']:.2f}"])
    w.writerow(["Diesel litres/month", f"{t['diesel_litres']:.1f}"])
    w.writerow(["CO2 kg/month", f"{t['co2_kg']:.1f}"])
    w.writerow(["Scenario saving/month (N)", f"{sc['saving_month']:.2f}"])
    w.writerow(["Scenario saving/year (N)", f"{sc['saving_year']:.2f}"])
    return out.getvalue()
