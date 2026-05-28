# Changelog — Finanzas

Todos los cambios notables del proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

---

## [1.6.5] — 2026-05-29

### Añadido

- **Tramos IRPF configurables** (AdminPanel → Configuración):
  - Nueva tabla `tax_brackets` en la BD. El admin puede editar los tramos del
    IRPF del ahorro (desde/hasta/tipo %) sin tocar el código.
  - Valores por defecto: los 5 tramos vigentes en España (19/21/23/27/28 %).
  - El informe fiscal HTML usa los tramos de la BD en lugar de los hardcodeados.
  - Endpoint público `GET /api/config/tax-brackets` para la UI de dividendos.
  - Endpoints admin CRUD `GET/POST/PUT/DELETE /api/admin/config/tax-brackets`.

- **Campo de retención y botón "Aplicar -X%" en formulario de dividendos**:
  - El campo `withholding_tax` ahora es visible y editable en el formulario.
  - El botón "Aplicar -X%" calcula automáticamente la retención aplicando el
    tipo del primer tramo (el menor) sobre el importe bruto.
  - La etiqueta del botón refleja el tipo actual del primer tramo configurado.

- **Tipo de cambio automático al seleccionar fecha** (transacciones y dividendos):
  - Al seleccionar una fecha en un formulario con divisa USD, la app busca el
    tipo EUR/USD de esa fecha en la BD (tabla `ecb_rates`) y lo rellena
    automáticamente. Si no hay dato local, consulta Yahoo Finance como
    fallback. El campo queda editable para corrección manual.
  - Nuevo endpoint `GET /api/markets/exchange-rate?date=YYYY-MM-DD`.

### Infraestructura

- Migración Alembic `f1a2b3c4d5e6` — tabla `tax_brackets` con seed data.
- 224 tests en verde (20 tests nuevos: CRUD tramos, permisos, tipo de cambio).

---

## [1.6.4] — 2026-05-28

### Añadido

- **Proxy inverso Caddy con HTTPS automático**: se añade un servicio `caddy`
  al `docker-compose.yml`. Caddy obtiene y renueva el certificado Let's Encrypt
  automáticamente; no requiere ninguna configuración manual de SSL.
- **`Caddyfile`**: nuevo fichero de configuración de Caddy, incluido en el
  paquete de distribución. Lee el dominio de la variable de entorno `DOMAIN`.
- **Guía de despliegue HTTPS**: nueva sección en el manual de instrucciones
  con los 7 pasos para poner la app en producción con HTTPS en un VPS.

### Cambiado

- `docker-compose.yml`: el contenedor `finanzas` ya no expone puertos al host;
  el acceso externo pasa por Caddy vía la red Docker interna (`finanzas:8000`).
- `docker-compose.yml`: añadidas variables `DOMAIN` y `COOKIE_SECURE`.
- `.env.example`: nuevas variables `DOMAIN` (dominio para Caddy) y
  `COOKIE_SECURE=true` (obligatorio con HTTPS).

---

## [1.6.3] — 2026-05-27

### Añadido

- **Actualización manual del historial** (AdminPanel): nueva sección
  "Actualización manual del historial" en la página de administración.
  - Botón "⚠ Forzar actualización del historial" con panel de confirmación
    que detalla las consecuencias antes de ejecutar (tiempo estimado,
    imposibilidad de cancelar, ejecución en segundo plano).
  - El proceso lanza `update_price_history` + `update_snapshots` en un
    hilo separado para no bloquear la UI.
  - Protección contra ejecuciones concurrentes: si ya hay una actualización
    en curso devuelve 409 e informa al usuario.
  - Spinner y mensaje "Actualizando…" mientras se ejecuta.
  - Polling automático cada 3 s hasta completar; muestra "✓ completada"
    o el mensaje de error al terminar.
  - Pie de sección con fecha/hora y resultado de la última ejecución.
  - Endpoints: `POST /api/admin/force-history-update` (202 / 409) y
    `GET /api/admin/force-history-update/status`.

### Infraestructura

- 204 tests en verde (sin cambios en tests existentes).

---

## [1.6.2] — 2026-05-27

### Corregido

