# Finanzas — Seguimiento de cartera de inversión

> **Versión actual: 1.17.1** · **Tests: 558 en verde** · Aplicación web personal
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
  proveedores (`providers/`). Tipos de cambio EUR/USD del BCE.
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
   las transacciones. Una posición cerrada es la que tiene cero acciones
   vivas.
3. **FIFO obligatorio** para valores homogéneos (norma española): las
   acciones vendidas son siempre las primeras compradas.
4. **No hardcodear nada que pueda cambiar**: nombre de la app, mercados,
   splits, tipos de cambio, tramos IRPF. Todo gestionable por admin y/o
   almacenado en la BD.

### Arquitectura

5. **Capa de cálculo pura.** `services/calculations.py` y
   `services/tax_report.py` no importan SQLAlchemy, FastAPI ni nada de I/O.
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
- `calculations._normalize_splits()` multiplica shares y divide price por
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

### Capacidades añadidas v1.7–v1.10 (resumen + punteros)

> Las anteriores siguen vigentes. Estas son las grandes piezas posteriores; el
> detalle versión a versión está en [CHANGELOG.md](CHANGELOG.md).

- **Fondos de inversión y traspasos fiscalmente neutros** (v1.7.0): mercados con
  `is_fund_market`. Un traspaso = `transfer_out` (consume sin tributar) +
  `transfer_in` (hereda el coste FIFO), acoplados por `transfer_group_id`. La
  plusvalía se difiere hasta el reembolso. Endpoints `POST/DELETE
  /api/portfolio/transfer`. Lógica en `calculations.py` (`consumed_cost_fifo`).
- **Multidivisa** (v1.8.0): divisas configurables por admin, no solo EUR/USD.
  Conversión a EUR con el tipo del BCE de cada fecha (`exchange_rates.py`).
- **Rentabilidad ponderada por dinero (TIR/XIRR) y por tiempo (Modified Dietz)**
  (v1.8.4–1.8.5): `services/returns.py` (puro). Endpoints
  `GET /api/portfolio/xirr` y `/period-returns` (YTD/1a/3a/total). Los traspasos
  no son flujos de caja.
- **Segmentación por tipo de activo** (v1.7.6, comportamiento radio desde v1.12.1): chips Todo/Acciones/Fondos/…
  con selección exclusiva (un solo tipo activo a la vez) que filtran cartera, gráficos y retornos (`?types=`).
- **Importación**: CSV de operaciones (`csv_import`) y Ghostfolio
  (`ghostfolio_import`).
- **Aportaciones periódicas (DCA)** (v1.7.4): backfill de las pasadas + plan
  (`recurring_plans`) que ejecuta el scheduler para las futuras.
- **Jobs en segundo plano con estado por polling** (patrón clave): operaciones
  largas que en el VPS darían timeout ("Failed to fetch") se lanzan en un hilo,
  devuelven 202 y exponen `.../status`. Lo usan **forzar histórico** y **rellenar
  ISINs**; el ISIN además hace **commit incremental** (lo hecho persiste aunque
  se corte).
- **Pipeline de ISINs en 2 pasadas** (v1.9.1/1.9.7): 1ª exacta (Yahoo por
  ticker), 2ª heurística por nombre en Business Insider
  (`providers/business_insider.py`), conservadora y sin colisionar con ISINs ya
  en BBDD; excluye cripto.
- **Informe fiscal — fondos aparte** (v1.8.9/1.9.2/1.9.4): los reembolsos de
  fondos van en su propia sección/indicador (PDF y home fiscal), separados de la
  venta de acciones; cada tarjeta de ganancia muestra su cuota IRPF estimada. La
  base imponible sigue agregando todo (base del ahorro). No modela compensación
  cruzada del 25 % ni arrastre de pérdidas de 4 años (se avisa en el informe).
- **Histórico de cartera correcto** (v1.9.5/1.9.9): `_history_series` valora cada
  fecha con el último cierre conocido de cada valor (carry-forward) y con el tipo
  de cambio **de esa fecha** (`rate_on_date`). Alimenta el gráfico y los retornos
  por periodo.
