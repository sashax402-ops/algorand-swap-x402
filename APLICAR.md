# Cómo aplicar esto

## 1. Archivos que reemplazan a los tuyos (mismo path)
- `news/providers.py` → sustituye al actual
- `news/ranking.py` → sustituye al actual
- `news/nlp_store.py`, `news/nlp_provider.py` → nuevos

## 2. `news/service.py` — una línea (arregla la caché)
No lo reescribí completo porque no toca nada más. En `report()`, dentro de
`config_signature`, añade una clave:

```python
config_signature = {"demo": self.settings.demo, "hours": self.settings.max_age_hours,
                    "language": self.settings.language, "ai": self.settings.ai_enabled,
                    "model": self.settings.ai_model, "asset": asset,
                    "nlp": getattr(self.settings, "nlp_source_enabled", False),  # NUEVO
                    "providers": sorted(k for k, v in self.settings.provider_keys.items() if v)}
```

Sin esto, activar/desactivar `NLP_SOURCE_ENABLED` no invalida la caché de 15 min:
seguirías viendo el reporte viejo un rato tras el cambio.

## 3. `news/config.py` — no lo tengo
Nunca lo subiste (subiste el `config.py` del motor NLP, que es un archivo distinto
con el mismo nombre). Añade un campo a tu `Settings`, con el mismo patrón que uses
para `DEMO_MODE`/`PAYMENTS_ENABLED`:

```python
nlp_source_enabled: bool = ...  # desde NLP_SOURCE_ENABLED, default false
```

`providers.py`/`service.py` ya usan `getattr(self.settings, "nlp_source_enabled", False)`,
así que funcionan aunque no añadas el campo (la fuente queda desactivada, como ahora) —
esto es solo para poder activarla vía `.env` de forma prolija.

Si me pasas tu `news/config.py` real, te devuelvo el diff exacto en vez de esta nota.

En `render.yaml`, si despliegas ahí, añade análogamente:
```yaml
      - key: NLP_SOURCE_ENABLED
        value: "false"
```

## 4. Correr el colector (proceso aparte, en el OTRO repo)
Con el venv del motor NLP (el que ya usas para `main_live.py`), desde su carpeta:

```bash
python nlp_collector.py \
  --db /ruta/a/trading_news_v2/data/news.sqlite3 \
  --assets /ruta/a/trading_news_v2/assets.json
```

Usa la misma ruta que `DATABASE_PATH`/`settings.db_path` en Trading News (en
`render.yaml` es `/var/data/news.sqlite3`; en local, la que tengas en tu `.env`).

## 5. Limitación real que no puedo resolver sin más archivos
`resolve_symbol()` en `nlp_collector.py` solo empareja `evento.activo` contra
símbolo/alias/nombre exacto de tu `assets.json`. No tengo
`nlp_pipeline/correlation_matrix.py`, así que no sé qué valores produce
`mapear_evento()` — el ejemplo de tu propio `pipeline.py` ("aranceles a China")
sugiere activos macro (SP500, etc.), no cripto. Es muy probable que, tal cual,
esto no capture nada todavía. Pásame `correlation_matrix.py` y te ayudo a mapear
sus categorías a tus 49 tickers cripto.

## 6. El botón de comprar
Antes de nada, revisa si es `PAYMENTS_ENABLED=false` (ver el mensaje del chat).
Si ya está en `true` y sigue sin responder, pásame `frontend/wallet.js` (el
fuente, no `static/wallet.js` compilado) para depurar `connect()`/`sign()`.