- **Gráfico de cartera — caída artificial al final**: el gráfico de
  "Evolución del valor" mostraba una caída brusca en el último punto
  cuando un valor pagaba un dividendo. La causa era que `fetch_history`
  usaba `auto_adjust=True` en yfinance, que ajusta retroactivamente
  *todos* los cierres de la ventana descargada, incluyendo el más reciente
  (el del mismo día del ex-date). El precio así obtenido (p.ej. 2,94 €
  para SAB.MC cuando el real era 3,44 €) se almacenaba en `price_history`
  como dato correcto; al reconstruir la evolución de cartera con ese cierre
  el valor aparecía mucho más bajo ese día.
  - `fetch_history` ahora usa `auto_adjust=False` (precios reales de
    mercado, sin ajuste por dividendo).
  - El job nocturno `_update_history_for_security` re-descarga los últimos
    7 días (en lugar de solo desde `last_date + 1`) y usa
    `on_conflict_do_update` para sobrescribir cualquier entrada incorrecta
    almacenada previamente.

### Infraestructura

- Limpieza: eliminado `finanzas-v1.6.0.zip` superado por v1.6.1 y v1.6.2.
- 196 tests en verde (sin cambios).

---

## [1.6.1] — 2026-05-27

### Añadido

- **Buscador en Mercados**: campo de búsqueda en tiempo real sobre la lista
  de valores de la pestaña activa. Filtra simultáneamente por ticker (Yahoo
  Ticker) y por nombre del valor, sin distinción de mayúsculas/minúsculas.
  - El filtro es local (sin petición al backend) y funciona sobre los datos
    ya cargados de la pestaña.
  - Se limpia automáticamente al cambiar de pestaña.
  - Botón ✕ para borrar la búsqueda con un clic.
  - Contador "X de Y" visible cuando hay un filtro activo.
  - Mensaje "Ningún valor coincide con la búsqueda" si no hay resultados.
  - Funciona tanto en la vista escritorio (tabla) como en móvil (tarjetas).
  - Internacionalizado (ES/EN).

### Infraestructura

- 4 nuevas claves `markets.search_*` en `translations.js`.
- 196 tests en verde (sin cambios).

---

## [1.6.0] — 2026-05-27

### Añadido

- **Dashboard personalizable**: el usuario puede activar/desactivar cada
  sección y reordenarlas con los botones ▲/▼ del modal de configuración
  (⚙ en la cabecera). La configuración se persiste en `localStorage`.
  Secciones disponibles:
  - **Resumen (KPIs)**: tarjetas de valor total, B/P latente, variación
    del día y número de posiciones abiertas.
  - **Posiciones abiertas**: tabla simplificada de posiciones.
  - **Favoritos**: tabla con barra de desplazamiento vertical (máx. 360 px)
    para listas largas.
  - **Mayores movimientos**: para cada mercado seleccionado, muestra las
    5 mayores subidas y las 5 mayores bajadas del día. Activada por defecto.
  - **Gráficos de cartera**: los tres gráficos de "Mi Cartera"
    (distribución, B/P por acción, evolución del valor). Desactivada por
    defecto (opt-in).
- **Selector de mercados para movimientos**: en el modal ⚙ se puede
  elegir de qué mercados se muestran las subidas/bajadas. Por defecto
  se muestran todos los mercados disponibles.
- **Selector de gráficos para el dashboard**: permite elegir cuáles de
  los tres gráficos de cartera se muestran en el dashboard.

### Modificado

- **Top movers — filtro estricto**: `direction=up` devuelve solo valores
  con `daily_change_pct > 0`; `direction=down` solo los de `< 0`.
  Antes, si había menos de 5 bajadas reales, se rellenaba con los valores
  que menos subían. Ahora se muestran los huecos vacíos con el mensaje
  "Sin movimientos".
- **Gráficos de cartera extraídos** a `PortfolioChartsPanel.jsx`
  (componente compartido entre `Portfolio.jsx` y `Dashboard.jsx`).
  `Portfolio.jsx` se simplifica delegando los tres gráficos al componente.

### Corregido