- **Scatter de operaciones cerradas** incluye round-trips parciales de posiciones
  aún abiertas (`still_open`). **Donut de distribución**: top 8 por volumen +
  «Otros».
- **Precios objetivo y alertas** (v1.9.11–1.9.16, 1.10.1): objetivo de **compra**
  (fuente única: `favorites.target_buy_price`, editable en lista de mercados y en
  el detalle) y objetivo de **venta** (`positions.target_sell_price`). El detalle
  muestra «% hasta obj.» junto a cada precio. Indicador parpadeante
  «Comprar»/«Vender» en la ficha. **Campana** de alertas en el menú (todas las
  secciones): badge con nº de alertas activas y popup clicable; se recalcula al
  navegar entre secciones. (El `target_buy_price` de `positions` quedó **muerto**
  y se eliminó del código en v1.10.6; la columna permanece en BD, deprecada.)
- **Notificaciones push (Web Push)** (v1.10.0): claves VAPID auto-generadas y
  guardadas en `app_config`; tabla `push_subscriptions`; router `api/push.py`
  (`/vapid-key` público, `/subscribe`, `/unsubscribe`). El job de snapshots llama
  `check_push_alerts`, que envía **solo las alertas nuevas** por dispositivo
  (dedup con `last_notified_keys`) y borra suscripciones muertas (HTTP 410).
  Service worker propio (`src/sw.js`, estrategia `injectManifest`) maneja `push` y
  `notificationclick`. UI de alta/baja en Utilidades. Requiere HTTPS (lo da Caddy)
  y, en iOS, PWA instalada.
- **Borrar datos de cartera** (v1.10.0/1.9.13): Utilidades → zona de peligro;
  exporta backup JSON y luego `DELETE /api/portfolio/reset` (borra posiciones,
  transacciones, dividendos y planes; conserva cuenta, favoritos y preferencias).
- **Umbral de «polvo»** (v1.10.2/1.10.4): `PositionResult.is_closed` cierra una
  posición si no quedan acciones vivas **o** si el coste de los lotes vivos cae por
  debajo de un umbral (descarta residuos de redondeo). El umbral es **configurable
  por admin** (`app_config.dust_threshold`, por defecto 0,10); se inyecta en
  `compute_position(dust_threshold=…)` desde la API vía `get_dust_threshold(db)`,
  manteniendo la **capa de cálculo pura**.
