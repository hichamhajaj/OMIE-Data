import json
import re
from pathlib import Path
from datetime import date, datetime
import requests

# --- Configuración ---
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
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,/;q=0.8",
})

today = date.today()
today_str = today.strftime("%Y%m%d")
now = datetime.now()
current_hour = now.hour + 1  # OMIE suele usar horas 1..24

# --- Funciones Auxiliares ---
def classify_level(price: float, min_price: float, max_price: float) -> str:
    if max_price == min_price:
        return "medium"
    ratio = (price - min_price) / (max_price - min_price)
    if ratio <= 0.33:
        return "cheap"
    if ratio <= 0.66:
        return "medium"
    return "expensive"

def build_hour_label(hour: int) -> str:
    start_hour = max(0, hour - 1)
    end_hour = hour if hour < 24 else 24
    return f"{start_hour:02d}:00-{end_hour:02d}:00"

def get_best_ranges(prices: list[dict], max_results: int = 5) -> list[dict]:
    sorted_prices = sorted(prices, key=lambda x: (x["price_es_eur_kwh"], x["hour"]))
    best = []
    for item in sorted_prices[:max_results]:
        best.append({
            "hour": item["hour"],
            "hour_label": item["hour_label"],
            "price": item["price_es_eur_kwh"],
            "level": item["level"],
        })
    return best

def get_consecutive_blocks(prices: list[dict], size: int) -> list[dict]:
    blocks = []
    if len(prices) < size:
        return blocks
    for i in range(len(prices) - size + 1):
        block = prices[i:i + size]
        hours = [x["hour"] for x in block]
        # evitar bloques rotos si falta alguna hora
        if hours != list(range(hours[0], hours[0] + size)):
            continue
        avg_price = round(sum(x["price_es_eur_kwh"] for x in block) / size, 5)
        blocks.append({
            "start_hour": block[0]["hour"],
            "end_hour": block[-1]["hour"],
            "start_label": block[0]["hour_label"],
            "end_label": block[-1]["hour_label"],
            "hours": hours,
            "average_price": avg_price,
        })
    blocks.sort(key=lambda x: x["average_price"])
    return blocks[:5]

# --- Lógica de descarga y parseo ---
def download_omie_file() -> tuple[str, str]:
    index_resp = session.get(LIST_URL, timeout=30)
    index_resp.raise_for_status()
    index_html = index_resp.text
    pattern_today = rf"marginalpdbc_{today_str}\.\d+"
    matches_today = re.findall(pattern_today, index_html)

    if matches_today:
        filename = matches_today[0]
    else:
        all_files = re.findall(r"marginalpdbc_\d{8}\.\d+", index_html)
        if not all_files:
            raise RuntimeError("No se encontró ningún fichero marginalpdbc en OMIE.")
        filename = all_files[0]

    file_resp = session.get(
        DOWNLOAD_URL,
        params={"filename": filename, "parents": "marginalpdbc"},
        timeout=30,
    )
    file_resp.raise_for_status()
    content = file_resp.text.strip()
    if not content:
        raise RuntimeError(f"Contenido vacío en {filename}")
    return filename, content

def parse_prices(content: str) -> list[dict]:
    prices = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line: continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6 or not re.fullmatch(r"\d{4}", parts[0] or ""):
            continue
        try:
            hour = int(parts[3])
            price_pt = float(parts[4].replace(",", "."))
            price_es = float(parts[5].replace(",", "."))
            prices.append({
                "year": int(parts[0]),
                "month": int(parts[1]),
                "day": int(parts[2]),
                "hour": hour,
                "hour_label": build_hour_label(hour),
                "price_pt_eur_mwh": round(price_pt, 2),
                "price_es_eur_mwh": round(price_es, 2),
                "price_es_eur_kwh": round(price_es / 1000, 5),
            })
        except ValueError:
            continue
    prices.sort(key=lambda x: x["hour"])
    if not prices:
        raise RuntimeError("No se pudieron extraer precios.")
    return prices

def enrich_prices(prices: list[dict]) -> dict:
    min_item = min(prices, key=lambda x: x["price_es_eur_kwh"])
    max_item = max(prices, key=lambda x: x["price_es_eur_kwh"])
    avg_price = round(sum(p["price_es_eur_kwh"] for p in prices) / len(prices), 5)
    
    for item in prices:
        item["level"] = classify_level(item["price_es_eur_kwh"], min_item["price_es_eur_kwh"], max_item["price_es_eur_kwh"])

    current_item = next((p for p in prices if p["hour"] == current_hour), None)
    next_item = next((p for p in prices if p["hour"] == current_hour + 1), None)

    return {
        "summary": {
            "current_hour": current_hour,
            "current_price": current_item["price_es_eur_kwh"] if current_item else None,
            "next_price": next_item["price_es_eur_kwh"] if next_item else None,
            "average_price": avg_price,
            "min_price": min_item["price_es_eur_kwh"],
            "max_price": max_item["price_es_eur_kwh"],
            "cheapest_hour": {"hour": min_item["hour"], "hour_label": min_item["hour_label"], "price": min_item["price_es_eur_kwh"]},
            "most_expensive_hour": {"hour": max_item["hour"], "hour_label": max_item["hour_label"], "price": max_item["price_es_eur_kwh"]},
        },
        "insights": {
            "best_hours_1h": get_best_ranges(prices),
            "best_blocks_2h": get_consecutive_blocks(prices, 2),
            "best_blocks_3h": get_consecutive_blocks(prices, 3),
            "cheap_hours_count": len([p for p in prices if p["level"] == "cheap"]),
            "medium_hours_count": len([p for p in prices if p["level"] == "medium"]),
            "expensive_hours_count": len([p for p in prices if p["level"] == "expensive"]),
        },
    }

def generate_history(precios_dir: Path, limit: int = 90) -> dict:
    history_files = sorted(precios_dir.glob("*.json"), reverse=True)
    days = []
    for file_path in history_files[:limit]:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            s = data.get("summary", {})
            days.append({
                "date": data.get("date"),
                "average_price": s.get("average_price"),
                "min_price": s.get("min_price"),
                "max_price": s.get("max_price"),
                "cheapest_hour": s.get("cheapest_hour"),
                "most_expensive_hour": s.get("most_expensive_hour"),
            })
        except: continue
    return {"updated_at": datetime.now().isoformat(), "days_count": len(days), "days": sorted(days, key=lambda x: x["date"] or "")}

# --- Ejecución Principal ---
def main():
    filename, content = download_omie_file()
    prices = parse_prices(content)
    enriched = enrich_prices(prices)
    
    day_payload = {
        "date": str(today),
        "source": "OMIE",
        "filename": filename,
        "updated_at": datetime.now().isoformat(),
        "count": len(prices),
        **enriched,
        "prices": prices,
    }

    docs_dir = Path("docs")
    precios_dir = docs_dir / "precios"
    precios_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "latest.json").write_text(json.dumps(day_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (precios_dir / f"{today}.json").write_text(json.dumps(day_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    
    history_payload = generate_history(precios_dir)
    (docs_dir / "history.json").write_text(json.dumps(history_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"Éxito. Archivo: {filename} | Precios: {len(prices)}")

if __name__ == "__main__":
    main()
