import json
import re
from pathlib import Path
from datetime import date, datetime
import requests

LIST_URL = (
    "https://www.omie.es/en/file-access-list"
    "?dir=Precios+horarios+del+mercado+diario+en+Espa%C3%B1a"
    "&parents%5B0%5D=%2F"
    "&parents%5B1%5D=Mercado+Diario"
    "&parents%5B2%5D=1.+Precios"
    "&realdir=marginalpdbc"
)

DOWNLOAD_URL = "https://www.omie.es/en/file-download"

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)

today = date.today()
today_str = today.strftime("%Y%m%d")
now = datetime.now()
current_hour = now.hour + 1  # OMIE usa 1..24 normalmente


def get_level(price: float, min_price: float, max_price: float) -> str:
    if max_price == min_price:
        return "medium"

    ratio = (price - min_price) / (max_price - min_price)

    if ratio <= 0.33:
        return "cheap"
    if ratio <= 0.66:
        return "medium"
    return "expensive"


# 1) Leer el índice público
index_resp = session.get(LIST_URL, timeout=30)
index_resp.raise_for_status()
index_html = index_resp.text

# 2) Buscar fichero de hoy; si no existe, usar el más reciente visible
pattern_today = rf"marginalpdbc_{today_str}\.\d+"
matches_today = re.findall(pattern_today, index_html)

if matches_today:
    filename = matches_today[0]
else:
    all_files = re.findall(r"marginalpdbc_\d{8}\.\d+", index_html)
    if not all_files:
        raise RuntimeError("No se encontró ningún fichero marginalpdbc en el índice público de OMIE.")
    filename = all_files[0]

# 3) Descargar fichero
file_resp = session.get(
    DOWNLOAD_URL,
    params={"filename": filename, "parents": "marginalpdbc"},
    timeout=30,
)
file_resp.raise_for_status()
content = file_resp.text.strip()

if not content:
    raise RuntimeError(f"No se pudo descargar contenido válido desde OMIE. filename={filename}")

prices = []

for raw_line in content.splitlines():
    line = raw_line.strip()
    if not line:
        continue

    parts = [p.strip() for p in line.split(";")]

    # Filas de datos: YYYY;MM;DD;HORA;PT;ES;
    if len(parts) < 6:
        continue
    if not re.fullmatch(r"\d{4}", parts[0] or ""):
        continue

    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        hour = int(parts[3])
        price_pt = float(parts[4].replace(",", "."))
        price_es = float(parts[5].replace(",", "."))
    except ValueError:
        continue

    prices.append(
        {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "hour_label": f"{hour:02d}:00",
            "price_pt_eur_mwh": round(price_pt, 2),
            "price_es_eur_mwh": round(price_es, 2),
            "price_es_eur_kwh": round(price_es / 1000, 5),
        }
    )

if not prices:
    raise RuntimeError(f"Se descargó el fichero {filename}, pero no se pudieron extraer precios.")

# Orden por hora por seguridad
prices.sort(key=lambda x: x["hour"])

min_item = min(prices, key=lambda x: x["price_es_eur_kwh"])
max_item = max(prices, key=lambda x: x["price_es_eur_kwh"])
average_price = round(sum(p["price_es_eur_kwh"] for p in prices) / len(prices), 5)

# Añadir nivel cheap/medium/expensive a cada hora
for item in prices:
    item["level"] = get_level(
        item["price_es_eur_kwh"],
        min_item["price_es_eur_kwh"],
        max_item["price_es_eur_kwh"],
    )

current_item = next((p for p in prices if p["hour"] == current_hour), None)
next_item = next((p for p in prices if p["hour"] == current_hour + 1), None)

data = {
    "date": str(today),
    "source": "OMIE",
    "filename": filename,
    "updated_at": datetime.now().isoformat(),
    "count": len(prices),
    "current_hour": current_hour,
    "current_price": current_item["price_es_eur_kwh"] if current_item else None,
    "next_price": next_item["price_es_eur_kwh"] if next_item else None,
    "average_price": average_price,
    "min_price": min_item["price_es_eur_kwh"],
    "max_price": max_item["price_es_eur_kwh"],
    "cheapest_hour": {
        "hour": min_item["hour"],
        "hour_label": min_item["hour_label"],
        "price": min_item["price_es_eur_kwh"],
    },
    "most_expensive_hour": {
        "hour": max_item["hour"],
        "hour_label": max_item["hour_label"],
        "price": max_item["price_es_eur_kwh"],
    },
    "prices": prices,
}

docs_dir = Path("docs")
docs_dir.mkdir(exist_ok=True)

precios_dir = docs_dir / "precios"
precios_dir.mkdir(exist_ok=True)

latest_path = docs_dir / "latest.json"
history_path = precios_dir / f"{today}.json"

latest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"OK: {latest_path}")
print(f"OK: {history_path}")
print(f"Archivo OMIE usado: {filename}")
print(f"Precios extraídos: {len(prices)}")
