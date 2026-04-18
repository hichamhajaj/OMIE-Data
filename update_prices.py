import requests
import json
from pathlib import Path
from datetime import date

today = date.today().strftime("%Y%m%d")

versions = ["1", "2", "3"]
content = None

for version in versions:
url = f"https://www.omie.es/sites/default/files/dados/AGNO_{today[:4]}/MES_{today[4:6]}/TXT/marginalpdbc_{today}.{version}"
r = requests.get(url)

```
if r.status_code == 200:
    content = r.text
    break
```

if not content:
raise Exception("No se pudo descargar OMIE")

lines = content.splitlines()

prices = []

for line in lines:
parts = line.split(";")

```
if len(parts) >= 6 and parts[0] == "MARGINALPDBC":
    try:
        hour = int(parts[4])
        price = float(parts[6].replace(",", "."))

        prices.append({
            "hour": hour,
            "price_eur_mwh": price,
            "price_eur_kwh": round(price / 1000, 5)
        })

    except:
        continue
```

data = {
"date": str(date.today()),
"source": "OMIE",
"prices": prices
}

docs_dir = Path("docs")
docs_dir.mkdir(exist_ok=True)

precios_dir = docs_dir / "precios"
precios_dir.mkdir(exist_ok=True)

with open(docs_dir / "latest.json", "w", encoding="utf-8") as f:
json.dump(data, f, ensure_ascii=False, indent=2)

with open(precios_dir / f"{date.today()}.json", "w", encoding="utf-8") as f:
json.dump(data, f, ensure_ascii=False, indent=2)

print("JSON generado correctamente")