- **Precio en tiempo real distorsionado en días de dividendo**: `fetch_live_quote`
  usaba `auto_adjust=True` en la ventana de 5 días de yfinance. Cuando un valor
  ha pagado un dividendo recientemente, yfinance ajusta retroactivamente todos los
  precios de esa ventana por el factor del dividendo (ej: SAB.MC mostraba 2,94 €
  en lugar de 3,44 €). El porcentaje diario permanecía correcto (es un cociente
  y el factor se cancela), pero el precio absoluto quedaba desplazado. Cambiado a
  `auto_adjust=False` en `fetch_live_quote` para obtener el precio real de mercado.
  `fetch_history` (gráfico histórico) mantiene `auto_adjust=True` correctamente.

### Infraestructura

- Nuevo fichero `frontend/src/components/PortfolioChartsPanel.jsx`.
- 18 nuevas claves `dashboard.*` en `translations.js` (ES + EN).
- 196 tests en verde (sin cambios en el número).

---

## [1.5.7] — 2026-05-26

### Modificado

- **Informe impreso — Bloque 2: colores de fila por grupo de valor**: las
  filas del detalle de movimientos comparten un fondo de color cuando
  pertenecen al mismo valor; el fondo alterna (blanco / azul muy claro)
  cada vez que cambia el valor, haciendo inmediatamente visible qué
  operaciones corresponden a cada acción.
- **Gráficos de cartera — títulos traducidos**: los tres títulos de los
  gráficos de la página "Mi cartera" ("Distribución de cartera",
  "Beneficio / Pérdida por acción (%)" y "Evolución del valor de cartera")
  así como la etiqueta del tooltip de evolución, usaban cadenas
  hardcodeadas en español. Ahora se obtienen de `t()` y cambian al inglés
  cuando se selecciona ese idioma:
  - "Distribución de cartera" → "Portfolio distribution"
  - "Beneficio / Pérdida por acción (%)" → "Gain / Loss per security (%)"
  - "Evolución del valor de cartera" → "Portfolio value over time"
  - Tooltip "Valor cartera" → "Portfolio value"
- **Detalle de valor (`SecurityDetail`) — internacionalización completa**:
  toda la página estaba hardcodeada en español. Traducidas todas las
  cadenas visibles: etiquetas de tarjetas (precio, var. día, mínimos,
  máximos, acciones, B/P, dividendos, comisiones…), títulos de sección
  (Compras, Ventas, Dividendos), cabeceras de tabla, botones (Añadir,
  Empezar a seguir, Editar, Actualizar, Favorito), mensajes de estado
  vacío, confirmaciones de borrado, modales de transacción, dividendo y
  edición de valor, y mensajes de error en formularios.
  ~70 cadenas extraídas como claves `sd.*` en `translations.js` (ES + EN).

### Infraestructura

- Regla 27 añadida a `CLAUDE.md`: todo texto visible del frontend debe
  obtenerse con `t()`, con las dos traducciones ES + EN.
- 4 nuevas claves `portfolio.chart_*` y ~70 claves `sd.*` en `translations.js`.
- 196 tests en verde (sin cambios en el número).

---

## [1.5.6] — 2026-05-26

### Corregido

- **Bloque 2: compras del mismo día a distinto precio aparecen como filas
  independientes**: hasta ahora todas las compras de un valor en la misma
  fecha se agrupaban en una sola fila (con precio promedio), ocultando que
  eran operaciones distintas. Ahora la clave de agrupación incluye el
  precio unitario de cada lote: dos compras del mismo día con el mismo precio
  se siguen agrupando (son el mismo lote consumido parcialmente por varios
  pares FIFO), pero dos compras del mismo día a precios distintos generan
  dos filas separadas, mostrando su precio real. Las compras del mismo día
  se ordenan de menor a mayor precio unitario.

### Infraestructura

- 196 tests en verde.

---

## [1.5.5] — 2026-05-26

### Corregido

