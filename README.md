# Next Trip Finder

Buscador de vuelos baratos por **rango de fechas** (no fecha fija), con franjas
horarias de salida independientes para ida y vuelta, y modo exploración de
varios destinos (o una selección de destinos europeos populares) a la vez.

## Fuente de datos: Google Flights vía `fast-flights` (por defecto) — ⚠️ léelo antes de usarlo

Se evaluaron, por este orden, **Kiwi Tequila** (cerrado a autoservicio,
invitación únicamente), **Amadeus for Developers** (decomisionó su portal
self-service el 17/07/2026, claves existentes desactivadas) y **Duffel**
(oficial y de pago en modo real: ~0,005 $/búsqueda). Ninguna de las tres es
gratis y sin condiciones hoy en día.

El provider por defecto es **`fast-flights`**
(https://github.com/AWeirdDev/flights), una librería Python que decodifica el
mismo payload protobuf que usa la propia web de Google Flights. Es la única
opción de este proyecto que es a la vez **gratis** y da **datos reales**
(precio, aerolínea, hora, escalas) — a cambio de un riesgo real que debes
aceptar conscientemente:

- **No es una API oficial.** No hay acuerdo con Google; es ingeniería inversa
  de un endpoint interno no pensado para terceros.
- **Puede romperse sin aviso** si Google cambia el formato interno. De hecho
  ya hubo que trabajar alrededor de dos límites confirmados al probar esto
  contra datos reales (ver más abajo): la interstitial de consentimiento de
  cookies de la UE, y que el modo "round-trip" de la librería nunca devuelve
  la vuelta combinada con la ida.
- **Riesgo de bloqueo**: no hay límites de tasa documentados porque no es una
  API oficial. Tráfico repetido desde la IP de tu VPS podría acabar
  bloqueado o recibiendo CAPTCHAs. `GOOGLE_FLIGHTS_MAX_CONCURRENCY` limita
  cuántas búsquedas van en paralelo, y `GOOGLE_FLIGHTS_PROXY` permite enrutar
  a través de un proxy si lo necesitas, pero ninguna de las dos cosas
  elimina el riesgo.
- Zona legal gris: probablemente incumple los términos de uso de Google.

No hace falta ninguna API key para este provider — funciona nada más
instalar dependencias.

### Dos límites reales que hubo que sortear (verificado con datos en vivo)

1. **Interstitial de consentimiento de la UE**: para tráfico que Google trata
   como europeo, la petición normal recibe la página de "aceptar cookies" de
   `consent.google.com` en vez de resultados. `providers/google_flights.py`
   fija una cookie `SOCS` de consentimiento antes de la petición (workaround
   conocido, [issue #46](https://github.com/AWeirdDev/flights/issues/46) del
   proyecto, cerrado por el autor como "no planeado" — nunca se integró en la
   librería, así que se aplica aquí).
2. **El modo `round-trip` no da vuelta combinada**: comprobado contra Google
   Flights en vivo (MAD→BCN): pedir `trip="round-trip"` con las dos fechas
   devuelve **solo opciones de ida**, nunca la vuelta — limitación conocida y
   sin arreglar en la librería. Por eso cada combinación de fechas se busca
   como **dos búsquedas `one-way` independientes** (ida y vuelta), y se cruzan
   localmente las `GOOGLE_FLIGHTS_TOP_OPTIONS_PER_LEG` opciones más baratas de
   cada una. El precio final es la **suma de dos tarifas one-way**, que
   aproxima pero no garantiza ser igual a la tarifa combinada real que
   ofrecería la aerolínea en un billete de ida y vuelta.

### Alternativas ya integradas si `fast-flights` deja de servirte

- **Duffel** (`FLIGHT_PROVIDER=duffel`, `providers/duffel.py`): oficial,
  alta instantánea, pero en modo real cobra por uso (~0,005 $/búsqueda,
  gratis hasta un ratio de 1500 búsquedas por reserva). Requiere pasar
  verificación KYC vía Stripe para pasar de sandbox (datos simulados) a
  modo live (datos reales). Instrucciones: https://app.duffel.com/join
- **Kiwi Tequila** (`FLIGHT_PROVIDER=kiwi`, `providers/kiwi.py`): el más
  completo funcionalmente (rango de fechas + franjas horarias en una sola
  llamada, sin necesidad de la rejilla de fechas que usan los otros dos),
  pero solo si consigues acceso de partner — https://tequila.kiwi.com

### Por qué la búsqueda funciona por "rejilla de fechas"

Ni `fast-flights` ni Duffel aceptan un rango de fechas o una franja horaria
como fecha "flexible" a nivel de búsqueda — cada búsqueda es una fecha exacta
de ida y una de vuelta (aunque sí aceptan franja horaria por tramo, y eso sí
se envía nativamente). Como no hay ningún endpoint gratuito de "precio más
barato por fecha" (el de Amadeus murió con el resto del self-service), este
proyecto genera él mismo la rejilla de combinaciones (`providers/date_grid.py`):

1. Enumera todos los pares (fecha ida, fecha vuelta) válidos según tus rangos
   de fecha y duración mínima/máxima.
2. Los reparte entre los destinos a explorar y muestrea un subconjunto
   acotado por `GOOGLE_FLIGHTS_MAX_TOTAL_SEARCHES` (40 por defecto), para que
   una búsqueda nunca dispare un número de peticiones descontrolado.
3. Lanza una búsqueda real por cada combinación muestreada (concurrente,
   limitada por `GOOGLE_FLIGHTS_MAX_CONCURRENCY`).

**Limitación honesta**: al ser una rejilla muestreada y no exhaustiva, con
rangos de fechas muy amplios es posible que alguna combinación válida no se
llegue a comprobar. Sube `GOOGLE_FLIGHTS_MAX_TOTAL_SEARCHES` si necesitas más
cobertura (a costa de más peticiones y más riesgo de bloqueo).

### Modo "cualquier destino"

No hay ningún endpoint gratuito de descubrimiento de destinos (el de Amadeus
también murió), así que cuando dejas el campo Destinos vacío, la app explora
una lista fija de ~24 destinos europeos populares
(`providers/regions.py::EUROPE_EXPLORATION_DESTINATIONS`), acorde a que tu
interés está sobre todo en Europa. Para cualquier otro destino, o para
acotar a menos destinos y obtener más combinaciones de fecha por cada uno,
escríbelos explícitamente en el campo Destinos.

## Estructura

```
backend/
  app/
    main.py                    # FastAPI app, CORS, manejo de errores
    config.py                  # Settings (variables de entorno)
    api/routes.py               # POST /api/search, GET /api/health, selección de provider
    schemas/search.py           # Modelos Pydantic de petición/respuesta
    schemas/watch.py            # Modelo reservado para vigilancia de precios (futuro)
    providers/base.py           # Interfaz FlightProvider
    providers/google_flights.py # Provider por defecto (fast-flights, gratis, no oficial)
    providers/duffel.py         # Provider alternativo (oficial, de pago en modo live)
    providers/kiwi.py           # Provider alternativo (requiere partner access)
    providers/date_grid.py      # Rejilla de fechas compartida (Duffel y Google Flights)
    providers/regions.py        # Shortlist de destinos europeos para el modo exploración
    services/search_engine.py   # Orquesta el provider y re-verifica filtros
frontend/
  index.html / style.css / app.js   # Formulario y tabla de resultados
docker-compose.yml
```

## Cómo funciona el filtrado

`SearchEngine` es quien tiene la última palabra: vuelve a comprobar fechas,
duración y franjas horarias sobre todo lo que devuelve el provider y ordena
por precio antes de devolver la respuesta — así el contrato de la API ("solo
combinaciones que cumplen, nunca todo sin filtrar") se cumple
independientemente de las particularidades de cada proveedor.

## Ejecutar en local (sin Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend: sirve `frontend/` con cualquier servidor estático, por ejemplo:

```bash
cd frontend
python -m http.server 8080
```

Como en local no hay proxy de nginx, `app.js` asume que `/api/search` está en
el mismo origen que la página; en desarrollo puedes lanzar el backend con
`--port 8080` y CORS abierto, o servir el frontend detrás de un proxy que
apunte `/api` a `http://localhost:8000`.

## Ejecutar con Docker

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend (interno, vía proxy de nginx en `/api`): no expuesto directamente

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `FLIGHT_PROVIDER` | `google` (por defecto, gratis/no oficial), `duffel` o `kiwi` |
| `GOOGLE_FLIGHTS_MAX_TOTAL_SEARCHES` | Nº máx. de búsquedas reales por cada petición a `/api/search` |
| `GOOGLE_FLIGHTS_MAX_CONCURRENCY` | Nº máx. de búsquedas simultáneas a Google Flights |
| `GOOGLE_FLIGHTS_PROXY` | Proxy opcional para las peticiones a Google Flights |
| `GOOGLE_FLIGHTS_TOP_OPTIONS_PER_LEG` | Nº de opciones más baratas por tramo (ida/vuelta) que se cruzan entre sí por cada fecha candidata |
| `DUFFEL_ACCESS_TOKEN` / `DUFFEL_BASE_URL` / `DUFFEL_VERSION` / `DUFFEL_MAX_TOTAL_SEARCHES` | Solo si `FLIGHT_PROVIDER=duffel` |
| `TEQUILA_API_KEY` / `TEQUILA_BASE_URL` | Solo si `FLIGHT_PROVIDER=kiwi` |
| `DEFAULT_CURRENCY` | Moneda por defecto |
| `ALLOWED_ORIGINS` | Orígenes permitidos por CORS, separados por coma |
| `REQUEST_TIMEOUT_SECONDS` | Timeout de las llamadas al proveedor (Duffel/Kiwi) |

## Extensibilidad futura

- **Nuevo proveedor**: implementa `FlightProvider.search()` en
  `backend/app/providers/` y añádelo a `build_provider()` en
  `api/routes.py`. `SearchEngine` no depende de ningún proveedor concreto.
- **Vigilancia de precios**: `backend/app/schemas/watch.py` ya define el
  modelo `SavedSearch` (búsqueda guardada + mejor precio visto). Falta por
  hacer: persistencia (tabla/DB), un scheduler que repita la búsqueda
  periódicamente, y el disparo de notificación (pensado para integrarse con
  Telegram/n8n, dado que ya tienes esa infraestructura corriendo).
