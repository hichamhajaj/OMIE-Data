# OMIE + GitHub Pages + GitHub Actions

Plantilla mínima para publicar un JSON diario del precio mayorista OMIE y consumirlo desde una app iOS, Android o web.

## Qué hace

- descarga el fichero diario `marginalpdbc_YYYYMMDD.v` de OMIE,
- extrae `MarginalES`,
- genera `docs/latest.json`,
- guarda histórico en `docs/precios/YYYY-MM-DD.json`,
- publica todo con GitHub Pages.

## Importante

Esto publica **precio OMIE del mercado diario**, no **PVPC oficial**.

## Estructura

- `scripts/update_prices.py`: descarga y parsea OMIE
- `.github/workflows/update-omie.yml`: ejecución diaria automática
- `docs/latest.json`: JSON para tu app
- `docs/index.html`: página simple de comprobación

## Pasos

1. Crea un repositorio en GitHub.
2. Sube todo el contenido de esta plantilla.
3. En GitHub, ve a **Settings > Pages**.
4. En **Build and deployment**, elige **Deploy from a branch**.
5. En **Branch**, selecciona `main` y carpeta `/docs`.
6. Guarda.
7. En **Actions**, ejecuta manualmente el workflow **Update OMIE prices** la primera vez.

## URL final

Tu JSON quedará normalmente en:

```text
https://TU-USUARIO.github.io/TU-REPO/latest.json
```

Y el índice web en:

```text
https://TU-USUARIO.github.io/TU-REPO/
```

## Swift ejemplo

```swift
import Foundation

struct PriceResponse: Decodable {
    let source: String
    let date: String
    let prices: [HourPrice]
}

struct HourPrice: Decodable, Identifiable {
    var id: Int { hour }
    let hour: Int
    let hour_label: String
    let price_eur_mwh: Double
    let price_eur_kwh: Double
}

func fetchPrices() async throws -> PriceResponse {
    let url = URL(string: "https://TU-USUARIO.github.io/TU-REPO/latest.json")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return try JSONDecoder().decode(PriceResponse.self, from: data)
}
```

## Notas

- El workflow usa `workflow_dispatch` para poder lanzarlo a mano.
- También usa `schedule` para ejecutarse cada día.
- El script prueba versiones `.1`, `.2` y `.3` del fichero.
- En cambios de hora puede haber 23, 24 o 25 registros.