- **Resumen del Bloque 1 coherente con la vista agrupada por valor**: el
  cuadro "Ganancias / Pérdidas computables / Saldo computable" que aparece
  bajo la tabla de ganancias/pérdidas ahora usa el resultado NETO de cada
  valor para clasificarlo como ganancia o pérdida, en lugar de clasificar
  cada par FIFO individualmente.

  Ejemplo: Acciona Energía tuvo dos ventas en el ejercicio, una con
  resultado -2,84 € y otra con +19,35 €. El resultado neto del valor es
  +16,51 €, que se contabiliza íntegramente como ganancia.
  En el sistema anterior aparecía una ganancia de +19,35 y una pérdida de
  -2,84 de forma separada, siendo inconsistente con la fila única que ya
  muestra +16,51 en la tabla.

  El saldo computable final (`ganancias + pérdidas computables`) es
  matemáticamente idéntico; solo cambia cómo se desglosa entre las dos
  líneas del resumen.

### Infraestructura

- Nueva función `_compute_adjusted_totals()` en `pdf_generator.py`:
  agrupa los pares FIFO por valor antes de clasificar, separando los pares
  afectados por la regla de recompra que se acumulan sin cambios.
- 196 tests en verde.

---

## [1.5.4] — 2026-05-26

### Modificado

- **Informe impreso — Bloque 1 rediseñado (totalizado por valor)**:
  - Se eliminan las columnas "F. compra" y "F. venta" (el detalle está en
    el bloque 2).
  - Una sola fila por valor y ejercicio, con el acumulado de todas las
    operaciones FIFO: nº de acciones totales, coste total, importe total
    de ventas y resultado total.
  - Nueva columna "Año venta" (muestra solo el año, sin día/mes).
  - Si algún par FIFO del valor tiene pérdida marcada por la regla de
    recompra, la fila aparece atenuada con nota explicativa.
- **Informe impreso — Bloque 2: nueva columna "Subtotal" y mejoras**:
  - Se añade la columna "Subtotal (€)" (= nº acciones × precio unitario,
    sin comisión) entre "Precio unit." y "Comisión".
  - La columna "Total" muestra ahora: coste total pagado en compras
    (subtotal + comisión) e importe neto recibido en ventas (subtotal − comisión).
    La relación es siempre coherente: subtotal ± comisión = total.
  - Las filas se ordenan primero por nombre del valor, luego por fecha de
    operación (antes se ordenaba primero por fecha), de modo que todas las
    operaciones de un mismo valor aparecen agrupadas visualmente.

### Infraestructura

- 196 tests en verde (sin cambios en el número).

---

## [1.5.3] — 2026-05-26

### Modificado

- **Cabecera resumen fiscal — aclaración sobre comisiones**: la tarjeta
  "Resultado neto ventas" (tanto en la pantalla del ejercicio en curso como
  en el informe impreso) añade ahora un subtexto que aclara que las
  comisiones ya están incluidas en el cálculo, evitando confusión con la
  tarjeta "Comisiones pagadas".
- **Informe impreso — Bloque 2 reemplazado**: la sección "Gastos en
  comisiones" se sustituye por "Detalle de movimientos", que lista cada
  operación de compra y venta (por fecha y valor) con: tipo, fecha, nº de
  acciones, precio unitario, comisión, divisa y total de la operación.
  Las operaciones del mismo valor y fecha se agregan en una sola fila.
  Las compras muestran el precio neto de comisión y el total con comisión;
  las ventas muestran el precio bruto y el importe total bruto.
- **Internacionalización completa del informe fiscal** (ES/EN):
  - Todos los textos de `TaxReport.jsx` (tarjetas, gráfico de tramos,
    sección de informe completo) usan ahora `t('tax.*')` desde `AppContext`.
  - El informe HTML impreso recibe el parámetro `?lang=es|en` y usa un
    diccionario `labels` para todos sus textos (títulos de bloques, cabeceras
    de columnas, avisos, pie de página).
  - Los avisos del informe impreso se generan en el idioma solicitado.
  - El texto de la regla de recompra ("NO COMPUTA") se localiza en el
    informe impreso según el idioma.
  - Traducciones añadidas en `translations.js`: 18 nuevas claves `tax.*`
    en español e inglés.

### Infraestructura

- `SaleLine` enriquecida: nuevos campos `buy_fee_eur`, `sell_fee_eur`,
  `currency` y `fiscal_window_days` (usados por el generador de movimientos).
