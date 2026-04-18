import json
import re
from pathlib import Path
from datetime import date

import requests

LIST_URL = (
    "https://www.omie.es/en/file-access-list"
    "?dir=Precios+horarios+del+mercado+diario+en+España"
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

# 1) Leer el índice público de OMIE
index_resp = session.get(LIST_URL, timeout=30)
index_resp.raise_for_status()
index_html = index_resp.text

# 2) Buscar el fichero del día actual; si no está, coger el más reciente del índice
pattern_today = rf"marginalpdbc_{today_str}\.\d+"
matches_today = re.findall(pattern_today, index_html)

if matches_today:
    filename = matches_today[0]
else:
    all_files = re.findall(r"marginalpdbc_\d{8}\.\d+", index_html)
    if not all_files:
        raise RuntimeError("No se encontró ningún fichero marginalpdbc en el índice público de OMIE.")
    filename = all_files[0]

# 3) Descargar el fichero real usando el endpoint público del sitio
file_resp = session.get(
    DOWNLOAD_URL,
    params={"filename": filename, "parents": "marginalpdbc"},
    timeout=30,
)

# A veces OMIE devuelve 200 aunque el contenido no sea válido; validamos también texto
file_resp.raise_for_status()
content = file_resp.text.strip()

if not content or "MARGINALPDBC" not in content:
    raise RuntimeError(f"No se pudo descargar un fichero válido desde OMIE. filename={filename}")

# 4) Parsear filas
prices = []

for line in content.splitlines():
    parts = line.strip().split(";")

    # Formato esperado:
    # MARGINALPDBC;YYYY;MM;DD;HORA;MarginalPT;MarginalES;
    if len(parts) >= 7 and parts[0] == "MARGINALPDBC":
        try:
            hour = int(parts[4])
            price_es = float(parts[6].replace(",", "."))
            prices.append(
                {
                    "hour": hour,
                    "price_eur_mwh": price_es,
                    "price_eur_kwh": round(price_es / 1000, 5),
                }
            )
        except ValueError:
            continue

if not prices:
    raise RuntimeError(f"Se descargó el fichero {filename}, pero no se pudieron extraer precios.")

# 5) Generar JSON
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
