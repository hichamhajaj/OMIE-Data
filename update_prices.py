from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE_URL = "https://www.omie.es/es/file-download"
REALDIR = "marginalpdbc"
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HIST = DOCS / "precios"
TIMEOUT = 30


@dataclass
class HourPrice:
    hour: int
    hour_label: str
    price_eur_mwh: float
    price_eur_kwh: float



def madrid_today() -> date:
    # CEST/CET is good enough here because the workflow is scheduled around midday.
    # We intentionally avoid external tz dependencies.
    now_utc = datetime.now(timezone.utc)
    approx_madrid = now_utc + timedelta(hours=2)
    return approx_madrid.date()



def target_market_date() -> date:
    # OMIE publishes next-day day-ahead prices, so the file generated today normally
    # corresponds to tomorrow's delivery date.
    return madrid_today() + timedelta(days=1)



def build_candidate_urls(day: date) -> List[str]:
    ymd = day.strftime("%Y%m%d")
    # Try common versions first. .1 is by far the most common, but .2/.3 may exist.
    candidates = []
    for version in ("1", "2", "3"):
        filename = f"marginalpdbc_{ymd}.{version}"
        candidates.append(f"{BASE_URL}?parents%5B0%5D=marginalpdbc&filename={filename}&realdir={REALDIR}")
    return candidates



def fetch_text(day: date) -> str:
    errors = []
    for url in build_candidate_urls(day):
        try:
            with urlopen(url, timeout=TIMEOUT) as response:
                raw = response.read()
                return raw.decode("latin-1")
        except (HTTPError, URLError) as exc:
            errors.append(f"{url} -> {exc}")
            continue
    raise RuntimeError("No se pudo descargar ningún fichero OMIE para la fecha objetivo.\n" + "\n".join(errors))



def parse_prices(text: str, expected_day: date) -> List[HourPrice]:
    rows: List[HourPrice] = []
    date_token = expected_day.strftime("%Y;%m;%d;")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == ";":
            continue
        if not re.match(r"^\d{4};\d{2};\d{2};\d{1,2};", line):
            continue

        parts = [p.strip() for p in line.split(";") if p.strip() != ""]
        if len(parts) < 6:
            continue

        year, month, day, hour = map(int, parts[:4])
        if date(year, month, day) != expected_day:
            continue

        price_es = float(parts[5].replace(",", "."))
        hour_label = f"{hour:02d}:00-{(hour % 24):02d}:00"
        rows.append(
            HourPrice(
                hour=hour,
                hour_label=hour_label,
                price_eur_mwh=round(price_es, 2),
                price_eur_kwh=round(price_es / 1000, 5),
            )
        )

    if not rows:
        preview = "\n".join(text.splitlines()[:20])
        raise RuntimeError(
            "Se descargó el fichero OMIE pero no se pudieron extraer precios. "
            f"Fecha esperada: {expected_day.isoformat()}\nVista previa:\n{preview}"
        )

    rows.sort(key=lambda x: x.hour)
    return rows



def build_payload(prices: List[HourPrice], market_day: date) -> dict:
    cheapest = min(prices, key=lambda x: x.price_eur_kwh)
    most_expensive = max(prices, key=lambda x: x.price_eur_kwh)
    avg_kwh = round(sum(p.price_eur_kwh for p in prices) / len(prices), 5)
    avg_mwh = round(sum(p.price_eur_mwh for p in prices) / len(prices), 2)

    return {
        "source": "OMIE",
        "market": "day-ahead",
        "country": "ES",
        "note": "Precio mayorista horario del mercado diario. No es PVPC oficial.",
        "date": market_day.isoformat(),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "unit": {
            "display": "EUR/kWh",
            "raw": "EUR/MWh"
        },
        "summary": {
            "hours_count": len(prices),
            "avg_eur_mwh": avg_mwh,
            "avg_eur_kwh": avg_kwh,
            "cheapest_hour": asdict(cheapest),
            "most_expensive_hour": asdict(most_expensive),
        },
        "prices": [asdict(p) for p in prices],
    }



def write_json(payload: dict) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    HIST.mkdir(parents=True, exist_ok=True)

    latest_path = DOCS / "latest.json"
    dated_path = HIST / f"{payload['date']}.json"

    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    index_payload = {
        "latest": payload["date"],
        "history": sorted([p.name for p in HIST.glob("*.json")], reverse=True),
    }
    (DOCS / "index.json").write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")



def write_index_html(payload: dict) -> None:
    cheapest = payload["summary"]["cheapest_hour"]
    expensive = payload["summary"]["most_expensive_hour"]
    html = f"""<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Precio luz OMIE</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 40px auto; padding: 0 16px; }}
    code, pre {{ background: #f5f5f5; padding: 2px 6px; border-radius: 6px; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 12px 0; }}
  </style>
</head>
<body>
  <h1>Precio diario OMIE</h1>
  <p><strong>Fecha de mercado:</strong> {payload['date']}</p>
  <p><strong>Actualizado:</strong> {payload['updated_at']}</p>
  <div class=\"card\">
    <p><strong>Media:</strong> {payload['summary']['avg_eur_kwh']} €/kWh</p>
    <p><strong>Hora más barata:</strong> {cheapest['hour_label']} — {cheapest['price_eur_kwh']} €/kWh</p>
    <p><strong>Hora más cara:</strong> {expensive['hour_label']} — {expensive['price_eur_kwh']} €/kWh</p>
  </div>
  <p>JSON actual: <a href=\"./latest.json\">latest.json</a></p>
  <p>Índice histórico: <a href=\"./index.json\">index.json</a></p>
  <p>Histórico por fecha: <a href=\"./precios/\">/precios/</a></p>
  <p><em>Nota:</em> esto es OMIE (mercado mayorista), no PVPC oficial.</p>
</body>
</html>
"""
    (DOCS / "index.html").write_text(html, encoding="utf-8")



def main() -> None:
    market_day = target_market_date()
    raw_text = fetch_text(market_day)
    prices = parse_prices(raw_text, market_day)
    payload = build_payload(prices, market_day)
    write_json(payload)
    write_index_html(payload)
    print(f"OK: generado latest.json para {market_day.isoformat()} con {len(prices)} horas")


if __name__ == "__main__":
    main()