- `SecurityRef` enriquecida: nuevo campo `currency` propagado desde
  `portfolio_repository._to_security_ref`.
- `pdf_generator.render_tax_report_html` acepta `lang: str = "es"`.
- `GET /reports/tax/{year}/html` acepta `?lang=es|en`.
- 196 tests en verde (sin cambios en el número).

---

## [1.5.2] — 2026-05-25

### Corregido

- **`sort_order` perdido en export/import de catálogo**: la exportación del
  catálogo de mercados (`GET /admin/catalog/export`) no incluía el campo
  `sort_order`, con lo que un ciclo export→import dejaba todos los mercados
  con `sort_order=0`, borrando el orden visual configurado por el admin.
  Añadido el campo al JSON de exportación y al schema `CatalogMarketIn`.
  2 tests de regresión.
- **Texto del plazo de recompra incorrecto en el informe fiscal**: el aviso
  de la regla de recompra en el informe IRPF usaba `market == "nasdaq"` para
  decidir el texto, en lugar del valor real `fiscal_window_days`. Mercados con
  código distinto de "nasdaq" pero con ventana de 365 días decían "dos meses"
  (incorrecto); mercados crypto (`fiscal_window_days=1`) también decían "dos
  meses". Ahora el texto se deriva del campo: ≥365 días → "un año",
  ≥30 días → "N meses", <30 días → "N días".
  2 tests de regresión.
- **Regla de recompra no detectaba consumo parcial de lote**: si el FIFO
  consumía solo una parte de un lote de compra dentro del plazo (p.ej. compra
  10 acc, venta 5 con pérdida), las acciones restantes del mismo lote no se
  detectaban como "recompra" y la pérdida se marcaba erróneamente como
  computable. Corregido normalizando `all_buys` con splits y comparando
  `buy.shares` vs `match.shares` para detectar el sobrante.
  `_normalize_splits` renombrada a `normalize_splits` (función pública).
  2 tests de regresión.
- **`HTTP_422_UNPROCESSABLE_ENTITY` deprecado**: `delete_position` usaba el
  código de estado deprecado generando `DeprecationWarning` de Starlette en
  los tests. Cambiado a `HTTP_422_UNPROCESSABLE_CONTENT`.

### Infraestructura

- 196 tests en verde (subida desde 190 en v1.5.1).

---

## [1.5.1] — 2026-05-24

### Añadido

- **Eliminar posición sin ventas**: nueva acción en Mi Cartera para borrar
  una posici��n completa (y todas sus compras y dividendos asociados) cuando
  el usuario la dio de alta por error o para pruebas.
  - Botón 🗑 visible en la fila solo si la posición no tiene ninguna venta.
  - Diálogo de confirmación antes de eliminar.
  - Backend: `DELETE /api/portfolio/positions/{position_id}` (204).
    Si la posición tiene ventas → 422 con mensaje claro.
  - 3 tests de regresión: sin ventas (204), con ventas (422), id inexistente (404).
- **Badge ACCIÓN/ETF/CRYPTO en Mi Cartera**: el chip de tipo de activo
  (igual que en el Explorador de Mercados) aparece ahora también en la
  columna "Valor" de las tablas de posiciones abiertas y cerradas.
  El campo `market_code` se añade a `PositionSummary` y
  `ClosedPositionSummary`.

---

## [1.5.0] — 2026-05-24

### Añadido

- **ETFs y criptomonedas**: soporte completo para nuevos tipos de activos
  mediante el mecanismo de mercados dinámicos existente.
  - `catalogo-etfs-completo.json`: 47 ETFs distribuidos en dos mercados
    (`etfs_eur` y `etfs_usd`). ETFs en GBP excluidos (divisa no soportada).
  - `catalogo-crypto.json`: 31 criptomonedas en mercado `crypto` (USD),
    con `fiscal_window_days=1` (sin regla de recompra en España).
- **Orden configurable de pestañas de mercado**: columna `sort_order`
  (INTEGER, migración `e3f1a2b4c5d6`) en la tabla `markets`. El admin
  puede reordenar con botones ▲/▼ en el AdminPanel. Endpoint
  `PUT /admin/markets/reorder` acepta `[{code, sort_order}]`.