- **Ordenación de tablas + buscador** (v1.10.3): hook `useSortableData` +
  `SortableHead` (orden en cliente, 3 estados asc/desc/defecto, nulos al final, no
  persistente) en cartera abierta/cerrada, mercados/favoritos y tablas del detalle.
  Buscador por ticker/nombre en cartera abierta y cerrada. **Cuidado con las reglas
  de hooks**: estos hooks deben ir ANTES de cualquier `return` de carga/error (ver
  [Notas operativas](#notas-operativas-lecciones-aprendidas)).
- **Error Boundary global** (v1.10.6): envuelve el contenido; un error de runtime
  muestra un mensaje recuperable en vez de pantalla en negro, con el menú operativo.
- **Mejoras en la herramienta de traspasos** (v1.10.7): (1) **Edición** de un
  traspaso ya grabado (`PATCH /api/portfolio/transfer/{group_id}`): corrige
  shares, dest_shares y fecha sin deshacer; recalcula el coste heredado por FIFO
  y valida consistencia FIFO en origen y destino. El modal se abre pre-relleno;
  el fondo queda bloqueado. (2) **Buscador** en el selector de fondo destino:
  combobox filtrable por nombre, ticker o ISIN. (3) Columna renombrada «Base de
  coste (€)» / «Cost basis (€)» (antes «Coste heredado»). (4)
  `TransactionOut.transfer_partner_shares`: historial incluye las participaciones
  del lado opuesto del traspaso.
- **Subcarteras** (v1.11.0): agrupaciones personalizadas de posiciones (abiertas
  y cerradas) definidas por el usuario. Alternativa no acumulativa al filtro por
  tipo de activo. Tablas `subcarteras` + `subcartera_positions` (muchos-a-muchos).
  Router `/api/subcarteras` con CRUD + gestión de posiciones. Frontend: toggle
  «Por tipo / Por subcartera» (solo visible si hay subcarteras), chips de
  subcartera, filtrado client-side de tablas y server-side de gráficos
  (`?position_ids=…` en history/xirr/period-returns). Modal de gestión con
  editor de dos columnas (todas las posiciones / en la subcartera).
- **Búsqueda por ISIN** (v1.11.3): todos los buscadores de productos de inversión
  (catálogo de Mercados, cartera abierta/cerrada, editor de subcarteras) admiten
  el código ISIN además de ticker y nombre. `PositionSummary` incluye `isin`.
- **«Posiciones Abiertas - Movimientos del día» en Dashboard** (v1.11.3, título renombrado en v1.12.2): sección configurable
  `topperformers` habilitada por defecto. Dos columnas: mayores subidas y
  mayores bajadas del día (`daily_change_eur`). N por columna configurable
  (3 ó 5; defecto 5). Solo posiciones con snapshot del día. Sin llamada extra
  al backend; respeta el filtro de tipo.
- **Solicitudes de catálogo por usuarios** (v1.12.0): usuarios normales pueden
  proponer nuevos valores sin depender del admin directamente.
  - Hint al pie de Mercados (solo no-admin): «¿No encuentra el producto?» +
    botón «Agréguelo aquí» + «contacte con el administrador».
  - Modal `AddProductModal`: ticker → botón **Validar** (`GET /api/catalog/validate-ticker`,
    Yahoo Finance sin persistencia, preview con precio/divisa/exchange/in_catalog)
    → nombre auto-rellenado → selector de mercado → **Enviar solicitud**.
  - Modal `CatalogMessageModal`: texto libre → `POST /api/catalog/messages`.
  - **Campana extendida**: `GET /api/notifications` se suma a alertas de precio.
    Notificaciones de solicitud (`request_pending`, `request_approved`,
    `request_rejected`) con opciones **Entendido** (DELETE) y **Entendido +
    Dejar mensaje** (POST reply → crea `CatalogMessageRow` vinculado a la solicitud).
  - **AdminPanel — tab Catálogo**: badge parpadeante con count de pendientes
    (`GET /api/admin/catalog/requests/pending-count`). Sección **Solicitudes**:
    tabla filtrable por estado, modal de revisión donde el admin puede reasignar
    el mercado, añadir notas y aprobar/rechazar. Aprobar crea el `Security`.
    Sección **Mensajes de usuarios**: mensajes libres + respuestas post-resolución,
    botón «Marcar resuelto».
  - 3 tablas nuevas: `security_requests`, `user_notifications`, `catalog_messages`.
  - 3 routers nuevos: `/api/catalog` (user), `/api/admin/catalog` (admin),
    `/api/notifications` (user).
- **Mensajes con asunto + respuesta del admin** (v1.13.0): campo `subject` en
  `catalog_messages` (auto-determinado por el origen: "Mercados", etc.); admin puede
  responder una vez (`POST /admin/catalog/messages/{id}/reply`) → notificación
  `message_reply` al usuario en la campana. `GET /admin/catalog/messages/pending-count`
  para badge en tab Usuarios. Sección de mensajes movida de tab Catálogo → tab Usuarios.
  Migración `d1e2f3a4b5c6`.
- **Valores en moneda nativa** (v1.13.0): `PositionSummary` y `ClosedPositionSummary`
  incluyen `*_native` (cost, market_value, unrealized_pnl, dividends, realized_pnl,
  total_profit, fees, avg_cost) y `currency`. SecurityDetail y filas de cartera usan
  moneda nativa del valor (USD, GBP…); totales del portfolio y fiscal en EUR.
- **Notificaciones personalizadas del admin** (v1.13.1): `POST /api/admin/notifications/send`
  con `{user_id, title, body}`. `user_id=null` → broadcast a todos los usuarios activos.
  Crea `UserNotificationRow(type="admin_message")`. Componente `SendNotificationModal`.
  Tab Usuarios del AdminPanel: botón por fila + sección broadcast. Tabla de usuarios
  compactada a 3 columnas (Usuario, Actividad, Acciones).
- **Contexto en respuestas de usuario** (v1.13.2): `POST /notifications/{id}/reply`
  incluye el bloque de contexto de la notificación original en el `CatalogMessageRow`
  (título + cuerpo, separados visualmente). El campo `subject` se rellena con el título
  de la notificación automáticamente. Título campana: «Alertas de precio y notificaciones».
- **Notificaciones por email para administradores** (v1.14.0): campo `email` en usuarios
  (`users.email TEXT` nullable, migración 22ª). Los admins con email reciben una copia por
  correo de nuevas solicitudes de catálogo, mensajes de usuarios y respuestas. Proveedores:
  Gmail (SMTP + contraseña de app), Outlook, SMTP genérico, SendGrid y Mailgun. Config
  guardada en `app_config["email_config"]` (JSON), contraseñas enmascaradas en la API como
  `"***"`. Servicio puro `email_service.py` + orquestador `email_notifications.py`.
  AdminPanel — Herramientas: sección «Configuración de correo» con selector de proveedor y
  textos de ayuda. AdminPanel — Usuarios: email visible + botón ✉ por fila.
- **Notificaciones por caducidad y solicitud de renovación** (v1.15.0): cuando una cuenta
  de usuario normal caduca, los admins reciben notificación in-app (campana) y copia por
  email. El job nocturno `check_expired_users` detecta caducados proactivamente (sin esperar
  al login). Login con cuenta caducada devuelve `detail="account_expired"` distinguible del
  bloqueo manual. Nuevo endpoint `POST /api/auth/request-renewal` (sin auth): usuario
  caducado solicita renovación → notificación in-app + email a todos los admins. En el
  frontend, Login muestra mensaje específico + botón «Solicitar renovación de acceso».
  Nuevos tipos de notificación `user_expired` y `renewal_request` (solo «Entendido», sin
  botón de respuesta). Función `notify_admins_inapp` en `email_notifications.py`.
  La solicitud de renovación también crea un `CatalogMessageRow` visible en AdminPanel →
  Usuarios → «Mensajes de usuarios», donde el admin puede responder o resolver (v1.15.2).
  La campana refresca notificaciones al abrirse, no solo al navegar (v1.15.1).
- **Auditoría de código y correcciones críticas** (v1.16.0):
  - `db.commit()` movido antes de `notify_admins()` en `request_renewal` y
    `_notify_admins_user_expired`: antes un fallo de email descartaba
    silenciosamente notificaciones in-app y `CatalogMessageRow`.
  - `request_renewal` es idempotente: clics repetidos no crean mensajes
    duplicados en AdminPanel.
  - `Navigation.jsx`: split `loadAlerts` (completo, en navigate+intervalo) /
    `refreshNotifs` (solo `/notifications`, al abrir campana); guards
    `loadingRef`/`notifLoadingRef` evitan race conditions; `useEffect([open])`
    en `AlertBell`; `onClick` vuelve a forma funcional.
  - `email_notifications.py`: nueva función `get_app_name(db)` → sujetos de
    email usan el nombre configurable de la app en lugar de `"[Finanzas]"`.
- **Rangos de precio extendidos en detalle de valor** (v1.17.0/v1.17.1):
  - `PriceSnapshot` añade `max_2y` y `max_5y` (migración 23ª). `compute_ranges()`
    calcula min/max para 1, 2 y 5 años.
  - `SecurityDetail`: selector **1A / 2A / 5A** junto al título del gráfico.
    Al cambiar el rango: (1) el gráfico muestra el periodo seleccionado y (2)
    las tarjetas Mín./Máx. muestran solo el par correspondiente al rango activo.
    Histórico almacenado en estado ampliado a 5 años (`slice(-1825)`).

---

## Funcionalidad actual

Qué puede hacer la app hoy (visión de producto):

- **Catálogo dinámico** de mercados y valores (IBEX 35, Mercado Continuo, Nasdaq,
  ETFs, cripto y **fondos**), con buscador, screener de Yahoo e importación por
  catálogo. Divisas configurables.
- **Cartera por usuario**: compras/ventas (FIFO), dividendos (con retención),
  splits, **traspasos de fondos** y **aportaciones periódicas (DCA)**. Todo se
  deriva de `transactions`.
- **Valoración en vivo**: snapshots de precio (scheduler periódico) y barrido
  nocturno de histórico + tipos del BCE.
- **Analítica**: B/P latente y realizado, dividendos, comisiones, **TIR (XIRR)**,
  **retornos por periodo**, gráfico de evolución, distribución (donut top 8),
  scatter rentabilidad/tiempo, dividendos por valor.
- **Informe fiscal IRPF** (HTML→PDF): ganancias/pérdidas de acciones, regla de
  recompra, dividendos, **sección de fondos**, tramos configurables y cuota
  estimada. Más resumen del año en curso en la sección fiscal.
- **Importar/Exportar**: CSV, Ghostfolio y backup completo (admin).
- **Administración**: usuarios y suscripciones, mercados (incl. sincronizar
  divisa y rellenar ISINs), splits, tramos IRPF, configuración (nombre de app,
  logo, divisas, intervalo de snapshots, **umbral de cierre por «polvo»**),
  forzar histórico.
- **Precios objetivo y alertas**: objetivo de compra/venta por valor, campana de
  alertas en el menú y **notificaciones push** al dispositivo (PWA).
- **Subcarteras**: agrupaciones personalizadas de posiciones, alternativa al
  filtro por tipo. Editor de dos columnas para asignar/quitar posiciones.
  Toggle «Por tipo / Por subcartera» en Mi Cartera (oculto si no hay subcarteras).
- **Búsqueda por ISIN**: todos los buscadores de productos (Mercados, cartera,
  subcarteras) admiten ticker, nombre o ISIN.
- **Dashboard — «Posiciones Abiertas - Movimientos del día»**: sección configurable con las mayores
  subidas y bajadas del día de las posiciones abiertas (`daily_change_eur`).
- **Solicitudes de catálogo y mensajes**: usuarios normales proponen nuevos valores
  (validación Yahoo Finance, flujo aprobación/rechazo por el admin) y pueden enviar
  mensajes con **asunto** al admin; el admin puede responder → notificación en la
  campana. Tab Usuarios del AdminPanel incluye badge y sección de mensajes.
- **Valores en moneda nativa**: SecurityDetail y filas de cartera abierta/cerrada
  muestran los importes en la moneda propia del valor (USD, GBP…); totales y fiscal
  en EUR.
- **Notificaciones del admin**: el admin puede enviar notificaciones personalizadas
  (título + cuerpo) a un usuario concreto o a todos los activos (broadcast). Aparecen
  en la campana del destinatario. AdminPanel tab Usuarios: botón por fila + sección
  broadcast.
- **Email para administradores**: los admins con email configurado reciben copia por
  correo de eventos relevantes (nueva solicitud de catálogo, nuevo mensaje, respuesta de
  usuario). Proveedores: Gmail, Outlook, SMTP genérico, SendGrid, Mailgun. Configuración
  en AdminPanel → Herramientas → «Configuración de correo».
- **Notificaciones por caducidad y renovación**: cuando una cuenta caduca los admins
  reciben notificación in-app + email. El usuario caducado ve el motivo al login y puede
  pulsar «Solicitar renovación de acceso» para notificar al admin sin estar autenticado.
- **Rangos de precio en detalle de valor**: selector 1A/2A/5A vinculado al gráfico
  histórico y a las tarjetas Mín./Máx. — al cambiar el rango se muestra el gráfico
  del periodo y el par de tarjetas correspondiente (solo 2 tarjetas visibles a la vez).
- **PWA** instalable, responsive, ES/EN, tema claro/oscuro. **Error Boundary**
  global (un fallo de UI no deja la pantalla en negro).

---

## Estado actual

**v1.17.1 · 558 tests en verde** (pytest, SQLite en memoria). 23 migraciones
Alembic, 21 tablas. Desplegado en VPS Debian con Caddy + HTTPS
(`jsg-portfolio.com`).

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
Regresiones: `test_bugs.py` (cada bug = un test). Distribución:
`test_distribution.py` (coherencia zip/Dockerfile, iconos PWA, **BOM** en
`pyproject.toml`/`package.json`/`entrypoint.sh`, shebang y `cd` del entrypoint).

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
  `/dividends-by-security` · `/xirr` · `/period-returns` · `/by-security/{id}` y
  `/by-security/{id}/operations` (historial aunque esté cerrada).
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
- `POST /api/markets/refresh-all` (admin) · `POST /api/admin/force-history-update`
  (+ `/status`) · `POST /api/admin/markets/{code}/sync-currency` (admin) ·
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
- Bloqueado si `is_enabled=False` o `expires_at` pasado → 403
  "Contactar con el administrador".
- Router `api/admin.py` con dependencia `require_admin` (403 si no es admin).
- Crear primer admin: `python -m app.scripts.create_user <user> <pass> --admin`
- Al arrancar, `_ensure_default_admin()` crea admin si
  `ADMIN_DEFAULT_USER` / `ADMIN_DEFAULT_PASSWORD` están en `.env`.

---

## Despliegue en VPS con HTTPS (Caddy)

- **2 contenedores**: `caddy` (puertos 80/443) + `finanzas` (puerto 8000
  interno, sin exponer al host).
- Caddy obtiene y renueva certificados Let's Encrypt automáticamente.
- Dominio en `.env` mediante `DOMAIN`.
- Para pruebas locales sin dominio: `DOMAIN=localhost` (Caddy sirve HTTP).
- `Caddyfile` típico en VPS:
  ```
  jsg-portfolio.com www.jsg-portfolio.com {
      reverse_proxy finanzas:8000
  }
  ```
- **Importante**: tras descomprimir el zip en el VPS, restaurar el
  `Caddyfile` real (el del zip usa `{$DOMAIN}` genérico) antes del
  `docker compose up`.

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
3. pytest — todo en verde
4. cd frontend && npm run build       ← IMPRESCINDIBLE
5. python gen_instrucciones.py        (regenera PDF)
6. printf '#!/bin/sh\n...' > entrypoint.sh   ← debe empezar 0x23 0x21
7. Generar zip (script Python al final de este documento)
8. git add ... && git commit con resumen claro
```

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
- `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `entrypoint.sh`, `.dockerignore`
- `.env.example`, `instrucciones.pdf`, `CHANGELOG.md`, `README.md`
- `catalogo-valores.json`, `catalogo-etfs-completo.json`, `catalogo-crypto.json`

**Verificaciones obligatorias antes de commit**:
- `entrypoint.sh` en zip empieza con `0x23 0x21` (`#!`, sin BOM)
- No contiene `backend/.env`, `.claude/`, `CLAUDE.md`
- Contiene `frontend/dist/assets/*.js` con timestamp reciente
- Iconos PWA presentes en `frontend/dist/icons/`

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
EXCLUDE_EXT   = {'.pyc', '.pyo', '.log', '.db', '.db-shm', '.db-wal'}

def should_exclude(rel):
    parts = rel.split('/')
    if any(p in EXCLUDE_DIRS for p in parts): return True
    if rel in EXCLUDE_FILES: return True
    _, ext = os.path.splitext(rel)
    if ext in EXCLUDE_EXT: return True
    base = os.path.basename(rel)
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
   - [Capacidades v1.7–v1.10](#capacidades-añadidas-v17v110-resumen--punteros),
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
