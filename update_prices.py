import json
import re
from pathlib import Path
from datetime import date

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

# 1) Leer el índice público
index_resp = session.get(LIST_URL, timeout=30)
index_resp.raise_for_status()
index_html = index_resp.text

# 2) Intentar coger el fichero de hoy; si no, el más reciente del índice
pattern_today = rf"marginalpdbc_{today_str}\.\d+"
matches_today = re.findall(pattern_today, index_html)

if matches_today:
    filename = matches_today[0]
else:
    all_files = re.findall(r"marginalpdbc_\d{8}\.\d+", index_html)
    if not all_files:
        raise RuntimeError("No se encontró ningún fichero marginalpdbc en el índice público de OMIE.")
    filename = all_files[0]

# 3) Descargar el fichero real
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

    # Saltar cabeceras, títulos y líneas no numéricas
    # Las filas de datos empiezan por año, ej: 2026;04;18;1;...
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
            "price_pt_eur_mwh": price_pt,
            "price_es_eur_mwh": price_es,
            "price_es_eur_kwh": round(price_es / 1000, 5),
        }
    )

if not prices:
    raise RuntimeError(f"Se descargó el fichero {filename}, pero no se pudieron extraer precios.")

data = {
    "date": str(today),
    "source": "OMIE",
    "filename": filename,
    "count": len(prices),
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
