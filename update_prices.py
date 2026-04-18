import json
from pathlib import Path
from datetime import date
import requests

today = date.today()
today_str = today.strftime("%Y%m%d")

content = None
last_url = None

for version in ["1", "2", "3"]:
    url = (
        f"https://www.omie.es/sites/default/files/dados/AGNO_{today_str[:4]}/"
        f"MES_{today_str[4:6]}/TXT/marginalpdbc_{today_str}.{version}"
    )
    last_url = url
    response = requests.get(url, timeout=30)
    if response.status_code == 200 and response.text.strip():
        content = response.text
        break

if not content:
    raise RuntimeError(f"No se pudo descargar OMIE. Última URL probada: {last_url}")

prices = []

for line in content.splitlines():
    parts = line.strip().split(";")

    if not parts or parts[0] != "MARGINALPDBC":
        continue

    # Formato esperado:
    # MARGINALPDBC;YYYY;MM;DD;HORA;MarginalPT;MarginalES;
    if len(parts) >= 7:
        try:
            hour = int(parts[4])
            price_es = float(parts[6].replace(",", "."))
            prices.append({
                "hour": hour,
                "price_eur_mwh": price_es,
                "price_eur_kwh": round(price_es / 1000, 5)
            })
        except ValueError:
            continue

if not prices:
    raise RuntimeError("No se encontraron precios en el fichero descargado.")

data = {
    "date": str(today),
    "source": "OMIE",
    "count": len(prices),
    "prices": prices
}

docs_dir = Path("docs")
docs_dir.mkdir(exist_ok=True)

precios_dir = docs_dir / "precios"
precios_dir.mkdir(exist_ok=True)

latest_path = docs_dir / "latest.json"
history_path = precios_dir / f"{today}.json"

latest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Generado: {latest_path}")
print(f"Generado: {history_path}")
