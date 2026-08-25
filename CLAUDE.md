# Finanzas — Seguimiento de cartera de inversión

> **Versión actual: 1.24.3** · **Tests: 626 en verde** · Aplicación web personal
> multiusuario para seguimiento de cartera de inversión (IBEX 35, Mercado
> Continuo, Nasdaq, ETFs, cripto, **fondos de inversión**). Inspiración
> funcional: snowball-analytics.

---

## Cómo usar este documento

CLAUDE.md se carga automáticamente al inicio de cada conversación. Está
diseñado para que un nuevo chat retome el proyecto sin contexto previo.

**Índice rápido — dónde mirar para…**

| Quiero… | Sección |
|---|---|
| Entender el stack y la arquitectura | [Stack](#stack) · [Capas](#capas-y-separación-de-responsabilidades) |
| No romper invariantes del proyecto | [Reglas de oro](#reglas-de-oro-no-romper) |
| Ver qué se ha hecho recientemente | `git log --oneline -30` y [CHANGELOG.md](CHANGELOG.md) |
| Saber qué funcionalidad hay hoy | [Funcionalidad actual](#funcionalidad-actual) |
| Saber el estado del repo (tests, routers) | [Estado actual](#estado-actual) |
| Entender un cálculo financiero | [Modelo de datos](#modelo-de-datos-sqlite) · [Splits](#splits--contrasplits-v140) · [Tramos IRPF](#tramos-irpf-configurables-v165) |
| Generar una nueva versión | [Metodología de release](#metodología-de-release) |
| Desplegar / actualizar VPS | [Despliegue](#despliegue-en-vps-con-https-caddy) |
| Escribir un test nuevo | [Patrones de tests](#patrones-de-tests) |
| Añadir un endpoint o feature | [Metodología de trabajo](#metodología-de-trabajo) |

---

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 (estilo declarativo `Mapped` /
  `mapped_column`) + Alembic (migraciones) + APScheduler (jobs nocturnos).
- **BD**: SQLite, fichero único, volumen persistente.
- **Datos de mercado**: yfinance, detrás de una capa de abstracción de
  proveedores (`providers/`). Tipos de cambio del BCE (multidivisa desde
  v1.8.0; divisas soportadas configurables por admin).
- **Frontend**: React + Vite, instalable como PWA. Responsive (escritorio y
  móvil). Gráficos con `recharts`.
- **Despliegue**: dos contenedores Docker (`finanzas` + `caddy`), volumen
  persistente para `finanzas.db` y los backups. Caddy gestiona HTTPS
  automáticamente con Let's Encrypt.

---

## Reglas de oro (NO romper)

### Cálculo y datos

1. **Dinero siempre en `Decimal`, nunca `float`.** La conversión a
   `Decimal` ocurre al leer de SQLite; la conversión a `str`/`float` ocurre
   solo en la frontera de la API o de presentación. En medio, exactitud
   absoluta.
2. **Todo se deriva de `transactions`.** El número de acciones, el precio
   medio y los beneficios NO se almacenan. Se calculan aplicando FIFO sobre
   las transacciones. Una posición está cerrada si tiene cero acciones vivas
   **o** si solo queda «polvo» (coste vivo < umbral configurable por admin,
   def. 0,10 — ver umbral de polvo en Capacidades).
3. **FIFO obligatorio** para valores homogéneos (norma española): las
   acciones vendidas son siempre las primeras compradas.
4. **No hardcodear nada que pueda cambiar**: nombre de la app, mercados,
   splits, tipos de cambio, tramos IRPF. Todo gestionable por admin y/o
   almacenado en la BD.

### Arquitectura

5. **Capa de cálculo pura.** `services/calculations.py`, `tax_report.py`,
   `returns.py`, `indicators.py` y `email_service.py` no importan SQLAlchemy,
   FastAPI ni nada de I/O de BD. La configuración (p. ej. `dust_threshold`)
   se inyecta como parámetro desde la API, nunca leyendo BD en `services/`.
6. **No mezclar responsabilidades**: repositorios para I/O puro, servicios
   para lógica pura, routers para HTTP.
7. **Distinguir modelos de BD y objetos de cálculo.** `TransactionRow` (BD) ≠
   `Transaction` (dataclass de cálculo). El repositorio traduce.
8. **El API REST es la única interfaz frontend↔backend.** No hay acceso
   directo a la BD desde el frontend.

### Calidad

9. **Verificar con tests** todo lo que tenga lógica no trivial. Cada test
   lleva en comentario la aritmética que justifica el resultado esperado.
10. **Escribir test antes de arreglar un bug.** No se arregla un bug sin un
    test que lo reproduzca y verifique la corrección.
11. **Explicar las decisiones de diseño antes de escribir el código.**
12. **Commits atómicos.** Cada commit es una unidad lógica completa con
    mensaje claro (qué y por qué). No mezclar cambios no relacionados.

### Frontend / UX

13. **Internacionalización obligatoria (ES/EN).** Todo texto visible se
    obtiene mediante `t('clave')` desde `AppContext`, **nunca hardcodeado**.
    Excepciones: nombres propios (Yahoo Ticker, ISIN, "EUR", "USD"). Al
    añadir cualquier texto se añaden simultáneamente ambas traducciones en
    `frontend/src/i18n/translations.js`.
14. **Versión visible en la UI** (sidebar, cabecera móvil, login). Se
    incrementa con cada release y se debe mostrar en interfaz.

### Operación

15. **Tras cada nueva versión generada, actualizar el changelog.** Mantener
    registro claro de cambios, mejoras y bugfixes. Después: número de
    versión en código, manual PDF, y zip de distribución.
16. **Mantener la seguridad en mente.** Proteger rutas autenticadas,
    validar entrada del usuario, manejar errores sin exponer detalles
    sensibles.

---

## Capas y separación de responsabilidades

```
┌─────────────┐   HTTP    ┌────────────┐    ┌─────────────────┐
│  Frontend   │ ←──────── │ api/       │ ─→ │ services/        │  (puro)
│  (React)    │           │ (routers)  │    │ - calculations   │
└─────────────┘           └────────────┘    │ - tax_report     │
                                │            │ - pdf_generator  │
                                ↓            └─────────────────┘
                          ┌────────────┐              ↑
                          │ repos/     │ ─────────────┘
                          │ (I/O puro) │  traduce TransactionRow → Transaction
                          └────────────┘
                                │
                                ↓
                          ┌────────────┐   ┌─────────────┐
                          │ models/    │ ← │ providers/  │  yfinance, BCE
                          │ (SQLAlch)  │   └─────────────┘
                          └────────────┘
```

- `repositories/` — I/O puro. No aplica FIFO, no decide nada fiscal, no
  redondea. Solo lectura para alimentar el cálculo.
- `repositories/tax_report_input.py` — orquestador: une repositorio +
  `compute_position` para producir el input de `build_tax_report`.
- `services/` — lógica pura, sin I/O.
- `api/` — routers FastAPI; única capa que conoce HTTP.

---

## Modelo de datos (SQLite)

**Tablas (21)**: `users`, `user_status_log`, `securities`, `security_splits`,
`markets`, `price_history`, `price_snapshots`, `ecb_rates`, `favorites`,
`positions`, `transactions`, `dividends`, `recurring_plans`, `app_config`,
`tax_brackets`, `push_subscriptions`, `subcarteras`, `subcartera_positions`,
`security_requests`, `user_notifications`, `catalog_messages`.

- **Multidivisa** (v1.8.0): `transactions`/`dividends` llevan `currency` y
  `exchange_rate` (tipo del BCE en la fecha; 1 para EUR). El BCE publica el tipo
  como "divisa por 1 EUR" → `euros = importe / rate`. Las divisas soportadas son
  configurables por admin (en `app_config`); `ecb_rates` tiene PK `(date, currency)`.
  Conversión por fecha: `repositories/exchange_rates.py` (`rate_on_date`,
  `latest_rate`).
- `markets.market_type` (`stock|fund|etf|crypto`) e `is_fund_market` segmentan el
  catálogo y habilitan el régimen de fondos (traspasos fiscalmente neutros).
- `transactions.type` ∈ `buy|sell|transfer_in|transfer_out`; las dos últimas son
  un traspaso de fondos acoplado por `transfer_group_id`.
- `recurring_plans`: aportaciones periódicas futuras (DCA) que ejecuta el scheduler.
- FKs con intención: `positions.security_id` es `ON DELETE RESTRICT` (no se
  borra un valor con histórico); el resto es `CASCADE`.
- `security_splits.security_id` es `ON DELETE CASCADE`.
- `user_status_log.actor_id` es `ON DELETE SET NULL`.
- SQLite NO aplica claves foráneas si no se activa `PRAGMA foreign_keys=ON`
  en cada conexión (se hace en el factory de Session).
- Esquema de referencia: `crear-tablas.sql`.

### Migraciones Alembic (cronológico)

1. `d61c248a5dfa` — initial_schema
2. `9b1c2b84199f` — add_is_admin_to_users
3. `a3f9c1d2e5b4` — v1.2.0 dynamic markets
4. `c7f9e2b4d8a1` — v1.3.0 user subscriptions + `app_config.app_name`
5. `b2d1a3c4e5f6` — v1.4.0 `security_splits`
6. `e3f1a2b4c5d6` — v1.5.0 market `sort_order`
7. `f1a2b3c4d5e6` — v1.6.5 `tax_brackets` (con seed: 19/21/23/27/28 %)
8. `a1b2c3d4e5f6` — v1.6.6 multicurrency (currency/exchange_rate en tx y dividendos)
9. `b2c3d4e5f6a1` — v1.6.7 `users.last_login`
10. `c3d4e5f6a1b2` — v1.6.9 `markets.yahoo_exchange`
11. `d4e5f6a1b2c3` — v1.7.0 `markets.is_fund_market`
12. `e5f6a1b2c3d4` — v1.7.0 tipos de transacción de traspaso
13. `f6a1b2c3d4e5` — v1.7.2 `transactions.transfer_group_id`
14. `a1b2c3d4e5f7` — v1.7.4 `recurring_plans`
15. `b2c3d4e5f7a8` — v1.7.6 `markets.market_type`
16. `c3d4e5f6a1b9` — v1.8.0 multidivisa (divisas configurables, `ecb_rates` PK `(date, currency)`)
17. `d5e6f7a8b9c1` — v1.9.11 `positions.target_buy_price` (**deprecada en v1.10.6**: el
    objetivo de compra vive en `favorites`; la columna se conserva pero no se usa)
18. `f7a8b9c0d1e2` — v1.10.0 `push_subscriptions` (notificaciones Web Push)
19. `b9c0d1e2f3a4` — v1.11.0 `subcarteras` + `subcartera_positions`
20. `c0d1e2f3a4b5` — v1.12.0 `security_requests` + `user_notifications` + `catalog_messages`
21. `d1e2f3a4b5c6` — v1.13.0 `catalog_messages`: añade `subject`, `admin_reply`, `admin_reply_at`
22. `e2f3a4b5c6d7` — v1.14.0 `users.email` (TEXT nullable, solo admins)
23. `f3a4b5c6d7e8` — v1.17.0 `price_snapshots.max_2y` + `max_5y` (rangos de precio 2/5 años)

---

## Convenciones de nombres importantes

- **Modelos SQLAlchemy** usan sufijo `Row` cuando hay confusión con el
  dataclass de cálculo: `TransactionRow`, `DividendRow`, `TaxBracketRow`,
  `MarketRow`. Mantener la distinción evita colisiones de import y deja
  claro qué es una fila de BD y qué es un objeto puro de cálculo.
- **El repositorio** traduce `TransactionRow` → `calculations.Transaction`.
  Es el puente entre la BD y la lógica.
- `SecuritySplit` (SQLAlchemy) vs `Split` (dataclass): misma distinción.
- Los `Decimal` se devuelven al JSON como **string** (por seguridad de
  precisión). En tests: `float(data["rate"]) == 19.0`, no `data["rate"] == 19.0`.

---

## Tipo `Money` (models/base.py)

`TypeDecorator` para columnas monetarias en SQLite:
- Al escribir: `Decimal` → `float` (lo único que SQLite entiende),
  validando que no entre un `float` crudo por accidente.
- Al leer: `float` → `Decimal(str(float))`, que elimina el ruido binario
  del `REAL` de SQLite.
- **Limitación**: el camino `Decimal → float → Decimal` no preserva los
  ceros finales (`100.10` se relee como `100.1`). Numéricamente exacto;
  solo se pierde la escala textual.

---

## Features detalladas

### Splits / contrasplits (v1.4.0)

- Tabla `security_splits`: `security_id`, `ex_date`, `ratio_num` (nuevas),
  `ratio_den` (antiguas), `notes`. Eventos globales gestionados por admin.
- `calculations.normalize_splits()` multiplica shares y divide price por
  el factor para todas las transacciones anteriores a `ex_date`. El coste
  total por lote se conserva (invariante).
- `PortfolioRepository.splits_for_security()` carga los splits; **todos
  los call-sites lo hacen** (portfolio abierto, cerrado, validaciones CRUD,
  tax_report_input, historial de cartera, analytics).
- El gráfico `/portfolio/history` normaliza también el `running_shares`
  para ser coherente con los precios split-adjusted de Yahoo.
- **Limitación conocida**: splits con ratios que producen decimales
  periódicos (ej. 3:2 aplicado dos veces) pueden dejar error de
  centésimas. Los tests usan `abs(valor - esperado) < 0.01`.

### Tramos IRPF configurables (v1.6.5)

- Tabla `tax_brackets`: `id`, `min_amount`, `max_amount` (NULL = sin techo),
  `rate`, `sort_order`. Editables por admin desde AdminPanel.
- Seed inicial: 0→6k 19 %, 6k→50k 21 %, 50k→200k 23 %, 200k→300k 27 %,
  >300k 28 % (vigentes 2023).
- `pdf_generator._build_tax_summary(report, brackets=None)`: si `brackets`
  es `None` usa `_BRACKETS` hardcodeado como fallback; si se pasa, usa
  esos. `api/reports.py` carga los tramos de la BD y los pasa.
- Colores del gráfico de tramos: gradiente verde→rojo por posición
  (`_bracket_color(i)`), no por valor concreto del rate.
- Endpoint público `GET /api/config/tax-brackets` (sin auth) para que el
  formulario de dividendos pueda leer el primer tramo para el botón
  "Aplicar -X %".

### Tipo de cambio automático (v1.6.5)

- `GET /api/markets/exchange-rate?date=YYYY-MM-DD`:
  1. Busca en `ecb_rates` el registro más reciente con `date <= pedida`.
  2. Si no hay, llama a `yf.Ticker("EURUSD=X").history(timeout=5)` (Yahoo).
  3. Si tampoco, devuelve `{rate: null, source: "not_found"}`.
- En el frontend, los formularios de transacción y dividendo auto-rellenan
  el campo `exchange_rate` cuando `currency=USD` y cambia la fecha. El
  campo queda editable para corrección manual.

### Hora real de Yahoo (v1.6.10)

- `LiveQuote.quote_time: str | None` — timestamp del último trade
  reportado por Yahoo, extraído del index del DataFrame de `history()`.
- El scheduler usa `quote.quote_time` (si está) en lugar de
  `datetime.now()` al guardar el snapshot. Así "Precios actualizados:"
  refleja la hora EN ORIGEN, no la del scheduler.

### Marca vs nombre de la app (v1.6.7)

- **"JSG Soft."** es el nombre del distribuidor, **hardcodeado** en el
  código (en defaults, manifest PWA, título del navegador).
- **Nombre de la aplicación** (ej. "JSG Portfolio") es **configurable por
  el admin** desde AdminPanel → Configuración. Se guarda en
  `app_config.app_name`. Aparece en sidebar, cabecera móvil y login.
- PWA instalado muestra "JSG Soft. - {app_name}" como título.

### PWA (v1.6.6)

- Configurado con `vite-plugin-pwa`. Manifest en `vite.config.js`.
- **Iconos imprescindibles**: `frontend/public/icons/icon-192.png` y
  `icon-512.png`. Sin ellos los navegadores no muestran el botón de
  instalación aunque VitePWA esté correctamente configurado. Hay tests en
  `test_distribution.py` que verifican que existen y son PNG válidos.

### Scatter plot de posiciones cerradas (v1.6.7+)

- `GET /portfolio/closed-analytics` añade `avg_days_held` (media ponderada
  por lote FIFO) y `pnl_pct` al `ClosedPositionSummary`.
- Color de cada punto: combina rentabilidad y tiempo (v1.6.12):
  - **Positivos**: rentabilidad anualizada (`pct/años`). Verde aceituna
    `#71732B` (3 %/año) → verde intenso `#16a34a` (60 %/año).
  - **Negativos**: intensidad `|pct| × (1 + años/3)`. Naranja `#D24608`
    (intensidad 5) → rojo oscuro `#7f1d1d` (intensidad 80+).
- Paletas separadas para evitar que una ganancia parezca pérdida.
- Toggle de escala X (lineal/logarítmica) para no perder visibilidad cuando
  hay outliers de tiempo.

### Dividendos por acción (v1.6.7+)

- `GET /portfolio/dividends-by-security` agrega todos los dividendos del
  usuario por valor (consolidando múltiples posiciones del mismo security).
- Campos: `count`, `months_held` (solo tiempo activo, ceil/30.44),
  `years_held`, `avg_yield_pct`, `avg_per_share`, `total_eur`,
  `yield_on_cost` (anualizado).
- Helper interno `_months_held_active(txs)`: itera transacciones ordenadas
  por fecha, suma solo días donde `shares > 0`. Si la posición sigue
  abierta, cuenta hasta hoy.
- Por cada dividendo, calcula el capital en esa fecha con
  `compute_position(txs_until_div_date)` → `avg_cost × shares_at_date`.

### Capacidades añadidas v1.7–v1.18 (resumen + punteros)

> Las features pre-v1.7 anteriores siguen vigentes. Estas son las piezas
> posteriores agrupadas por tema, con sus punteros técnicos. El detalle
> versión a versión está en [CHANGELOG.md](CHANGELOG.md).

#### Cálculo y datos

- **Fondos y traspasos fiscalmente neutros** (v1.7.0): mercados con
  `is_fund_market`. Un traspaso = `transfer_out` (consume FIFO sin tributar) +
  `transfer_in` (hereda el coste como precio sintético en EUR), acoplados por
  `transfer_group_id`; la plusvalía se difiere hasta el reembolso. Lógica en
  `calculations.py` (`consumed_cost_fifo`). Endpoints
  `POST/PATCH/DELETE /api/portfolio/transfer[/{group_id}]`; la edición
  (v1.10.7) recalcula el coste heredado y valida FIFO en origen y destino;
  el historial incluye `TransactionOut.transfer_partner_shares`.
- **Multidivisa** (v1.8.0): divisas configurables por admin. Conversión a EUR
  con el tipo del BCE de cada fecha (`repositories/exchange_rates.py`:
  `rate_on_date`, `latest_rate`). **Alta de divisas con buscador** (v1.20.0):
  el AdminPanel usa un autocompletado sobre el conjunto cerrado de divisas del
  BCE (`ECB_CURRENCIES` en `providers/ecb.py`, **fuente única de verdad**);
  `PATCH /admin/config/currencies` valida contra esa lista (422 si el BCE no la
  publica) y, al añadir una divisa nueva, dispara `update_ecb_rates` en segundo
  plano (backfill idempotente). Endpoint `GET /admin/config/available-currencies`.
- **TIR (XIRR) y retornos por periodo (Modified Dietz)** (v1.8.4–1.8.5):
  `services/returns.py` (puro). `GET /api/portfolio/xirr` y `/period-returns`
  (YTD/1a/3a/total). **Los traspasos no son flujos de caja.**
- **Histórico de cartera** (v1.9.5/1.9.9): `_history_series` valora cada fecha
  con el último cierre conocido de cada valor (carry-forward) y el tipo de
  cambio **de esa fecha** (`rate_on_date`). Alimenta gráfico y retornos.
- **Umbral de «polvo»** (v1.10.2/1.10.4): `PositionResult.is_closed` también
  cierra la posición si el coste vivo cae bajo el umbral (residuos de
  redondeo). Configurable (`app_config.dust_threshold`, def. 0,10); se inyecta
  vía `get_dust_threshold(db)` → `compute_position(dust_threshold=…)` — la
  capa de cálculo sigue pura.
- **Rangos de precio 1/2/5 años** (v1.17.0–v1.18.1): `compute_ranges()` calcula
  min/max con cortes por fecha natural; `PriceSnapshot` guarda los 6 campos
  (migración 23ª añadió `max_2y`/`max_5y`). En `SecurityDetail`, el selector
  1A/2A/5A corta el gráfico **por fecha natural** (v1.18.1 — no por nº de
  filas: el histórico solo tiene ~252 sesiones/año) y muestra solo el par de
  tarjetas Mín./Máx. del rango activo. El estado guarda 5 años (`slice(-1825)`).

#### Cartera, catálogo y filtros

- **Segmentación por tipo de activo** (v1.7.6; radio desde v1.12.1): chips
  Todo/Acciones/Fondos/… con selección exclusiva; filtran cartera, gráficos y
  retornos (`?types=`).
- **Subcarteras** (v1.11.0): agrupaciones personalizadas de posiciones
  (muchos-a-muchos: `subcarteras` + `subcartera_positions`). Router
  `/api/subcarteras` (CRUD + `POST/DELETE /{id}/positions/{pos_id}`). Toggle
  «Por tipo / Por subcartera» (oculto si no hay subcarteras); las tablas
  filtran client-side y los gráficos server-side (`?position_ids=…`).
- **Aportaciones periódicas DCA** (v1.7.4): backfill de las pasadas + plan
  (`recurring_plans`) que ejecuta el scheduler para las futuras.
- **Importación**: CSV (`csv_import`) y Ghostfolio (`ghostfolio_import`).
- **Pipeline de ISINs en 2 pasadas** (v1.9.1/1.9.7): 1ª exacta (Yahoo por
  ticker), 2ª heurística por nombre en Business Insider
  (`providers/business_insider.py`), conservadora, sin colisionar con ISINs
  existentes, excluye cripto. **Búsqueda por ISIN** (v1.11.3) en todos los
  buscadores de productos; `PositionSummary.isin`.
- **Valores en moneda nativa** (v1.13.0): `PositionSummary` y
  `ClosedPositionSummary` añaden campos `*_native` + `currency`; SecurityDetail
  y filas de cartera muestran la divisa del valor. **Totales y fiscal en EUR.**
- **Selector de mercados visibles** (v1.18.0): ⚙ en Mercados abre un modal de
  checkboxes por tipo. Config en `localStorage('marketsConfig')` =
  `{hiddenMarkets: []}` (lista vacía = todo visible → los mercados nuevos del
  admin aparecen visibles por defecto). Si el mercado/tipo activo queda oculto
  al guardar, auto-salta al primer visible. Favoritos no se puede ocultar.
- **Subcarteras en el detalle de valor y navegación bidireccional** (v1.19.0):
  en la cabecera de `SecurityDetail`, entre el badge de mercado y el de divisa,
  aparecen chips clicables con las subcarteras que contienen la posición →
  navegan a Portfolio con esa subcartera activa (`location.state.subcartId`).
  El badge de mercado es también clicable → navega a Mercados con el tipo de
  producto correcto preseleccionado (`location.state.type`). Ambas páginas
  leen `location.state` solo al montar; si no hay estado, conservan su
  comportamiento por defecto.

#### Fiscal

- **Informe fiscal — fondos aparte** (v1.8.9–1.9.4): los reembolsos de fondos
  van en sección/indicador propio (PDF y home fiscal), separados de la venta
  de acciones; cada tarjeta muestra su cuota IRPF estimada. La base imponible
  agrega todo (base del ahorro). No modela la compensación cruzada del 25 % ni
  el arrastre de pérdidas de 4 años (se avisa en el propio informe).

#### Alertas, notificaciones y comunicación

- **Precios objetivo** (v1.9.11–v1.10.6): objetivo de compra =
  `favorites.target_buy_price` (**fuente única**); objetivo de venta =
  `positions.target_sell_price`. Campana de alertas en el menú con badge;
  indicador «Comprar»/«Vender» en la ficha. (`positions.target_buy_price`
  quedó deprecada en BD, sin uso en código desde v1.10.6.) **El objetivo de
  compra se puede fijar sin tener posición** (v1.20.5): la casilla aparece
  siempre en `SecurityDetail`; al fijarla se sigue el valor (auto-favorito) y
  guarda en `favorites`. El indicador «Comprar» de la cabecera ya no exige
  posición. El objetivo de venta sigue ofreciéndose solo con posición (vive en
  `positions`); las notas siguen ligadas a la posición.
- **Notificaciones push (Web Push)** (v1.10.0): claves VAPID auto-generadas en
  `app_config`; tabla `push_subscriptions`; router `api/push.py` (`/vapid-key`
  público). `check_push_alerts` (job de snapshots) envía **solo las alertas
  nuevas** por dispositivo (dedup con `last_notified_keys`) y borra
  suscripciones muertas (HTTP 410). SW propio `src/sw.js` (injectManifest).
  Requiere HTTPS; en iOS, PWA instalada. El título del push usa
  `get_app_name(db)` (v1.18.1).
- **Solicitudes de catálogo y mensajes** (v1.12.0–v1.13.2): los usuarios
  proponen valores (`GET /api/catalog/validate-ticker` → preview de Yahoo sin
  persistencia → `POST /api/catalog/requests`); el admin aprueba (crea el
  `Security`) o rechaza desde AdminPanel → Catálogo (badge con pending-count).
  Mensajes libres con `subject` auto-determinado por el origen; el admin
  responde **una sola vez** (`POST .../messages/{id}/reply`, 409 si repite) →
  notificación `message_reply` al usuario. La respuesta del usuario a una
  notificación incluye el contexto original (título + cuerpo). 3 tablas
  (`security_requests`, `user_notifications`, `catalog_messages`) y 3 routers
  (`/api/catalog`, `/api/admin/catalog`, `/api/notifications`).
- **Notificaciones personalizadas del admin** (v1.13.1):
  `POST /api/admin/notifications/send {user_id|null, title, body}`;
  `user_id=null` = broadcast a todos los usuarios activos.
- **Email para administradores** (v1.14.0): `users.email` (nullable, migración
  22ª); los admins con email reciben copia de solicitudes, mensajes y
  respuestas. Proveedores: Gmail/Outlook/SMTP genérico/SendGrid/Mailgun.
  Config en `app_config["email_config"]`; secretos enmascarados como `"***"`
  en la API (el PATCH conserva el valor guardado si recibe `"***"`). Servicio
  puro `email_service.py` + orquestador `email_notifications.py` (incluye
  `notify_admins_inapp`, que **no hace commit** — responsabilidad del caller,
  y `get_app_name(db)` para los sujetos).
- **Caducidad de cuenta y renovación** (v1.15.0–v1.16.0): el job nocturno
  `check_expired_users` desactiva caducados y notifica a los admins (in-app +
  email). Login caducado → `detail="account_expired"`.
  `POST /api/auth/request-renewal` (sin auth, idempotente, siempre 200): crea
  notificación + `CatalogMessageRow` visible en AdminPanel → Usuarios →
  Mensajes. **`db.commit()` siempre antes de enviar email** (ver Lecciones
  críticas).

#### Operación y UX

- **Jobs en segundo plano con polling** (patrón clave): las operaciones largas
  que darían timeout en el VPS («Failed to fetch») se lanzan en un hilo →
  202 + endpoint `.../status`. Lo usan forzar histórico y rellenar ISINs
  (este último con **commit incremental**: lo hecho persiste aunque se corte).
- **Ordenación de tablas + buscador** (v1.10.3): hook `useSortableData` +
  `SortableHead` (3 estados asc/desc/defecto, nulos al final). **Los hooks van
  SIEMPRE antes de los `return` de carga/error** (ver Lecciones críticas).
- **Error Boundary global** (v1.10.6): un error de runtime muestra un mensaje
  recuperable con el menú operativo, no pantalla negra.
- **Borrar cartera** (v1.10.0): Utilidades → exporta backup JSON y luego
  `DELETE /api/portfolio/reset` (conserva cuenta, favoritos y preferencias).
- **Backup completo para migración 1:1** (v1.22.0): el backup admin
  (`GET/POST /api/admin/backup/export|import`) pasa a formato **`admin_2`**.
  ⚠️ **«1:1» se refiere a la configuración y los datos del usuario, NO a los datos
  de mercado**: el export **no incluye `price_history`, `price_snapshots` ni
  `ecb_rates`** (tampoco `user_notifications`, `catalog_messages`,
  `push_subscriptions` ni `user_status_log`). Tras restaurar en otro servidor hay
  que **forzar el histórico** desde AdminPanel, o el gráfico de evolución sale mal
  en silencio — ver [Tras migrar de servidor](#tras-migrar-de-servidor). Además de usuarios, catálogo y
  carteras, exporta **`app_config`** (nombre, logo, divisas, umbral de polvo,
  intervalo de snapshots, **config de email y claves VAPID — secretos EN CLARO**,
  custodiar el fichero), **`tax_brackets`**, **`security_splits`** (por ticker) y
  **subcarteras** (por usuario, posiciones por ticker), más los campos de usuario
  que faltaban (`email`/`is_enabled`/`expires_at`/`created_at`/`last_login_at`).
  Import idempotente: app_config = upsert por clave; tax_brackets = replace-all;
  splits = upsert por (valor, ex_date); subcarteras = upsert por (usuario,
  nombre); usuarios existentes se **actualizan** (email/is_enabled/expires_at, no
  toca contraseña ni rol); movimientos aditivos. **Retrocompatible con `admin_1`**
  (las secciones nuevas son opcionales). Lógica en `services/backup.py`
  (`ADMIN_BACKUP_VERSION`, `build_admin_export`, `validate_admin_backup`,
  `AdminImportResult`) y `api/admin.py`. Alternativa cruda para migrar: copiar
  el fichero `finanzas.db` del volumen.
- **Aviso de gráfico incompleto** (`GET /api/portfolio/history/coverage`): el
  gráfico de evolución **no se cachea**, se recalcula entero en cada petición
  desde `price_history` + `ecb_rates`. Cuando esas tablas están incompletas la
  curva sale mal **en silencio**, y una posición sin cotizaciones **no vale
  cero: desaparece del total** (el `continue` de `_history_inputs`), dejando la
  curva por debajo del valor real. El endpoint expone `missing_history`
  (posiciones excluidas) y `missing_rates` (divisas sin tipos del BCE) y el
  frontend pinta un aviso sobre el gráfico. `_history_inputs` es **la única
  definición** del criterio de exclusión, compartida con `_history_series`:
  duplicarlo garantizaba que un día divergieran y el aviso mintiera.

### Tras migrar de servidor

El backup admin **no lleva datos de mercado**. Al restaurar en un servidor nuevo,
`price_history` y `ecb_rates` llegan **vacías** y el gráfico de evolución se
dibuja con lo poco que haya, sin avisar (de ahí el endpoint `coverage`). Pasos:

1. Restaurar el backup admin.
2. **AdminPanel → Reconstrucción completa (5 años)**
   (`POST /api/admin/force-history-update?full=true`). **Usar el modo completo, no
   el normal**: el normal arranca en la última fecha guardada de cada valor y solo
   descarga 5 años si la tabla está *totalmente vacía*. Si la migración dejó
   cotizaciones parciales —o el nocturno alcanzó a escribir algo antes de que
   miraras—, el modo normal **no rellena hacia atrás** y el hueco se queda para
   siempre. Ambos modos ejecutan además `update_snapshots` y `update_ecb_rates`.
   (Hasta la corrección de 2026-08 el botón no lanzaba `update_ecb_rates`, así que
   los tipos había que esperarlos al nocturno de las 6:30, con toda la serie en
   divisa distorsionada mientras tanto.)
3. Comprobar que el aviso del gráfico desaparece. Cubre los tres casos: sin
   cotizaciones (`missing_history`), **historial truncado** (`partial_history`) y
   divisas sin tipos del BCE (`missing_rates`).

**Límite**: el backfill baja **5 años** (`today - 5*365`, tanto para precios como
para tipos). Con movimientos anteriores, esa parte del gráfico no se recupera por
esta vía. La alternativa que sí lo conserva todo es **copiar el fichero
`finanzas.db`** del volumen en vez de usar el backup.

- **Dashboard — Movimientos del día** (v1.11.3): sección configurable con las
  mayores subidas/bajadas del día de las posiciones abiertas
  (`daily_change_eur`), 3 ó 5 por columna, sin llamada extra al backend.
- **Scatter de cerradas** incluye round-trips parciales de posiciones aún
  abiertas (`still_open`); **donut de distribución** top 8 + «Otros».
- **Auditorías de código** (v1.16.0 y v1.18.1): los incidentes encontrados y
  las reglas resultantes están en
  [Lecciones críticas](#lecciones-críticas-incidentes-reales-no-repetir).
- **Historial limitado a 5 años en el servidor** (v1.19.1): `GET /markets/{id}/history`
  filtra con `WHERE date >= hoy - 1825 días` en la consulta SQL. El frontend
  ya no necesita `slice(-1825)`.
- **Mercados sin valores ocultos en la UI** (v1.19.2): `GET /markets/list`
  filtra con EXISTS y solo devuelve mercados que tienen al menos un valor en
  el catálogo. Los mercados vacíos siguen visibles para el admin en
  `GET /api/admin/markets`.
- **Sección «Últimos movimientos» en Mi Cartera** (v1.21.0): tabla al final de
  Portfolio con compras, ventas y dividendos de todas las posiciones, de más
  reciente a más antiguo, **paginada de 10 en 10** (cliente) sobre un máximo de
  **50** que devuelve el backend. `GET /api/portfolio/movements?limit=N` (N≤50)
  fusiona el top-N de `transactions` (buy/sell, **sin traspasos**) y `dividends`
  (importe = neto bruto−retención) y reordena por fecha desc. Cada fila navega
  al detalle del valor. Solo frontend + un endpoint; sin migración.

---

## Funcionalidad actual

Qué puede hacer la app hoy (visión de producto, agrupada):

- **Catálogo dinámico** de mercados y valores (IBEX 35, Mercado Continuo,
  Nasdaq, ETFs, cripto y fondos) con buscador por ticker/nombre/ISIN, screener
  de Yahoo, importación por catálogo y divisas configurables. Cada usuario
  elige qué mercados ve (⚙, `localStorage`); los mercados sin valores no se
  muestran (filtro server-side desde v1.19.2). Los usuarios normales pueden
  solicitar el alta de productos (validación Yahoo + aprobación del admin).
- **Cartera por usuario**: compras/ventas (FIFO), dividendos con retención,
  splits, traspasos de fondos fiscalmente neutros (crear/editar/borrar) y
  aportaciones periódicas (DCA). Todo derivado de `transactions`.
- **Valoración y analítica**: snapshots en vivo + barrido nocturno (histórico
  y tipos BCE). B/P latente y realizado, dividendos, comisiones, TIR (XIRR),
  retornos por periodo, gráfico de evolución, donut de distribución, scatter
  rentabilidad/tiempo y dividendos por valor. Filtros por tipo de activo o
  por subcarteras personalizadas. Importes en la moneda nativa del valor;
  totales y fiscal siempre en EUR.
- **Detalle de valor**: gráfico histórico con selector 1A/2A/5A vinculado a
  las tarjetas Mín./Máx. del rango activo; precios objetivo de compra/venta
  con «% hasta obj.» e indicador «Comprar»/«Vender». Chips de subcarteras
  relacionadas clicables (→ Cartera con subcartera activa); badge de mercado
  clicable (→ Mercados con el tipo de producto preseleccionado).
- **Informe fiscal IRPF** (HTML→PDF): ganancias/pérdidas con regla de
  recompra, dividendos, sección de fondos aparte, tramos configurables y
  cuota estimada. Resumen del año en curso en la sección fiscal.
- **Importar/Exportar**: CSV, Ghostfolio y backup completo.
- **Alertas y comunicación**: campana en el menú (alertas de precio +
  notificaciones in-app), notificaciones Web Push al dispositivo (PWA),
  mensajes usuario↔admin con asunto y respuesta, notificaciones
  personalizadas/broadcast del admin, copia por email a admins
  (Gmail/Outlook/SMTP/SendGrid/Mailgun), aviso de caducidad de cuenta y
  solicitud de renovación desde el login.
- **Administración**: usuarios (suscripciones, email, bloqueo/caducidad),
  mercados (sincronizar divisa, rellenar ISINs), splits, tramos IRPF,
  configuración (nombre de app, logo, divisas, intervalo de snapshots, umbral
  de «polvo») y forzar histórico.
- **PWA** instalable, responsive, ES/EN, tema claro/oscuro, Error Boundary
  global, ordenación de tablas y buscadores en cartera. El usuario puede
  borrar su cartera (con backup previo automático).

---

## Estado actual

**v1.24.3 · 626 tests en verde** (pytest, SQLite en memoria). 23 migraciones
Alembic, 21 tablas. Desplegado en VPS Debian con Caddy + HTTPS
(`jsg-portfolio.com`). Caddy hace además de proxy inverso HTTPS para
`webmin.{$DOMAIN}` (host:10000, vía `host.docker.internal`) y
`portainer.{$DOMAIN}` (contenedor, vía red interna `portainer:9000`) — ver
[Despliegue](#despliegue-en-vps-con-https-caddy).

### Tests (ficheros)

Cálculo puro: `test_calculations.py`, `test_splits.py`, `test_tax_report.py`,
`test_tax_fiscal_window.py`, `test_returns.py` (XIRR/Modified Dietz),
`test_transfers.py` (traspasos). HTTP/integración: `test_api.py`,
`test_portfolio_analytics.py`, `test_portfolio_repository.py`,
`test_markets_admin.py`, `test_tax_brackets.py`, `test_multicurrency.py`,
`test_currencies.py`, `test_market_type.py`, `test_recurring.py`,
`test_isin_pipeline.py`, `test_csv_import.py`, `test_ghostfolio_import.py`,
`test_import_export_v178.py`, `test_v179.py`, `test_active_updates.py`,
`test_yahoo_explorer.py`, `test_catalog_import.py`, `test_user_subscriptions.py`,
`test_app_logo.py`, `test_indicators.py`, `test_backup_service.py`,
`test_backup_full.py` (v1.22.0: backup admin_2 — export incluye app_config/
tramos/splits/subcarteras/campos de usuario/secretos; restaura y sobrescribe
config; replace-all de tramos; idempotencia; retrocompat admin_1;
round-trip del logo con bytes/MIME idénticos).
`test_push.py` (VAPID, suscripciones, alertas push, dedup).
`test_subcarteras.py` (CRUD, scoping, muchos-a-muchos, 404/403, filtrado position_ids).
`test_security_requests.py` (solicitudes de catálogo: crear, aprobar, rechazar,
notificaciones, mensajes, protección auth/admin).
`test_user_notifications.py` (GET, PATCH read, DELETE, POST reply, aislamiento entre usuarios).
`test_v1130.py` (v1.13.0–v1.13.2: mensajes subject/pending-count/reply/notif message_reply,
campos nativos USD en PositionSummary, notificaciones personalizadas del admin).
`test_email.py` (v1.14.0: campo email en usuarios, config de email, test endpoint,
triggers en solicitudes/mensajes/reply — mock `app.api.admin_markets.send_email`).
`test_user_expiry.py` (v1.15.0–v1.16.0: login caducado → account_expired + notifs a admins,
POST /auth/request-renewal crea CatalogMessageRow + notif + email, idempotencia (doble llamada no duplica), job check_expired_users — mock `app.api.auth.notify_admins`).
`test_movements.py` (v1.21.0: GET /portfolio/movements — combina/ordena compras/ventas/dividendos,
importes, excluye traspasos, tope 50, limit>50 → 422, auth requerido).
`test_force_history.py` (botón «forzar histórico»: lanza las TRES tareas del
nocturno —incluida `update_ecb_rates`—, 403, 409 de concurrencia, error en `/status`).
`test_history_coverage.py` (`GET /portfolio/history/coverage`: posiciones sin
cotizaciones, divisas sin tipos del BCE, filtro por posición, y que el gráfico
efectivamente devuelve 1000 en vez de 2000 cuando una posición queda excluida).
`test_split_detect.py` (v1.24.3: detección de splits no registrados — contrasplit,
split normal, agregación multiusuario, y que un split ya registrado NO aparezca).
`test_history_queries.py` (el gráfico no debe hacer N+1: nº de consultas
**constante**, no proporcional al nº de posiciones; y `coverage` no puede costar
más que el propio gráfico).
Regresiones: `test_bugs.py` (cada bug = un test). Distribución:
`test_distribution.py` (coherencia zip/Dockerfile, iconos PWA, **BOM** en
`pyproject.toml`/`package.json`/`entrypoint.sh`, shebang y `cd` del entrypoint;
v1.23.0: `docker-compose.sin-caddy.yml` existe, no declara Caddy, publica el
puerto de `finanzas` y va en el zip; **v1.24.3: la versión del **bundle compilado** coincide con `package.json`, en disco y en el zip; v1.23.1: `entrypoint.sh` ejecuta
`alembic upgrade head` ANTES de uvicorn**, y Dockerfile + zip incluyen
`alembic.ini` y `alembic/versions/`).

### Routers y prefijos API

| Módulo            | Prefix          | Autenticación |
|-------------------|-----------------|---------------|
| app_config        | /api/config     | **ninguna** (público) |
| auth              | /api/auth       | ninguna/user  |
| admin             | /api/admin      | require_admin |
| admin_markets     | /api/admin      | require_admin |
| admin_splits      | /api/admin      | require_admin |
| securities        | /api/securities | user/admin    |
| markets           | /api/markets    | user          |
| portfolio         | /api/portfolio  | user          |
| favorites         | /api/favorites  | user          |
| reports           | /api/reports    | user          |
| backup            | /api/backup     | user          |
| csv_import        | /api/import     | user          |
| ghostfolio_import | /api/import     | user          |
| push              | /api/push       | ninguna(`/vapid-key`)/user |
| subcarteras       | /api/subcarteras | user          |
| catalog_requests  | /api/catalog    | user          |
| admin_catalog_requests | /api/admin/catalog | require_admin |
| notifications     | /api/notifications | user        |

### Endpoints especiales a recordar

- `GET /api/config` (público) `{app_name}` · `GET /api/config/tax-brackets` (público).
- `GET /api/markets/exchange-rate?date=YYYY-MM-DD` → `{rate, date, source}`
  (`source ∈ {ecb, yahoo, not_found}`).
- `GET /api/portfolio/history` · `/closed-analytics` (scatter, con `still_open`) ·
- `GET /api/portfolio/history/coverage` → `{missing_history, partial_history, missing_rates, ok}`
  — qué le falta al gráfico de evolución para ser fiable (aviso en la UI).
  `partial_history` = histórico **truncado** (empieza después de la primera compra,
  con tolerancia de 7 días); se repara solo con `?full=true`.
  `/dividends-by-security` · `/xirr` · `/period-returns` · `/by-security/{id}` y
  `/by-security/{id}/operations` (historial aunque esté cerrada).
- `GET /api/portfolio/movements?limit=N` (N≤50) — últimos movimientos (buy/sell +
  dividendos, sin traspasos) de toda la cartera, fecha desc. Para la sección
  «Últimos movimientos» de Portfolio (paginada 10/pág. en cliente).
- `POST /api/portfolio/transfer`, `PATCH /api/portfolio/transfer/{group_id}` (editar) y `DELETE /api/portfolio/transfer/{group_id}`.
- `DELETE /api/portfolio/reset` (borra la cartera del usuario; el frontend exporta
  backup antes). `PATCH /api/portfolio/{id}/target-sell`.
- `PATCH /api/favorites/{id}` `{target_buy_price}` (**fuente única** del objetivo de
  compra; NO existe `/portfolio/{id}/target-buy`, se eliminó en v1.10.6).
- `GET /api/push/vapid-key` (público) · `POST/DELETE /api/push/subscribe` (user).
- `GET /api/subcarteras` · `POST /api/subcarteras` · `PATCH /api/subcarteras/{id}` · `DELETE /api/subcarteras/{id}` · `POST/DELETE /api/subcarteras/{id}/positions/{pos_id}` (user).
- `GET /api/catalog/validate-ticker?ticker=XXX` — preview de Yahoo Finance (nombre, precio, divisa, in_catalog). Sin persistencia. User.
- `POST /api/catalog/requests` — crea solicitud de producto (user) → notificación request_pending.
- `POST /api/catalog/messages` — mensaje libre al admin (user).
- `GET /api/notifications` · `PATCH /api/notifications/{id}/read` · `DELETE /api/notifications/{id}` · `POST /api/notifications/{id}/reply` (user).
- `GET /api/admin/catalog/requests?req_status=pending|approved|rejected|all` · `GET /api/admin/catalog/requests/pending-count` (admin).
- `PATCH /api/admin/catalog/requests/{id}/approve` body `{market_id, notes?}` — aprueba y crea el Security.
- `PATCH /api/admin/catalog/requests/{id}/reject` body `{notes?}` — rechaza.
- `GET /api/admin/catalog/messages` · `PATCH /api/admin/catalog/messages/{id}/resolve` (admin).
- `GET /api/admin/catalog/messages/pending-count` → `{"count": N}` (admin). **Registrar ANTES de las rutas `{message_id}`** para evitar conflictos de ruta.
- `POST /api/admin/catalog/messages/{id}/reply` body `{reply: str}` — respuesta única del admin (409 si ya respondió), crea notificación `message_reply` al usuario (admin).
- `POST /api/admin/notifications/send` body `{user_id: int|null, title: str, body: str}` — notificación personalizada a usuario concreto o broadcast (`user_id=null`). Devuelve `{sent: N}`.
- `PATCH /api/admin/users/{id}/email` body `{email: str|null}` — actualiza o borra el email del usuario (admin). Solo relevante en práctica para admins.
- `GET /api/admin/config/email` — devuelve config de email con contraseña/api_key enmascaradas como `"***"` (404 si no hay config).
- `PATCH /api/admin/config/email` body `EmailConfigIn` — guarda en `app_config["email_config"]`; si contraseña/api_key llegan como `"***"`, se conserva el valor guardado.
- `POST /api/admin/config/email/test` — envía email de prueba al email del admin logueado (422 si sin email o sin config).
- `POST /api/auth/request-renewal` (sin auth) body `{username: str}` — usuario caducado solicita renovación; notifica a admins in-app + email; siempre 200.
- `GET /api/portfolio/history`, `/xirr`, `/period-returns` aceptan `?position_ids=id1,id2,…` como alternativa a `?types=…` para filtrar por subcartera.
- `GET /api/admin/config` (incluye `dust_threshold`, `email_configured`, `email_provider`) · `PATCH
  /api/admin/config/dust-threshold` (admin) · `PATCH /api/admin/config/snapshot-interval`.
- `GET /api/admin/splits/detect` (admin) — splits/contrasplits NO registrados,
  detectados comparando el precio pagado con el cierre de ese día en las carteras
  de **todos** los usuarios. Devuelve `{detected: [{ticker, factor, users,
  suggested_ratio_num, suggested_ratio_den, samples}]}`. Compara precios ya
  normalizados con `normalize_splits`: lo que está bien dado de alta no aparece.
- `POST /api/markets/refresh-all` (admin) · `POST /api/admin/force-history-update`
  (+ `/status`; **`?full=true`** = reconstrucción completa: ignora lo guardado y baja
  5 años. Sin él, cada valor arranca en su última fecha almacenada y **nunca rellena
  hacia atrás**, así que un histórico truncado no se repara) · `POST /api/admin/markets/{code}/sync-currency` (admin) ·
  `POST /api/admin/securities/fill-isins` (+ `/status`, job en segundo plano).

### Limitaciones conocidas

- **Splits con ratios periódicos** (ej. 3:2 doble) pueden producir error de
  centésimas. Irrelevante; los tests usan tolerancia `< 0.01`.
- **Money** no preserva ceros finales (`100.10 → 100.1`). Aritmética exacta,
  solo escala textual.
- **Informe fiscal**: la cuota es una estimación; no modela la compensación
  cruzada del 25 % ni el arrastre de pérdidas de 4 años (requeriría histórico
  fiable de ejercicios anteriores). Se avisa en el propio informe.
- **`positions.target_buy_price`**: columna deprecada (v1.10.6), conservada en BD
  pero sin uso. El objetivo de compra vive en `favorites`.
- **Sin tests de frontend**: no hay vitest/jest. Los errores de runtime de React
  (p. ej. orden de hooks) no se detectan con la suite; el **Error Boundary** es la
  mitigación. Verificar en navegador los cambios de UI con estado de carga.

---

## Sistema de roles y auth

- Columna `is_admin BOOLEAN NOT NULL DEFAULT 0` en `users`.
- Auth por cookie firmada (`itsdangerous`), password con bcrypt.
- Bloqueado manualmente (`is_enabled=False`) → 403 "Contactar con el
  administrador". Caducado (`expires_at` pasado) → 403 con
  `detail="account_expired"` (v1.15.0), que el Login distingue para ofrecer
  el botón «Solicitar renovación de acceso».
- Router `api/admin.py` con dependencia `require_admin` (403 si no es admin).
- Crear primer admin: `python -m app.scripts.create_user <user> <pass> --admin`
- Al arrancar, `_ensure_default_admin()` crea admin si
  `ADMIN_DEFAULT_USER` / `ADMIN_DEFAULT_PASSWORD` están en `.env`.

---

## Despliegue en VPS con HTTPS (Caddy)

- **2 contenedores**: `caddy` (puertos 80/443) + `finanzas` (puerto 8000
  interno, sin exponer al host).
- **Variante sin Caddy** (v1.23.0): el zip incluye `docker-compose.sin-caddy.yml`,
  que no declara `caddy` ni sus volúmenes y publica `8000:8000` de `finanzas` al
  host (acceso directo por HTTP o detrás de un proxy propio). Para usarla se
  renombra/borra el `docker-compose.yml` original y se renombra esta variante a
  `docker-compose.yml`. Verificada por `test_distribution.py`.
- Caddy obtiene y renueva certificados Let's Encrypt automáticamente.
- Dominio en `.env` mediante `DOMAIN`.
- Para pruebas locales sin dominio: `DOMAIN=localhost` (Caddy sirve HTTP).
- **Caddyfile parametrizado con `{$DOMAIN}` (v1.20.2)**: el del zip es
  funcional tal cual; **solo hay que tener `DOMAIN` en `.env`**, ya no es
  necesario restaurar un Caddyfile manual. Sirve la app más dos subdominios:
  ```
  {$DOMAIN} www.{$DOMAIN}       → reverse_proxy finanzas:8000
  webmin.{$DOMAIN}             → reverse_proxy https://host.docker.internal:10000
  portainer.{$DOMAIN}          → reverse_proxy portainer:9000   (red interna)
  ```
- **Webmin detrás de Caddy** (v1.20.2): corre en el **host** (puerto 10000),
  HTTPS con certificado autofirmado → `reverse_proxy https://host.docker.internal:10000`
  con `tls_insecure_skip_verify`. Caddy alcanza el host con
  `extra_hosts: ["host.docker.internal:host-gateway"]` (servicio `caddy` del
  `docker-compose.yml`). **Ajustes en el host (una vez, idempotentes)**:
  `redirect_ssl=1` en `/etc/webmin/miniserv.conf`;
  `referers=webmin.<dominio> host.docker.internal` y `tempdir=/var/webmin/tmp`
  (+ `mkdir -p /var/webmin/tmp`) en `/etc/webmin/config`; luego
  `systemctl restart webmin`. (Fallback al bucle de redirección:
  `trust_unknown_referers=1`.)
  - **Terminal de Webmin (WebSocket)** (v1.20.4): la consola web (Otros →
    Terminal) se queda en "CONNECTING…" por DOS motivos encadenados que hay que
    resolver JUNTOS. (1) Caddy no completa el upgrade del WS contra el upstream
    HTTPS (el WS sale "Finished"/0 B en vez de 101): hay que **forzar HTTP/1.1**
    con `versions 1.1` dentro de `transport http`, y añadir `header_up Host
    {host}` + `X-Forwarded-Proto https` + `X-Forwarded-Host {host}` (ya en el
    Caddyfile del repo). (2) Webmin rechaza el origen
    (`Invalid Websockets origin` en `/var/webmin/miniserv.error`): su lista de
    orígenes permitidos NO se alimenta de Host ni `referers`, solo de host:puerto
    interno, `X-Forwarded-*` (si `trust_real_ip=1`), `websocket_host` y
    `websocket_extra_origins`. Solución idempotente en el host:
    `echo 'websocket_extra_origins=https://webmin.<dominio>' >> /etc/webmin/miniserv.conf`
    + `systemctl restart webmin`. Verificar: F12 → Network → filtro Socket → WS
    en **101**, y `tail /var/webmin/miniserv.error` sin `Invalid Websockets
    origin` posterior.
- **Portainer detrás de Caddy** (v1.20.3): NO por `host.docker.internal:9443`
  (doble TLS lento + CSRF 2.20+ rechaza con "Forbidden - origin invalid" al
  recibir un Host interno). Se le habla por **HTTP al puerto interno 9000 vía la
  red de Caddy** reescribiendo el Host:
  ```
  reverse_proxy portainer:9000 {
      header_up Host {host}
      header_up X-Forwarded-Host {host}
      header_up X-Forwarded-Proto https
  }
  ```
  **Paso manual (una vez)**: Portainer es externo a este compose, así que hay que
  conectar su contenedor a la red de Caddy —
  `docker network connect <proyecto>_default portainer` (p. ej.
  `jsg-portfolio_default`)— para que Caddy lo resuelva por nombre.
- **Activación**: crear los **DNS A** de `webmin.*` y `portainer.*` apuntando al
  servidor. Tras verificar, conviene cerrar 10000/9443 en el firewall público.
- **Aplicar cambios del Caddyfile con `docker restart` del contenedor de Caddy,
  NO con `caddy reload`**: en la práctica el reload dice "valid configuration"
  pero no activa los cambios; solo el reinicio del contenedor los aplica.
  Si el CSRF de Portainer sigue fallando: `docker logs --tail 5 portainer` y
  comprobar que `host=` de la línea `csrf.go` es el dominio público, no
  `host.docker.internal` (cuidado con la hora si el VPS va en UTC).
- Si el Caddyfile real del VPS tuviera config extra propia, incorporarla al del
  repo en vez de mantener una copia divergente.

---

## Metodología de trabajo

Esta sección es **operacional**: cómo hacer cambios y releases sin saltarse pasos.

### Flujo de trabajo típico para una nueva feature

1. **Explorar primero, escribir después.** Usar la herramienta Explore
   (agente) para encontrar el código relevante antes de proponer cambios.
2. **Cuando la tarea es no trivial**: entrar en plan mode, escribir el plan
   en `~/.claude/plans/`, validarlo con el usuario antes de tocar nada.
3. **Preguntar las dudas ANTES de implementar**, no después. Si hay
   ambigüedad sobre el cálculo (qué fecha usar, qué pondera, etc.),
   `AskUserQuestion` con opciones concretas.
4. **Implementación**:
   - Backend primero (modelos → schemas → migración → repos → services → API).
   - Frontend después (componentes → traducciones ES+EN).
   - Tests al final pero antes del commit.
5. **Commits atómicos por funcionalidad**, no por fichero. Mensaje
   explicando el "por qué".
6. **Tests siempre en verde antes del commit**:
   `cd backend && .\venv\Scripts\python.exe -m pytest tests\ -q`

### Metodología de release

> **Esta secuencia es OBLIGATORIA**. Saltarse el `npm run build` deja el
> `frontend/dist/` desactualizado y el usuario despliega una versión donde
> los cambios no se ven aunque el código esté correcto.

```
1. Bump versión en 4 ficheros (sed)
2. Actualizar CHANGELOG.md con la nueva entrada
   + bloque «Entorno de construcción» (ver abajo)   ← permite rollback informado
3. pytest — todo en verde
4. cd frontend && npm run build       ← IMPRESCINDIBLE, y DESPUÉS del paso 1
5. python gen_instrucciones.py        (regenera PDF)
6. printf '#!/bin/sh\n...' > entrypoint.sh   ← debe empezar 0x23 0x21
7. Generar zip (script Python al final de este documento)
8. git add ... && git commit con resumen claro
```

#### Registrar el entorno de construcción (paso 2)

Las dependencias se declaran con **mínimos abiertos** (`>=`) y **no hay
lockfile**: el `pip install --no-cache-dir .` del Dockerfile resuelve *las
versiones que existan el día del build*, no las del día en que la versión se dio
por buena. Consecuencia práctica: **volver a un zip antiguo no reproduce aquel
despliegue** — instala código viejo sobre dependencias nuevas, una combinación
que nunca se probó. Por lo mismo, el servidor de pruebas y el de producción
pueden acabar con imágenes distintas si se construyen en fechas distintas.

Mantener los mínimos abiertos es deliberado (los parches de seguridad de
`cryptography`, `requests` y `urllib3` siguen llegando solos), así que la
mitigación es barata: pegar en la entrada del CHANGELOG las versiones con las
que se verificó la release.

```bash
cd backend && ./venv/Scripts/python.exe -c "import importlib.metadata as md; print(chr(10).join(f'{n}=={md.version(n)}' for n in ['fastapi','uvicorn','sqlalchemy','alembic','pydantic-settings','yfinance','httpx','apscheduler','bcrypt','itsdangerous','jinja2','pywebpush','cryptography','pandas','numpy','starlette','pydantic','requests','urllib3']))"
```

`yfinance` es la **única dependencia con techo** (`>=1.6,<2.0`): rompe su API
entre majors y es la única cuya integración real no cubren los tests, que la
mockean — una suite en verde no dice nada sobre ella. Subir ese techo es una
decisión deliberada que exige probar contra Yahoo, nunca un `sed` de rutina.

#### Numeración de versiones

- **Patch (tercera cifra)** por defecto, para fixes/ajustes: 1.9.9 → 1.9.10 →
  1.9.11 (la tercera cifra puede pasar de 9; no se reinicia).
- **Minor (segunda cifra)** solo si hay **funcionalidad nueva**: 1.10.0, 1.11.0…
- **NO saltar a 2.0.0** sin que el usuario lo pida explícitamente.

#### Bump de versión (4 ficheros)

```bash
sed -i 's/version="X.Y.Z"/version="X.Y.W"/' backend/app/main.py
sed -i 's/"version": "X.Y.Z"/"version": "X.Y.W"/' frontend/package.json
sed -i 's/version = "X.Y.Z"/version = "X.Y.W"/' backend/pyproject.toml
sed -i 's/VERSION = "X.Y.Z"/VERSION = "X.Y.W"/' gen_instrucciones.py
```

#### Generación del zip

El zip contiene el frontend **precompilado** para que el Docker en VPS no
necesite Node ni acceso a npm.

**Excluir siempre**:
- `.git/`, `.claude/`
- `backend/venv/`, `backend/.venv/`, `frontend/node_modules/`
- `backend/finanzas.egg-info/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `htmlcov/`
- `backend/.env` (credenciales reales)
- `*.db`, `*.db-shm`, `*.db-wal`, `*.pyc`, `*.pyo`, `*.log`
- `CLAUDE.md`, `gen_instrucciones.py`
- `finanzas-vX.Y.Z.zip` (el propio zip)

**Incluir siempre**:
- `frontend/dist/` (precompilado — imprescindible)
- `frontend/src/`, `frontend/package*.json`, `frontend/vite.config.js`
- Todo `backend/app/`, `backend/alembic/`, `backend/tests/`
- `Dockerfile`, `docker-compose.yml`, `docker-compose.sin-caddy.yml` (variante sin
  Caddy, v1.23.0), `Caddyfile`, `entrypoint.sh`, `.dockerignore`
- `.env.example`, `instrucciones.pdf`, `CHANGELOG.md`, `README.md`
- `catalogo-valores.json`, `catalogo-etfs-completo.json`, `catalogo-crypto.json`

**Verificaciones obligatorias antes de commit**:
- `entrypoint.sh` en zip empieza con `0x23 0x21` (`#!`, sin BOM)
- No contiene `backend/.env`, `.claude/`, `CLAUDE.md`
- Contiene `frontend/dist/assets/*.js` con timestamp reciente
- Iconos PWA presentes en `frontend/dist/icons/`
- **Ninguna base de datos dentro** (ni por nombre ni por cabecera SQLite)
- **Tamaño en linea con la version anterior**: un salto de 944 KB a 5,4 MB es
  la señal de que se ha colado algo que no debia

#### Script de generación de zip

```python
# Ejecutar desde la raíz del proyecto
import zipfile, os

VERSION = "X.Y.Z"   # actualizar
zip_name = f"finanzas-v{VERSION}.zip"

EXCLUDE_DIRS = {'.git', '.claude', 'venv', '.venv', 'node_modules',
                'finanzas.egg-info', '__pycache__', '.pytest_cache',
                '.mypy_cache', 'htmlcov'}
EXCLUDE_FILES = {'backend/.env', 'CLAUDE.md', 'gen_instrucciones.py'}
EXCLUDE_EXT   = {'.pyc', '.pyo', '.log'}

def should_exclude(rel):
    parts = rel.split('/')
    if any(p in EXCLUDE_DIRS for p in parts): return True
    if rel in EXCLUDE_FILES: return True
    _, ext = os.path.splitext(rel)
    if ext in EXCLUDE_EXT: return True
    base = os.path.basename(rel)
    # CUALQUIER base de datos, con el sufijo que sea: .db, .db-shm, .db-wal y
    # tambien .db.bak-20260821-142941. Comparar splitext()[1] contra {'.db',...}
    # NO vale: para ese nombre devuelve '.bak-20260821-142941'.
    if '.db' in base: return True
    if base.startswith('finanzas-v') and base.endswith('.zip'): return True
    return False

count = 0
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS and not d.startswith('.')]
        for file in sorted(files):
            full = os.path.join(root, file)
            rel  = os.path.relpath(full, '.').replace(os.sep, '/')
            if should_exclude(rel): continue
            zf.write(full, rel); count += 1
print(f"ZIP: {zip_name}  ({count} ficheros)")
```

#### Dockerfile para distribución

El `Dockerfile` actual usa `frontend/dist/` precompilado directamente
(sin etapa Node). Correcto para el zip. **No añadir** la etapa
`FROM node:20-alpine` — solo sirve para CI/CD que compilan desde fuente.

### Despliegue en VPS — pasos

Para desplegar el zip en el VPS:
1. `docker compose down` (libera puertos, conserva volúmenes/BD)
2. Limpiar `/opt/jsg-portfolio/` excepto `.env`
3. Copiar y descomprimir el nuevo zip
4. **Restaurar el Caddyfile real** con los dominios (`jsg-portfolio.com` etc.)
5. `docker compose up --build -d`
6. Verificar `docker compose logs caddy` busca "certificate obtained successfully"

---

## Patrones de tests

### Fixtures principales en `backend/tests/conftest.py`

- `engine` — SQLite en memoria con `foreign_keys=ON` y schema creado.
- `db` — Session limpia.
- `client` — TestClient sin sesión.
- `auth_client` — TestClient con sesión de usuario normal.
- `admin_client` — TestClient con sesión de admin.
- `test_user`, `test_admin` — usuarios insertados directamente.
- `seed_markets` — inserta IBEX/Continuo/Nasdaq.

### Patrón CRUD admin

```python
def test_admin_crea_X(admin_client):
    resp = admin_client.post("/api/admin/X", json={...})
    assert resp.status_code == 201
    data = resp.json()
    # Decimal vienen como string en JSON:
    assert float(data["rate"]) == 19.0   # NO data["rate"] == 19.0

def test_create_X_no_admin(auth_client):
    resp = auth_client.post("/api/admin/X", json={...})
    assert resp.status_code == 403
```

### Helpers comunes en `test_api.py`

```python
def _crear_security(client, ticker="SAN.MC"): ...
def _buy(client, pos_id, shares, price, d="2024-01-10", fee="0"): ...
def _sell(client, pos_id, shares, price, d="2024-06-01", fee="0"): ...
def _div(client, pos_id, shares, gross_per_share, d="..."): ...
```

### Test de regresión de bug

Cada bug arreglado se documenta en `test_bugs.py` con:
- Comentario explicando qué era el bug y por qué fallaba.
- El escenario mínimo que lo reproduce.
- Aritmética esperada en comentario.

---

## Frontend — convenciones y componentes clave

### Estructura

```
frontend/src/
├── pages/        — Dashboard, Markets, Portfolio, SecurityDetail, TaxReport, Utilities, AdminPanel, Login
├── components/   — PortfolioChartsPanel, SecurityTable, SecurityCard, Navigation, ErrorBoundary,
│                   AddProductModal (solicitar ticker), CatalogMessageModal (mensaje libre al admin)
├── hooks/        — useSortableData (orden de tablas), useMediaQuery
├── context/      — AuthContext (user, login, logout), AppContext (t, appName, theme, locale)
├── i18n/         — translations.js (ES+EN obligatorio)
├── api/          — client.js (fetch wrapper, dispara auth:logout en 401)
├── sw.js         — service worker propio (PWA injectManifest): push + notificationclick
└── styles/       — global.css (variables CSS, dark/light theme)
```

### Helpers reutilizables

- `tableScrollStyle(count)` (en `Portfolio.jsx` y `SecurityDetail.jsx`):
  devuelve `{maxHeight: 540, overflowY: 'auto'}` si `count > 10`.
- `fmtYearsMonths(months)` (en `Portfolio.jsx`): "X año(s) y Y mes(es)".
- `pnlColor(pct, days)` (en `PortfolioChartsPanel.jsx`): color del scatter
  combinando rentabilidad y tiempo.
- `useSortableData(items)` + `SortableHead` (en `hooks/useSortableData.jsx`):
  ordenación de tablas en cliente. **Las llamadas a este hook (y a cualquier otro)
  deben ir ANTES de los `return` de carga/error del componente** (ver Notas
  operativas: el bug de la pantalla negra v1.10.5).
- Cabeceras de tabla **sticky** por defecto (CSS `th { position: sticky }`).

### PortfolioChartsPanel.jsx

Exporta componentes individuales para que `Portfolio.jsx` pueda componer
layouts custom (no solo el panel completo):
- `DistributionChart` (donut top 8 + «Otros»), `GroupedDistributionChart` (por
  tipo/divisa), `PnLChart`, `HistoryChart`.
- `ClosedScatterChart` (con puntos `still_open`), `DividendBarChart`,
  `DividendScatterChart`.

### Permisos en UI

- `useAuth().user?.is_admin` para mostrar/ocultar controles solo-admin
  (ej. botón "Editar" en SecurityDetail solo aparece para admin).

### Toggles en gráficos

- Scatter `ClosedScatterChart` y `DividendScatterChart` tienen toggle
  "Eje X lineal / logarítmico" con el mismo estilo visual.
- En escala log, los datos con valor 0 en X se filtran para evitar log(0).

---

## Comandos

```powershell
# Tests (Windows con venv)
cd backend; .\venv\Scripts\python.exe -m pytest tests\ -v

# Tests rápido (silencioso)
cd backend; .\venv\Scripts\python.exe -m pytest tests\ -q

# Servidor de desarrollo backend
cd backend; .\venv\Scripts\uvicorn.exe app.main:app --reload --port 8000

# Dev server frontend
cd frontend; npm run dev

# Build frontend (obligatorio antes del zip)
cd frontend; npm run build

# Migraciones
cd backend; .\venv\Scripts\alembic.exe upgrade head
cd backend; .\venv\Scripts\alembic.exe revision --autogenerate -m "mensaje"

# Crear usuario / admin
cd backend; .\venv\Scripts\python.exe -m app.scripts.create_user <username> <password> [--admin]

# Generar manual PDF
python gen_instrucciones.py

# Docker (local con DOMAIN=localhost)
docker compose up --build
```

---

## Notas operativas (lecciones aprendidas)

- **Reinicio del servicio uvicorn en Windows**: verificar instancias
  fantasma con `tasklist | findstr python` antes y después del reinicio.
- **Tras tocar frontend, recompilar antes de hacer zip.** `npm run build`
  no es opcional, regenera `frontend/dist/`.
- **Commits inmediatos tras cada cambio funcional**, no acumular.
- **`entrypoint.sh` debe crearse con `printf` desde Bash**, nunca con
  editores Windows o `Set-Content` de PowerShell (añaden BOM).
- **Decimal en JSON viene como string** — en tests, convertir a `float`
  para comparar valores numéricos.
- **El test `test_distribution.py` verifica el zip más reciente**: ejecutar
  los tests *después* de generar el zip detecta problemas como iconos PWA
  faltantes o `entrypoint.sh` con BOM.

### Lecciones críticas (incidentes reales, NO repetir)

- **BOM rompe el despliegue.** `Set-Content -Encoding utf8` de PowerShell 5.1
  añade BOM (`0xEF BB BF`). Con BOM: `pyproject.toml` → `tomllib` falla → `pip
  install` aborta el build Docker; `package.json` → Vite falla; `entrypoint.sh` →
  el kernel no reconoce el shebang → crash-loop. **Para bump de versión y ficheros
  que lee otra herramienta, escribir SIN BOM**: con Python (`open(...,
  encoding='utf-8')`) o `[System.IO.File]::WriteAllText(path, text, (New-Object
  System.Text.UTF8Encoding $false))`. `entrypoint.sh` siempre con `printf` desde
  Bash. `test_distribution.py` ya verifica BOM en los tres; correrlo tras el zip.
- **`entrypoint.sh` DEBE ejecutar `alembic upgrade head` antes de uvicorn.** Las
  migraciones son la **única** vía de creación del esquema en producción (no hay
  `create_all()`; eso solo existe en `tests/conftest.py`). Al regenerar el fichero
  con `printf` en la v1.16.0 se perdió esa línea y nadie lo notó durante 7
  versiones: en el VPS el volumen ya tenía `finanzas.db` con las tablas creadas
  por versiones anteriores. Solo se manifestó en una **instalación nueva**
  (volumen vacío): SQLite abre un `.db` sin tablas y el `lifespan` falla en
  `_ensure_default_admin()` con `OperationalError: no such table: users` →
  `Application startup failed` → crash-loop. **Regla: al regenerar `entrypoint.sh`
  con `printf`, escribir SIEMPRE las 5 líneas completas** (shebang, `set -e`,
  `cd /app`, `alembic upgrade head`, `exec uvicorn`). `test_distribution.py` lo
  verifica desde v1.23.1. **Corolario**: los bugs que solo afectan a la
  instalación desde cero no se ven en el VPS de producción; probar el zip contra
  un volumen limpio antes de darlo por bueno.
- **`entrypoint.sh` hace `cd /app`, NO `/app/backend`.** El Dockerfile tiene
  `WORKDIR /app` y copia ahí. Una ruta incorrecta → crash-loop → Caddy 502.
  `test_distribution.py` verifica que el `cd` coincide con el `WORKDIR`.
- **Reglas de hooks de React (pantalla en negro).** Un hook (`useState`,
  `useEffect`, `useSortableData`, …) DESPUÉS de un `return` condicional de
  carga/error rompe la app: en el primer render no se ejecuta y al llegar los
  datos React lanza «Rendered more hooks than during the previous render» y
  desmonta TODO → pantalla negra. **Todos los hooks van ANTES de cualquier
  `return`**; usar arrays seguros (`positions || []`). El **Error Boundary** (v1.10.6)
  mitiga el síntoma, pero el orden correcto es la prevención. El build (`npm run
  build`) NO detecta esto: es runtime. **Verificar en navegador** los cambios de UI
  con estado de carga.
- **Capa de cálculo pura.** Para inyectar configuración (p. ej. `dust_threshold`)
  NO leer la BD dentro de `services/`: pasar el valor como parámetro desde la API
  (helper en repositorio). Ver `get_dust_threshold(db)` + `compute_position(...)`.
- **`p.id` no existe en las posiciones del API.** Los objetos devueltos por
  `/portfolio` (abierta y cerrada) usan `position_id`, NO `id`. Usar `p.id` en
  componentes React produce `undefined` silenciosamente: el `Set` colapsa toda la
  lista (el primer `undefined` queda marcado como visto y excluye el resto). La
  causa es difícil de depurar porque no hay error visible. Regla: **en componentes
  que reciben posiciones del API, usar siempre `p.position_id`** como clave,
  filtro y argumento de llamadas al backend.
- **`db.commit()` debe ir ANTES de cualquier llamada remota** (email, HTTP externo).
  El patrón `notify_admins_inapp → db.add → notify_admins → db.commit` dentro de un
  `try/except Exception` es silenciosamente destructivo: si `notify_admins` lanza
  (fallo SMTP, DNS, config), el `except` lo traga y `db.commit()` nunca ejecuta.
  SQLAlchemy hace rollback al cerrar la sesión → notificaciones y mensajes
  desaparecen aunque el endpoint devuelva 200. **Regla**: `db.commit()` justo después
  del último `db.add()`, antes de cualquier I/O externo. El email fallido es tolerable;
  la pérdida silenciosa de datos in-app no lo es. (Incidente detectado en auditoría
  v1.16.0; mismo patrón que v1.15.0 pero re-introducido al añadir `CatalogMessageRow`.)
- **`auth_client` y `admin_client` comparten la misma instancia `client`** (StaticPool).
  En pytest, si un test recibe ambas fixtures, el último login (adminuser) gana.
  Para tests que necesitan acciones de usuario Y admin: usar el mismo `client` con
  re-login explícito (`client.post("/api/auth/login", ...)`) y **no combinar
  `auth_client` + `admin_client` en el mismo test**. Al insertar mercados directamente
  en BD (sin HTTP), pasar siempre `created_at` explícito — el `server_default` de
  SQLAlchemy no se aplica en inserts ORM directos con SQLite en memoria.
- **Un dato incompleto no es lo mismo que un dato ausente, y el aviso tiene que
  distinguirlos.** El aviso del gráfico preguntaba «¿existe alguna cotización
  posterior a la primera compra?». Con compra en 2022 y cotizaciones desde 2026 la
  respuesta es *sí*: la posición entraba en el gráfico aportando valor solo desde
  2026, el tramo anterior quedaba hundido y **no saltaba ningún aviso**. Un
  detector que solo distingue «hay algo / no hay nada» da falsa tranquilidad
  justo en el caso que más se parece a la normalidad. **Regla**: cuando avises de
  datos que faltan, comprueba el **rango cubierto**, no la mera existencia. Y
  cuidado con el otro extremo: hace falta tolerancia (aquí 7 días naturales) o el
  aviso salta siempre y deja de leerse.
- **Un botón de «reparar» que solo actúa sobre el caso vacío no repara nada.**
  `update_price_history` arrancaba en la última fecha guardada de cada valor: solo
  bajaba 5 años si la tabla estaba *totalmente vacía*, así que un histórico
  truncado no tenía forma de arreglarse desde la interfaz. De ahí `full=true`.
  **Regla**: toda operación de recuperación necesita un modo que ignore el estado
  actual; si no, el estado corrupto es su propia coartada.
- **N+1 invisible: los tests tienen 3 filas, la cartera real tiene 27 posiciones
  y 214.193 cotizaciones.** «Mi cartera» llegó a **413 consultas y 1.256 ms** por
  carga sin que ningún test se quejara, porque con datos de juguete un N+1 no se
  nota. Las cuatro causas: `coverage` repetía el trabajo del gráfico, `pos.security`
  se resolvía en diferido (una consulta por posición), transacciones y dividendos
  se pedían por posición, y las cotizaciones se traían desde la primera compra
  **global** para descartarlas luego en Python (~29.500 filas traídas para usar
  11.800). Tras corregirlo: **29 consultas y 312 ms**. **Reglas**: (1) en cualquier
  bucle sobre posiciones, cargar de golpe con `selectinload` / `IN`, nunca consulta
  por elemento; (2) filtrar **en SQL**, no traer y descartar en Python — el coste
  no es el SQL (44 ms) sino deserializar lo que sobra (150 ms); (3) al añadir un
  endpoint que acompaña a otro, comprobar si repite su trabajo; (4) **medir sobre
  una copia de la BD real**, nunca sobre la de tests. `test_history_queries.py`
  fija el nº de consultas **constante**, no un tiempo (que dependería de la máquina).
- **Los datos de Yahoo pueden ser válidos y falsos a la vez.**
  `yf.Ticker("SAN.MC").isin` devuelve `CA05973U1057` — un ISIN canadiense
  perfectamente bien formado, pero de otra empresa (Santander es `ES0113900J37`).
  `_normalize_isin` solo valida la FORMA, así que no filtra nada de esto. La
  **pasada 1 de `fill-isins` lo escribía sin comprobar colisiones** (la pasada 2
  sí lo hacía), y como el worker nunca sobreescribe, el error quedaba fijado para
  siempre. En el catálogo local apareció **AAPL con el ISIN de Microsoft**.
  Corregido en 2026-08: ambas pasadas rechazan un ISIN que ya pertenezca a otro
  valor. **Regla**: ante un dato externo sin fuente de verdad, la colisión es la
  única señal disponible; preferir el hueco al dato incorrecto, porque el hueco
  es recuperable y el dato incorrecto no. **Ojo al auditar**: un ISIN duplicado
  NO siempre es error — un valor multi-listado lo comparte legítimamente
  (`SHELL.AS`/`SHEL.L`, `HSBA.L`/`0005.HK`, `SXR8.DE`/`CSPX.L`).
- **Una suite verde no dice nada de las integraciones que mockea.** Los 601 tests
  pasaban con `yfinance` 0.2.x y siguen pasando con 1.6.0 porque **todos** los
  tests que la tocan la mockean. El salto de major se detectó solo al ejercitar
  `YahooProvider` contra la red de verdad. Por eso `yfinance` es la **única
  dependencia con techo** (`>=1.6,<2.0`). Tras tocarla o tras un cambio de
  entorno, probar contra Yahoo: precios, batch, histórico e ISIN.
- **El backup admin NO lleva datos de mercado**, pese a llamarse «migración 1:1».
  No exporta `price_history`, `price_snapshots` ni `ecb_rates`. Al restaurar en
  otro servidor, el gráfico de evolución se dibuja con lo poco que haya y **no
  avisa**: una posición sin cotizaciones no vale cero, **desaparece del total**.
  Incidente real de 2026-08 («el gráfico se generó con discrepancias grandes»
  tras migrar). Ver [Tras migrar de servidor](#tras-migrar-de-servidor) y el
  endpoint `/history/coverage`. **Regla general**: cuando un cálculo descarta
  entradas por falta de datos, **exponer lo descartado**; un resultado incompleto
  y silencioso es peor que un error.
- **`frontend/dist/` está en `.gitignore` PERO con 12 ficheros trackeados a la
  fuerza.** Cada `npm run build` cambia el hash del bundle: el trackeado sale
  como borrado y el nuevo no entra solo, hace falta `git add -f`. Contradicción
  pendiente de resolver (o se trackea de verdad, o no se trackea y el zip lo toma
  del disco, como ya hace). Mientras siga así, **revisar `git status` tras cada
  build**.
- **El zip se distribuye: no puede llevar datos de usuarios.** Se coló
  `finanzas.db.bak-20260821-142941` —18 MB con la BD real: usuarios, hashes de
  contraseña, emails y carteras— y llegó a producción. El filtro comparaba
  `os.path.splitext(rel)[1]` contra `{'.db','.db-shm','.db-wal'}`, y para ese
  nombre `splitext` devuelve `.bak-20260821-142941`: no coincidía con nada.
  **`.gitignore` sí lo cubría** (`*.db.bak-*`), pero el script del zip no lee
  `.gitignore`, tiene sus propias reglas — dos listas de exclusión que hay que
  mantener en paralelo y que divergen en silencio. La única señal era el tamaño:
  944 KB → 5,4 MB. **Reglas**: excluir por `'.db' in basename`, no por extensión;
  comprobar el zip por cabecera mágica además de por nombre; y mirar el tamaño
  contra la release anterior. Cubierto desde la v1.24.3 en `test_distribution.py`.
- **El `npm run build` va DESPUÉS del bump de versión, no antes.** La versión que
  se ve en el login y en el menú **no se lee de `package.json` en ejecución**:
  `Login.jsx` y `Navigation.jsx` hacen `import { version } from '../../package.json'`
  y Vite lo resuelve en tiempo de compilación, incrustándolo como literal en el
  bundle. Compilar antes de subir la versión produce un zip que pasa **todas** las
  verificaciones —el `package.json` que lleva dentro es el correcto— y una
  aplicación desplegada que muestra la versión anterior. Pasó en la v1.24.3 y se
  perdió un despliegue buscándolo en la caché del navegador y en el service worker
  de la PWA, que es donde parece estar. **Diagnóstico rápido**: si el backend
  responde la versión nueva (`docker exec … python -c "from app.main import app;
  print(app.version)"`) y la interfaz muestra la vieja, es el bundle, no la caché.
  Desde la v1.24.3 lo cubren dos tests en `test_distribution.py`.
- **`auto_adjust=False` NO evita el ajuste por splits: `price_history` está
  SIEMPRE split-ajustado.** `auto_adjust` solo gobierna el ajuste por
  **dividendos**; yfinance reescala la serie entera hacia atrás en cuanto hay un
  split. Comprobado contra yfinance 1.6 con el contrasplit 1:25 de AMP.MC: el
  cierre devuelto es idéntico con `True` y con `False`. El código creía lo
  contrario y lo tenía documentado como tal. Consecuencias: (1) el número de
  acciones debe estar en unidades **post-split en toda la serie** — para eso está
  `normalize_splits`, que normaliza las transacciones **anteriores** a la
  `ex_date`; (2) **un split no registrado en `security_splits` deforma la
  valoración por su factor**, y `/history/coverage` no puede verlo, porque no es
  un dato que falte sino un dato incoherente: la curva sale completa y creíble.
  De ahí `GET /admin/splits/detect`. **Regla**: al dar de alta un valor con
  historia larga, comprobar si tiene splits; y ante un gráfico raro, comparar el
  precio pagado con el cierre de ese día antes de buscar en otro sitio.
- **Un test que fabrica datos que el proveedor real nunca produce no cubre
  nada.** `test_history_split_no_infla_valor_pre_split` daba VERDE con el bug de
  splits vivo porque insertaba a mano un cierre pre-split *sin ajustar*. Los 614
  tests estaban en verde y el fallo llevaba en producción desde que existe la
  función. Es la lección de yfinance con una vuelta de tuerca: aquí ni siquiera
  hacía falta red para detectarlo, bastaba con que el test hubiera usado la
  convención real. **Regla**: al escribir un test sobre datos de un proveedor,
  verificar la convención contra el proveedor UNA vez y dejarlo escrito en el
  docstring.
- **httpx SUSTITUYE la query string cuando se le pasa `params`** (requests la
  fusiona). Un `?format=csvdata` dentro del literal de la URL se descartaba, el
  BCE respondía SDMX-ML en vez de CSV y el parser CSV devolvía `{}` **sin lanzar
  nada**. El job insertaba cero filas, hacía `commit()` y lo registraba como
  éxito: `ecb_rates` estuvo vacía indefinidamente y toda valoración en divisa
  caía a un tipo plano sacado de la última transacción (de cualquier usuario).
  **Dos reglas**: los parámetros de una petición van TODOS en `params`, nunca
  mezclados con el literal; y **una descarga vacía no es un éxito** — si el rango
  contiene días hábiles y vuelven cero registros, hay que avisar. Mismo patrón
  que el gráfico incompleto: el silencio es el fallo.
- **Las tarjetas (snapshot) y el gráfico (histórico) son rutas de datos
  INDEPENDIENTES.** El gráfico lee `price_history` de la BD; las tarjetas (precio,
  variación, Mín./Máx.) leen `price_snapshots`, que solo se escribe si
  `fetch_live_quote` tiene éxito. Pueden divergir: un valor puede tener gráfico y
  NO tarjetas. **Valores muy ilíquidos del Continuo (p. ej. NXTE.XD) tienen un
  único cierre en Yahoo, no una serie diaria** (`period="5d"` y `"1mo"` devuelven
  1 fila). `fetch_live_quote`/`fetch_live_quotes` NO deben exigir ≥2 cierres: con
  uno solo devuelven `last_price` y dejan `prev_close`/`daily_change_pct` en
  `None` (la UI muestra «—»), para que el snapshot se cree igualmente. Exigir 2
  lanzaba `ValueError`, el endpoint `refresh` daba 500 (que el front traga con
  `.catch`) y la ficha quedaba sin tarjetas, sin error visible. (Incidente
  v1.20.1; `LiveQuote.prev_close`/`daily_change_pct` son `Decimal | None`.)

---

## Protocolo de cierre de chat (OBLIGATORIO)

Cuando el usuario cierre un chat (o lo pida explícitamente), antes de terminar
**realizar siempre estas acciones** para que el próximo chat retome sin pérdida
de contexto y se mantenga la trayectoria del proyecto:

1. **CHANGELOG.md** — comprobar que está completo hasta la última versión
   generada (debería estarlo si se siguió la metodología de release).
2. **CLAUDE.md** — actualizar lo que haya cambiado de visión global:
   - Cabecera (versión actual, nº de tests) y sección [Estado actual](#estado-actual)
     (versión, nº de migraciones y de tablas).
   - [Migraciones Alembic](#migraciones-alembic-cronológico) y lista de **tablas**
     si se añadieron.
   - [Routers](#routers-y-prefijos-api) y [Endpoints especiales](#endpoints-especiales-a-recordar)
     si hay nuevos/eliminados.
   - [Capacidades v1.7–v1.18](#capacidades-añadidas-v17v118-resumen--punteros),
     [Funcionalidad actual](#funcionalidad-actual) y [Tests (ficheros)](#tests-ficheros).
   - **Limitaciones conocidas** y **Lecciones críticas** si surgió algo nuevo.
3. **Memoria persistente** (`~/.claude/.../memory/`): actualizar `MEMORY.md`,
   `project_state.md` (versión, capacidades, decisiones load-bearing) y
   `project_backlog.md` (marcar lo hecho, dejar lo pendiente). Registrar nuevas
   lecciones como `feedback_*` si aplican.
4. **Verificar** que la metodología de release se respetó en la última versión
   (bump en 4 ficheros, build, PDF, zip sin BOM, tests verdes, commit) y dejar el
   árbol git limpio (todo commiteado).

> El objetivo: que la información importante sobre requisitos, propiedades, flujos
> y trayectoria quede **patente en los registros** y no dependa de la memoria de
> un chat concreto.