- **Internacionalización (i18n) ES/EN**:
  - `frontend/src/i18n/translations.js`: diccionario completo de cadenas
    para español e inglés.
  - `AppContext.jsx`: estado `locale` persistido en `localStorage`,
    función `t(key)` con fallback ES y fallback a la propia clave.
  - Selector de idioma en Utilidades (ES 🇪🇸 / EN 🇬🇧).
  - Traducciones aplicadas en: Navigation, Markets, Portfolio, Dashboard,
    SecurityTable, SecurityCard, Utilities.
- **Badge de tipo de activo**: chip visual en tabla y tarjetas móviles.
  Derivado del código de mercado: `etf` → "ETF" (azul), `crypto` →
  "Crypto" (morado), resto → "Acción"/"Stock" (verde).
- **Columnas condicionales** en `SecurityTable`: ISIN, Google Ticker y
  Dividendo solo se muestran si al menos un valor del conjunto actual tiene
  ese dato. Especialmente útil en el mercado Crypto (sin ISIN).
- **`fmtPrice()` adaptativo**: 2 decimales para precios normales, 4 para
  precios < 1, 6 para precios < 0,01 (necesario para micro-caps como SHIB).
- **Scroll horizontal en pestañas**: con muchos mercados activos, las
  pestañas no se envuelven a segunda línea sino que hacen scroll horizontal
  suave con scrollbar fina.
- **Método `api.put()`** añadido al cliente HTTP del frontend.
- **Pausa anti-rate-limit** (0,5 s) entre peticiones a yfinance en el
  scheduler de actualización de histórico.

### Modificado

- `backend/app/models/market.py`: añadido `sort_order: Mapped[int]`.
- `backend/app/schemas/market_admin.py`: `sort_order` en `MarketCreate`,
  `MarketUpdate`, `MarketOut`. Nueva clase `MarketReorderItem`.
- `backend/app/api/admin_markets.py`: nuevo endpoint `/markets/reorder`;
  `list_markets` y `markets.py` ordenan por `sort_order, code`.
- `backend/app/main.py`: versión `1.5.0`.
- `frontend/package.json`: versión `1.5.0`.

### Infraestructura

- Migración Alembic `e3f1a2b4c5d6` (v1.5.0 market sort_order).

---

## [1.4.3] — 2026-05-xx

### Añadido

- `GET /admin/catalog/export` y `POST /admin/catalog/import`.
- Fichero `catalogo-valores.json` con 93 valores (IBEX35 + Mercado
  Continuo + Nasdaq) listos para importar.

---

## [1.4.2] — 2026-05-xx

### Añadido

- Resumen fiscal PDF: primera página con 4 KPIs y barra de tramos IRPF.
- Cabecera fija en móvil con nombre de la app y versión.

---

## [1.4.1] — 2026-05-xx

### Corregido

- 6 bugs con 13 tests de regresión:
  `avg_return_pct`, backup USD/rate=1, precio cero, dedup fee,
  `shares_sold` con splits, regla de recompra con dos compras el mismo día.

---

## [1.4.0] — 2026-05-xx

### Añadido

- Gestión de splits / contrasplits (tabla `security_splits`).
- Normalización automática FIFO con `_normalize_splits()`.
- AdminPanel: sección de splits por valor.

---

## [1.3.0] — 2026-05-xx

### Añadido

- Control de suscripciones de usuario: enable/disable, caducidad, historial.
- Nombre de la aplicación personalizable desde `app_config`.
- Selector de tema claro/oscuro en la interfaz.

---

## [1.2.0] — 2026-xx-xx

### Añadido

- Mercados dinámicos: la tabla `markets` reemplaza los mercados hardcodeados.
- AdminPanel: CRUD de mercados y valores.

---

## [1.0.0] — 2026-xx-xx

### Primera versión

- Auth (cookie firmada, bcrypt), FIFO, informe fiscal IRPF básico.
- Dashboard, Markets, Portfolio, SecurityDetail, Utilities.
- PWA + Docker.
