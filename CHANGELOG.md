# Changelog — Finanzas

Todos los cambios notables del proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

---

## [1.9.12] — 2026-06-05

### Añadido — Botón «Cerrar sesión» visible en todas las secciones

- En móvil, el botón de cerrar sesión ahora aparece siempre en la cabecera
  superior (junto a la campana de alertas), en lugar de solo en el Dashboard.
  En escritorio ya estaba en la barra lateral (sin cambios).
- Se elimina el botón redundante de logout del propio Dashboard.

### Añadido — Campana de alertas de precio

- Icono 🔔 en la esquina superior derecha de todas las secciones (cabecera
  móvil y sidebar escritorio), a la izquierda del botón de cerrar sesión.
- La campana resalta (opacidad plena + badge verde con el número de alertas)
  cuando hay posiciones cuyo precio actual alcanza el objetivo fijado:
  - Precio actual ≥ precio venta objetivo → alerta «**Vender**».
  - Precio actual ≤ precio compra objetivo → alerta «**Comprar**».
- Al pulsar se abre un popup con la lista de valores con alertas activas:
  nombre, ticker y tipo de alerta. Haciendo clic en cualquiera se navega
  al detalle de ese valor.
- Sin alertas activas: campana semi-transparente sin badge.
- Los datos se cargan al entrar y se refrescan automáticamente cada 5 minutos.

---

## [1.9.11] — 2026-06-05

### Añadido — Fondo relacionado en tabla de traspasos

- La tabla de traspasos de fondos (SecurityDetail) muestra una nueva columna
  **Fondo relacionado**: el nombre del fondo en la otra punta del traspaso
  (origen para `transfer_in`, destino para `transfer_out`). Haciendo clic en
  el nombre se navega a la ficha de ese fondo.
- El endpoint `GET /portfolio/by-security/{id}/operations` enriquece las
  transacciones de traspaso con `related_security_id` y `related_security_name`
  (una sola query JOIN extra; `null` si la contraparte fue eliminada).

### Añadido — Precios objetivo de compra y venta en SecurityDetail

- Nuevo campo **Precio compra objetivo** y **Precio venta objetivo** en la ficha
  de cada valor (a la derecha de Notas en pantallas anchas, debajo en móvil).
  Se editan directamente y se guardan al perder el foco.
- Nuevo campo `target_buy_price` en la tabla `positions` (migración Alembic
  `d5e6f7a8b9c1`). El `target_sell_price` ya existía; ambos aparecen ahora
  también en SecurityDetail (antes solo en la lista de cartera).
- Nuevo endpoint `PATCH /portfolio/{position_id}/target-buy`.
- **Indicador de alerta parpadeante** en la esquina superior derecha de la
  ficha (a la izquierda del botón de favorito):
  - **«Vender»** (verde, parpadeo suave ~1.5 s) si precio actual ≥ objetivo venta.
  - **«Comprar»** si precio actual ≤ objetivo compra.
  - Si ambos se cumplen, prevalece «Vender».

---

## [1.9.10] — 2026-06-05

### Corregido — Histórico de cartera inflado antes de un split de acciones

- `_history_series` aplicaba todos los splits **futuros** a cada transacción sin
  importar la fecha `d` que se estaba procesando. Con `price_history` en precios
  reales (`auto_adjust=False`), esto causaba que para fechas **anteriores** al
  split el valor de la posición se multiplicara por el ratio (p. ej. ×2 en un
  split 2:1), inflando el gráfico de evolución y distorsionando los retornos por
  período (YTD/1a/3a/total) de cualquier usuario que tuviera valores con splits.
- **Fix**: los splits ahora se aplican progresivamente conforme el eje de fechas
  cruza cada `ex_date` (tres punteros: splits, transacciones y carry-forward de
  precio). Las compras en la propia fecha de split se contabilizan ya en escala
  post-split, coherente con `_normalize_splits`.
- Se añade test de regresión `test_history_split_no_infla_valor_pre_split`.
- Se corrigen los comentarios obsoletos en `providers/yahoo.py` que indicaban
  erróneamente que `fetch_history` usaba `auto_adjust=True`.

---

## [1.9.9] — 2026-06-04

### Corregido — Histórico de cartera con tipo de cambio de cada fecha (FX histórico)

- El gráfico de evolución de cartera convertía **todos** los cierres pasados con
  el tipo de cambio **actual** (`latest_rate`), distorsionando la curva —y los
  retornos por periodo que se apoyan en ella— de los valores en divisa
  extranjera. Ahora cada cierre se convierte a EUR con el tipo del BCE **vigente
  en esa fecha** (`rate_on_date`), precargando los tipos por divisa y buscándolos
  por fecha con bisect (sin penalizar el rendimiento).

---

## [1.9.8] — 2026-06-04

### Mejorado — Donut de distribución: top 8 + «Otros»

- El gráfico de distribución de cartera quedaba ilegible con muchas posiciones
  abiertas. Ahora muestra el **top 8 por volumen** y agrupa el resto bajo
  **«Otros»** (porción gris neutra, no clicable). El porcentaje del tooltip sigue
  siendo sobre el total de la cartera.

---

## [1.9.7] — 2026-06-04

### Mejorado — Rellenar ISINs: 2ª fuente (Business Insider), dos pasadas y exclusión de cripto

- **Pasada 1 (exacta):** Yahoo por ticker (como hasta ahora).
- **Pasada 2 (heurística):** para los que Yahoo no resuelve, búsqueda por **nombre**
  en Business Insider (markets.businessinsider.com). Criterio **conservador**: se
  acepta el ISIN solo si el ticker nativo casa con una única fila de renta
  variable/fondo (o hay un único resultado), y **siempre que ese ISIN no exista
  ya en la BBDD** (evita asignar a un valor el ISIN de otro).
- Las **cripto se excluyen** del rellenado (no tienen ISIN).
- El estado del job desglosa rellenados por pasada (exacta/heurística) y lista
  los descartados por colisión de ISIN y los que siguen sin encontrarse.

---

## [1.9.6] — 2026-06-04

### Corregido — Rellenar ISINs daba «Failed to fetch» en el VPS

- El rellenado de ISINs consultaba Yahoo valor a valor **dentro de la propia
  petición HTTP**. Con muchos valores tardaba minutos y superaba el timeout del
  navegador/proxy (Caddy) → «Failed to fetch»; además solo guardaba al final, así
  que un corte no dejaba nada.
- Ahora se ejecuta **en segundo plano** con **commit incremental** (cada ISIN se
  guarda al momento) y el frontend muestra el **progreso** (revisados/total,
  rellenados) por polling. `POST /admin/securities/fill-isins` responde 202 y hay
  `GET /admin/securities/fill-isins/status`.
- Si el proceso falla a mitad, el estado indica **cuántos se rellenaron antes del
  fallo** (lo ya hecho queda persistido). Re-ejecutar solo revisa los que aún
  faltan.

---

## [1.9.5] — 2026-06-04

### Corregido — Retornos por periodo (YTD/1 año/3 años/total) imposibles y gráfico de historial infravalorado

- El histórico de valor de cartera sumaba cada posición **solo en las fechas con
  cotización propia**. Cuando un valor no tenía precio en una fecha del eje
  (habitual entre fondos —NAV— y acciones, o por festivos desalineados), quedaba
  fuera del total de esa fecha. Esto infravaloraba la cartera, sobre todo el
  **último punto** (`v_end`), y disparaba los retornos por periodo a valores
  imposibles (p. ej. **−110 % total**), porque Modified Dietz quedaba con
  numerador negativo.
- Ahora se construye un **eje de fechas único** y cada posición se valora en cada
  fecha con su **último cierre conocido** (carry-forward). El gráfico de
  historial y las tarjetas YTD/1 año/3 años/total reflejan el valor real.

---

## [1.9.4] — 2026-06-04

### Corregido — Indicadores del año en curso (home fiscal): fondos aparecían junto a ventas

- La pantalla del año en curso de la sección fiscal seguía mostrando los fondos
  sumados en «Resultado neto ventas» (el desglose se había hecho solo en el PDF).
  Ahora replica las tarjetas del informe: «Resultado neto ventas» con solo
  acciones/ETF/cripto, nueva tarjeta «Resultado venta fondos» entre dividendos y
  comisiones, y cuota IRPF estimada bajo cada tarjeta de ganancia.
- `GET /api/reports/tax/{year}/summary` añade `net_sales_eur` (acciones) y
  `fund_net_eur` (fondos); su suma sigue siendo `net_capital_result_eur`.
- Etiquetas alineadas con el PDF: «Cuota IRPF est.» y «Ret. origen».

---

## [1.9.3] — 2026-06-04

### Cambiado — Informe fiscal: etiquetas más claras y avisos sobre la estimación

- La cuota por tarjeta pasa a llamarse **«Cuota IRPF est.»** para no confundirla
  con la retención en origen.
- En la tarjeta de dividendos, la retención se etiqueta **«Ret. origen»**.
- Nuevos avisos (solo cuando hay base imponible):
  - La cuota IRPF estimada **no contempla** la compensación entre ganancias y
    rendimientos (límite 25 %) ni el arrastre de pérdidas de ejercicios
    anteriores (hasta 4 años); la cuota real puede ser menor.
  - Las cuotas por concepto son **orientativas** (reparto proporcional del tipo
    efectivo) y pueden no sumar exactamente la cuota total.
- Decisión de diseño: no se calculan la compensación del 25 % ni el arrastre de
  4 años porque exigirían un histórico completo y fiable de ejercicios
  anteriores que la aplicación no puede garantizar; se documentan en los avisos
  en su lugar.

---

## [1.9.2] — 2026-06-04

### Cambiado — Resumen ejecutivo del informe fiscal: ventas, fondos y cuota por tarjeta

- La tarjeta **«Resultado neto ventas»** ya no acumula los fondos: muestra solo
  acciones/ETF/cripto.
- Nueva tarjeta **«Resultado venta fondos»**, situada entre Dividendos y
  Comisiones, con el resultado de los reembolsos de fondos.
- Cada tarjeta de ganancia (ventas, fondos, dividendos) muestra debajo, en
  pequeño, su **cuota estimada** = importe positivo × tipo efectivo
  (cuota total / base imponible). Antes la cuota solo aparecía en el total.
- La base imponible sigue agregando acciones + fondos + dividendos (todos a la
  base del ahorro); el desglose es solo de presentación.

---

## [1.9.1] — 2026-06-04

### Añadido — Admin: rellenar ISINs que faltan desde Yahoo

- Nuevo botón en AdminPanel («Buscar y rellenar ISINs»): por cada valor sin
  ISIN consulta Yahoo (`Ticker.isin`) y lo guarda. Nunca sobrescribe un ISIN
  ya existente. Reporta cuántos se rellenaron, cuántos se revisaron y qué
  tickers no resolvió Yahoo (para revisión manual).
- `POST /api/admin/securities/fill-isins` (solo admin).
- El proveedor Yahoo gana `fetch_isin(ticker)`, que valida la forma del ISIN
  (12 caracteres, 2 letras de país + 10) y descarta respuestas tipo «-».

---

## [1.9.0] — 2026-06-04

### Añadido — Scatter rentabilidad/tiempo: round-trips parciales de posiciones abiertas

- El gráfico «Rentabilidad vs. tiempo» dejaba fuera las ventas parciales ya
  realizadas de posiciones que siguen abiertas. Ahora cada round-trip cerrado
  del pasado se representa también, aunque la posición conserve acciones.
- Los puntos de posiciones aún abiertas se dibujan con **borde discontinuo y
  relleno más tenue**, y el tooltip lo indica («venta parcial · la posición
  sigue abierta»).
- `GET /api/portfolio/closed-analytics` incluye el campo `still_open` y, para
  los round-trips parciales, no atribuye dividendos al tramo vendido
  (`dividends_eur=0`), ya que no se pueden repartir limpiamente entre lo
  vendido y lo conservado.

---

## [1.8.9] — 2026-06-04

### Cambiado — Informe fiscal: fondos en sección propia

- Las ventas/reembolsos de **fondos de inversión** ya no se mezclan con las
  acciones en el Bloque 1 ni se detallan movimiento a movimiento en el Bloque 2.
  Ahora aparecen en un **Bloque 4 «Ganancias y pérdidas por venta de fondos»**,
  situado **después** de los dividendos, agregado por fondo (una fila por fondo y
  ejercicio) y con su propio subtotal.
- El resumen ejecutivo y la base imponible siguen agregando acciones + fondos
  (fiscalmente ambos van a la base del ahorro). Los traspasos entre fondos, al
  ser fiscalmente neutros, no aparecen en esta sección.

---

## [1.8.8] — 2026-06-04

### Añadido — Admin: sincronizar la divisa de un catálogo

- Nuevo botón 💱 en cada mercado del AdminPanel: fija la divisa de **todos** los
  valores del mercado a la divisa del mercado "padre". Corrige de golpe valores
  dados de alta con la divisa equivocada (p. ej. acciones extranjeras creadas en
  EUR).
- `POST /api/admin/markets/{code}/sync-currency` (solo admin) → devuelve cuántos
  valores se actualizaron.

---

## [1.8.7] — 2026-06-04

### Corregido — Historial de operaciones en posiciones cerradas

- Al entrar a un valor cuya posición está cerrada (vendida o **traspasada del
  todo**), las tablas de compras/ventas/traspasos se ocultaban porque el
  position_id se descubría vía `/portfolio/closed`, que no incluye los fondos
  cerrados solo por traspaso (sin `sale_matches`). Ahora las operaciones se
  obtienen con un endpoint dedicado independiente del estado.
- Nuevo `GET /api/portfolio/by-security/{id}/operations`: transacciones +
  dividendos del valor, exista o no posición abierta (404 si nunca hubo
  posición). SecurityDetail lo usa como fuente del historial.

---

## [1.8.6] — 2026-06-04

### Añadido — Distribución por tipo de producto y por divisa

- Dos nuevos donuts en Mi Cartera: distribución del **valor de mercado** por
  **tipo de producto** (Acciones/Fondos/ETF/Crypto) y por **divisa**
  (EUR/USD/GBP…). Complementan la distribución por valor ya existente.
- Cada gráfico se muestra solo si hay variedad (≥2 grupos) y respeta el
  segmentador por tipo. Solo frontend (los campos `market_type` y `currency` ya
  venían en el resumen de posiciones).

---

## [1.8.5] — 2026-06-04

### Añadido — Rentabilidad por periodo (YTD / 1 año / 3 años / total)

- Nueva fila de indicadores en Mi Cartera (junto al gráfico de evolución) con la
  rentabilidad **por periodo** mediante **Modified Dietz**, que ajusta por el
  momento de las aportaciones/retiradas dentro de cada ventana (los traspasos no
  cuentan). Es la rentabilidad acumulada del periodo (no anualizada), complemento
  de la TIR anual.
- `GET /api/portfolio/period-returns?types=` (respeta el segmentador). Devuelve
  `{ytd, y1, y3, total}` en % (null si no es calculable).
- Refactor interno: la serie de valor histórico se extrae a `_history_series`,
  reutilizada por el gráfico y por los retornos por periodo. Lógica pura
  `modified_dietz` en `services/returns.py`.

---

## [1.8.4] — 2026-06-03

### Añadido — TIR anual (rentabilidad ponderada por dinero / XIRR)

- Nueva métrica **TIR anual** en Mi Cartera: rentabilidad anualizada ponderada
  por dinero sobre todos los flujos reales (compras = salida; ventas y
  dividendos = entrada) más el valor de mercado actual como flujo final. Refleja
  mejor el rendimiento real que el "% sobre invertido" cuando hay aportaciones
  en distintas fechas (DCA). Los traspasos no son flujos (fiscalmente neutros).
- `GET /api/portfolio/xirr?types=` (respeta el segmentador por tipo). Devuelve
  `xirr_pct` (null si no es resoluble: sin operaciones, todo del mismo signo o
  un solo día), `cashflows` y `market_value_eur`.
- Lógica pura en `services/returns.py` (Newton-Raphson + bisección de respaldo).

---

## [1.8.3] — 2026-06-03

### Añadido — Rentabilidad "desde el traspaso" en fondos

- En un fondo cuya posición se nutre **solo de traspasos** (sin compras ni
  ventas), la ficha muestra ahora la **rentabilidad propia del fondo desde el
  traspaso**: valor actual vs valor de mercado en la fecha de cada traspaso
  (participaciones recibidas × NAV de esa fecha). Es distinta del B/P latente,
  que arrastra la base de coste heredada (plusvalía/minusvalía diferida del
  fondo de origen). Así se distingue "cuánto sube este fondo" de "qué pérdida
  diferida traigo".
- Backend: `PositionSummary.transfer_in_market_eur` (valor de mercado al
  traspasar). `null` si la posición no tiene traspasos.

---

## [1.8.2] — 2026-06-03

### Corregido — Valoración en vivo de valores en divisa extranjera

- **Bug**: un valor en divisa distinta de EUR (p. ej. USD) cuyo tipo aún no
  estaba cacheado en `ecb_rates` se valoraba con tipo = 1, es decir, tratando el
  importe extranjero como si fuera euros. El **valor actual** salía sin convertir
  (p. ej. 6×134,28 USD mostrados como 805,68 € en vez de ~694 €), generando un
  **beneficio latente falso**. El coste sí estaba convertido (tipo de la
  operación), de ahí el descuadre.
- **Fix**: cuando el BCE aún no tiene la divisa, `latest_rate` cae al **último
  tipo registrado en una transacción de esa divisa** (el que el usuario
  introdujo/autorrellenó) en lugar de 1. Una vez el job nocturno puebla
  `ecb_rates`, se usa el tipo real. Test de regresión añadido.

### Nota (no es bug)

- Un fondo que solo ha recibido **traspasos** puede mostrar pérdida latente si el
  coste **heredado** de los fondos de origen supera su valor actual: el traspaso
  es fiscalmente neutro y **arrastra la base de coste** (y la plusvalía/minusvalía
  diferida). La recuperación de NAV del fondo de destino no borra esa pérdida
  diferida. Verificado con tests (origen ganador → ganancia; origen USD → coste
  heredado en EUR).

Tests: 362 en verde (+3).

---

## [1.8.1] — 2026-06-03

### Corregido — Coherencia de divisa en importadores y tipos (auditoría post v1.8.0)

- **Backup (usuario y admin)**: el import solo rechazaba `USD` con
  `exchange_rate=1`; ahora rechaza **cualquier divisa no-EUR** con tipo 1 (un
  GBP/CHF con tipo 1 se importaba y luego rompía la carga de la cartera). Misma
  comprobación añadida al import de **dividendos** (antes no la tenía).
- **`GET /markets/exchange-rate?currency=EUR`**: devuelve tipo 1 directamente en
  vez de intentar consultar Yahoo `EUREUR=X`.
- **`update_ecb_rates`**: tras actualizar desde una versión con solo USD, hace
  un **backfill histórico completo** de todas las divisas del BCE (antes, como
  ya había USD reciente, las demás divisas nunca obtenían histórico).

Tests: 359 en verde (+3 de regresión).

---

## [1.8.0] — 2026-06-03

### Añadido — Soporte multi-divisa (más allá de EUR/USD)

Ahora pueden seguirse valores en cualquier divisa que publique el BCE (USD, GBP,
JPY, CHF, …), no solo EUR/USD.

- **Tipos del BCE por divisa**: la tabla `ecb_rates` pasa a PK `(date, currency)`
  y el job nocturno descarga **todas las divisas del BCE (~30) en una sola
  petición** (`EXR/D..EUR.SP00.A`). Migración `c3d4e5f6a1b9` (los datos previos
  se conservan como USD).
- **Valoración en EUR por divisa**: la cartera, el histórico, las aportaciones y
  el informe valoran cada posición con el tipo de **su** divisa (antes solo se
  convertía USD; el resto se trataba como euro → valor erróneo). Helper
  `repositories/exchange_rates.py` (`latest_rate`, `rate_on_date`).
- Se elimina el `CHECK currency IN ('EUR','USD')` de `securities` (migración) y
  se relajan los schemas. La divisa de un valor se valida contra las **divisas
  soportadas** (configurables por el admin; EUR siempre válida).
- `exchange-rate`, import Ghostfolio y backups consultan el tipo **por divisa**
  (caché BCE; Yahoo `EUR{div}=X` como respaldo). El autorelleno del tipo en el
  formulario de operación funciona para cualquier divisa configurada.
- **UI**: la etiqueta "Tipo EUR/USD" pasa a "Tipo de cambio (EUR/{divisa})".

### Limitaciones

- Solo divisas con tipo de referencia publicado por el BCE (las que no, dependen
  del respaldo de Yahoo para el tipo histórico).

---

## [1.7.9] — 2026-06-03

### Añadido — Compra de fondos por importe

- En valores de **mercados de fondos**, la ventana de operación cambia: el campo
  "Acciones" pasa a **"Participaciones"** y, en lugar de "Precio por acción", se
  introduce el **"Importe total"** pagado. El precio por participación se deriva
  automáticamente (precio = importe / participaciones), que es como lo informa el
  banco. El backend sigue almacenando el precio por participación (sin cambios de
  modelo). En valores no-fondo la ventana es la de siempre.

### Añadido — Export a Ghostfolio

- `GET /api/portfolio/export-ghostfolio`: descarga las operaciones en formato
  Ghostfolio (JSON con `activities`: BUY/SELL/DIVIDEND), compatible con su
  importador y con el de esta app (round-trip). Botón en Utilidades. Traspasos y
  planes no se representan en ese formato (para fidelidad completa, backup JSON).

### Cambiado — Snapshots en vivo por lotes (yf.download)

- El job en vivo y el refresco de Top movers agrupan los tickers en **una sola
  petición por lote** (`yf.download`, lotes de 40) en vez de una por valor.
  Sumado al conjunto activo de v1.7.7, deja las peticiones a Yahoo casi al
  mínimo. Los tickers que fallen en el lote se omiten y se reintentan en la
  siguiente pasada.

---

## [1.7.8] — 2026-06-02

### Añadido — Import/export completados

- **Export a CSV** (`GET /api/portfolio/export-csv`): descarga las operaciones
  (compras, ventas y dividendos) con las mismas columnas que la plantilla de
  importación → round-trip con `import-csv`. Botón en Utilidades. Los traspasos
  y planes de aportación no se representan en CSV (formato plano); para fidelidad
  completa, el backup JSON.
- **Planes de aportación periódica en los backups**: el backup de usuario y el
  de admin ahora **exportan e importan** `recurring_plans` (antes se perdían en
  un backup/restore). Importación idempotente (dedup por frecuencia/inicio/total/
  importe).
- **Mercados en el backup admin**: el backup completo incluye los mercados (con
  `market_type`); al importar se crean los que falten **antes** que los valores,
  para que un restore en BD limpia no deje valores "huérfanos" sin mercado.
  Compatible con backups admin anteriores (deriva el tipo si falta).

---

## [1.7.7] — 2026-06-02

### Cambiado — Actualización de precios por "conjunto activo" (robustez Yahoo)

Reduce drásticamente las peticiones a Yahoo Finance (riesgo de rate-limit/baneo)
al dejar de actualizar todo el catálogo cada pocos minutos.

- **Conjunto activo**: el job en vivo (cada N min) solo actualiza los valores
  **en uso** (poseídos en `positions` o seguidos en `favorites`), no el catálogo
  entero. `update_snapshots(only_ids=...)`.
- **Barrido nocturno** sigue refrescando histórico + snapshot de **todo** el
  catálogo una vez al día (base para navegar el explorador).
- **Refresco perezoso** (`POST /markets/{id}/refresh-if-stale`): al examinar un
  valor que no está en uso, se actualiza en ese momento (anti-rebote 1 h) sin
  meterlo en la programación.
- **Top movers bajo demanda** (`POST /markets/{market}/refresh-movers`): al abrir
  el Dashboard se refrescan en segundo plano los mercados de la sección Movers,
  con throttle (15 min) y tope de tamaño (250) para no escanear catálogos
  enormes. Base diaria garantizada por el barrido nocturno.
- **Menos coste por valor**: el path en vivo ya **no** consulta dividendos
  (petición extra a Yahoo); se capturan en el barrido nocturno.
- **Pausa entre peticiones** y **corte ante 429** (rate-limit) en las pasadas de
  snapshots. `refresh-all` (admin) pasa a ejecutarse **en segundo plano** y
  paced, sin bloquear la petición.

### Corregido

- Segmentación: la selección persistida se sanea contra los tipos realmente
  presentes (ya no queda una vista vacía sin chip resaltado tras vender todo de
  un tipo).
- Eliminadas traducciones huérfanas (`admin.market_is_fund*`, `market_fund_badge`).

---

## [1.7.6] — 2026-06-02

### Añadido — Segmentación por tipo de producto

- Nuevo campo **`market_type`** por mercado (`stock`/`fund`/`etf`/`crypto`),
  editable por el admin (sustituye el checkbox "Mercado de fondos" por un
  selector "Tipo"). `is_fund_market` se mantiene **derivado** del tipo para la
  lógica fiscal. Migración `b2c3d4e5f7a8` con autorelleno (fondos→fund;
  código con "etf"/"crypto"→etf/crypto; resto→stock).
- **Mi Cartera** y **Dashboard**: segmentador de **chips multiselección**
  (Todo · Acciones · Fondos · ETF · Crypto). Filtra resumen, posiciones,
  gráficos, cerradas y dividendos; los informes que quedan vacíos se ocultan.
  La selección se recuerda por pantalla.
- **`GET /api/portfolio/history?types=`**: el histórico (agregado en backend)
  acepta filtro por tipos para segmentar el gráfico de evolución.
- **Mercados**: menú de **dos niveles** — Tipo de producto (Acciones/Fondos/
  ETF/Crypto) + botón ★ Favoritos; segundo nivel con los mercados del tipo
  (si solo hay uno, se muestra directo).
- El tipo se expone por valor en `SecurityOverview`, `PositionSummary`,
  `ClosedPositionSummary` y dividendos-por-valor; el badge usa el tipo
  explícito en vez de heurística por código.

### Import / export adaptados

- **Catálogo (JSON)**: export incluye `market_type`; import lo respeta y, si
  falta (catálogos anteriores a v1.7.6), lo deriva. Se mantiene `is_fund_market`
  por compatibilidad.
- **CSV, Ghostfolio y backup**: operan por *ticker* sobre valores existentes;
  el tipo lo hereda el valor de su mercado, sin cambios de formato.

---

## [1.7.5] — 2026-06-02

### Cambiado — Aportaciones periódicas por rango de fechas

- La serie de aportaciones se define ahora por **fecha de inicio → fecha de
  fin** (ambas incluidas), en lugar de por un número fijo de aportaciones. Más
  intuitivo (p. ej. "200 €/mes de enero 2024 a diciembre 2030"). El backend
  calcula las aportaciones del rango (`contribution_dates_until`); internamente
  el plan sigue guardando el total derivado, sin migración de BD.
- **SecurityDetail**: el formulario sustituye "Nº de aportaciones" por "Fecha
  de fin" (con validación fin ≥ inicio).

### Corregido

- El build de v1.7.4 se compiló antes del bump de versión y mostraba "1.7.3"
  en la interfaz. Recompilado con la versión correcta (commit de corrección).

---

## [1.7.4] — 2026-06-02

### Cambiado — Aportaciones periódicas: modelo híbrido (pasado + futuro)

Replanteamiento del DCA de 1.7.3, que solo sabía registrar aportaciones
**pasadas** (calculaba participaciones con el precio histórico) y omitía en
silencio las futuras —imposibles de valorar sin cotización—. Ahora:

- **Aportaciones pasadas** (fecha <= hoy): se registran ya como compras
  (backfill) con el precio histórico de cada fecha, como antes.
- **Aportaciones futuras** (fecha > hoy): se guardan como un **plan** que el
  scheduler ejecuta al llegar cada fecha, creando la compra con el precio real
  de ese día. Ya no se pierden ni exigen conocer las participaciones por
  adelantado.
- Nueva tabla `recurring_plans` (migración `a1b2c3d4e5f7`). El calendario se
  ancla a la fecha de inicio para no acumular "drift" de día de mes.
- `execute_due_recurring_plans` corre en el job nocturno (con catch-up si el
  scheduler estuvo caído). Un hueco de precio en el pasado se salta; una fecha
  de hoy sin precio aún se reintenta en la siguiente pasada.
- Endpoints: `GET /api/portfolio/recurring-plans` (planes activos),
  `DELETE /api/portfolio/recurring-plans/{id}` (cancelar, sin tocar compras ya
  creadas). El POST devuelve el backfill creado **y** el plan futuro.
- **SecurityDetail**: el resumen muestra compras creadas + plan futuro; nueva
  tabla de planes activos con botón "Cancelar".

---

## [1.7.3] — 2026-06-02

### Añadido — Aportaciones periódicas (DCA)

- Nuevo endpoint `POST /api/portfolio/{position_id}/recurring-buys`: genera una
  serie de compras con **importe fijo por aportación**. Para cada fecha resuelve
  el precio histórico del valor (`price_history`, día hábil anterior si esa
  fecha no cotiza) y calcula participaciones = importe / precio. Los valores en
  divisa distinta de EUR usan el tipo EUR/USD del BCE de cada fecha.
- Las aportaciones que no se pueden valorar (fecha futura, sin precio histórico
  o sin tipo de cambio) se **omiten** y se devuelven con su motivo; el resto se
  crean igualmente.
- Frecuencias: semanal, mensual, trimestral, anual. La suma mensual recorta el
  día de mes cuando no existe (31 ene + 1 mes → 28/29 feb).
- **SecurityDetail**: botón "Aportación periódica" en la sección de compras, con
  resumen de creadas/omitidas tras generar.
- Lógica pura de calendario en `services/recurring.py` (sin I/O), con tests.

---

## [1.7.2] — 2026-06-02

### Añadido — Badge "Fondo"

- Los valores de mercados de fondos muestran ahora un badge ámbar **"Fondo"**
  (en vez de "Acción") en el explorador de mercados, las tarjetas y la cartera.
  El backend expone `is_fund_market` en `SecurityOverview`, `PositionSummary` y
  `ClosedPositionSummary` para que el frontend distinga el tipo de activo.

### Añadido — Deshacer traspaso

- Nuevo endpoint `DELETE /api/portfolio/transfer/{group_id}`: deshace un
  traspaso borrando **atómicamente** sus dos filas acopladas (`transfer_out`
  en el origen + `transfer_in` en el destino). Valida antes que la operación
  no deje ventas posteriores sin respaldo en ninguna de las dos posiciones
  (si el fondo de destino ya reembolsó, se rechaza con 422).
- Las dos filas de un traspaso se vinculan con un `transfer_group_id` (UUID).
  Migración Alembic `f6a1b2c3d4e5`: nueva columna en `transactions`.
- **SecurityDetail**: botón "Deshacer" en la tabla de traspasos (solo para
  traspasos creados desde v1.7.2, que llevan `transfer_group_id`).
- El backup/restore (usuario y admin) preserva `transfer_group_id`, de modo
  que los traspasos siguen siendo anulables tras una restauración.

### Corregido / Blindaje

- **Posición fantasma**: un fondo traspasado al 100% (cerrado por
  `transfer_out`, sin venta real) ya no aparece en `/portfolio/closed` como
  una fila cerrada con todo a cero. Coherente con `closed-analytics`.
- **CRUD de transacciones blindado**: editar (`PATCH`) o borrar (`DELETE`) una
  fila `transfer_in` / `transfer_out` suelta desde el endpoint genérico de
  transacciones se rechaza con 422. Los traspasos solo se gestionan vía los
  endpoints de traspaso, evitando que se rompa la pareja o el coste heredado.
- `crear-tablas.sql` (esquema de referencia) actualizado: `ck_tx_type` con los
  tipos de traspaso, `currency` sin CHECK (multi-divisa), y `transfer_group_id`.

---

## [1.7.1] — 2026-06-02

### Corregido — Traspasos de fondos en backup, histórico y analytics

- **backup/restore** (`backup.py`, `admin.py`): las transacciones `transfer_in` /
  `transfer_out` ya no se descartan al restaurar un backup. Antes se rechazaban
  silenciosamente con un error, dejando el FIFO del fondo de destino roto tras
  una restauración.
- **Histórico de cartera** (`/portfolio/history`): los fondos recibidos por
  traspaso ahora aparecen en el gráfico. `first_buy_date` y `running_shares`
  trataban `transfer_in` como si fuera una venta, excluyendo el fondo del
  histórico.
- **_months_held_active**: `transfer_in` ya suma participaciones en lugar de
  restarlas; los meses activos para dividendos de fondos traspasados eran
  incorrectos.
- **dividends-by-security**: `total_cost_eur` incluye ahora el coste heredado
  del `transfer_in`. Antes, un fondo sin compra directa mostraba coste = 0 y
  el yield on cost era infinito.

---

## [1.7.0] — 2026-06-02

### Añadido — Mercados de fondos de inversión

- **Mercados de fondos** (AdminPanel → Catálogo → Mercados). Cada mercado
  puede marcarse como "Mercado de fondos" con un checkbox en el formulario.
  Los mercados de fondos muestran un badge azul "Fondos" en la tabla.
- El catálogo **import/export JSON** incluye `is_fund_market` por mercado
  (compatible hacia atrás: ficheros sin el campo usan `false`).
- Migración Alembic `d4e5f6a1b2c3`: columna `is_fund_market` en `markets`.

### Añadido — Traspasos de fondos (fiscalmente neutros)

- Nuevo endpoint `POST /api/portfolio/transfer`: registra un traspaso entre
  fondos. Consume participaciones del origen (`transfer_out`, sin resultado
  fiscal) y crea participaciones en el destino (`transfer_in`) con el **coste
  de adquisición heredado**, calculado por FIFO en el backend.
- El motor de cálculo incorpora los tipos `transfer_in` / `transfer_out`:
  el traspaso es neutro (no genera ganancia/pérdida) y la plusvalía latente
  se difiere; aflora correctamente en el reembolso final del fondo de destino.
- Migración Alembic `e5f6a1b2c3d4`: amplía `ck_tx_type` con los nuevos tipos.
- Frontend: en la ficha de un fondo, sección "Traspasos" con su historial y
  un formulario para registrar un nuevo traspaso (fondo destino, participaciones
  de salida y de entrada, fecha).

### Cambiado — Informe fiscal y fondos

- Las ganancias de **reembolsos de fondos SÍ entran en el informe fiscal**
  (acumulan en la base del ahorro como las acciones). Se marcan con «(F)» y
  un aviso aclara que la retención del 19 % la practica automáticamente la
  entidad gestora, y que los traspasos no generan resultado fiscal.

### Cambiado — Scheduler

- Los fondos solo refrescan su valor liquidativo **una vez por hora** en el
  job de snapshots en vivo (su NAV es diario; consultarlo cada pocos minutos
  solo añade carga inútil sobre Yahoo). El resto de valores se actualizan en
  cada ejecución; el job nocturno sigue incluyendo a los fondos.

### Corregido (incluye los fixes de revisión previos)

- `_check_currency_consistency` ahora valida cualquier divisa ≠ EUR con
  `exchange_rate=1` (antes solo detectaba USD).
- `total_cost_eur` en dividendos-por-valor acumula en `Decimal` hasta la
  frontera (antes hacía `float()` prematuro).
- El scatter de posiciones cerradas filtra `avg_days_held=0` en escala log.

### Limitaciones conocidas

- El coste heredado del traspaso se calcula y se almacena al crearlo. Editar
  el historial del fondo de origen *anterior* a un traspaso ya registrado no
  recalcula automáticamente ese coste; habría que rehacer el traspaso.
- El coste heredado se conserva en EUR (base fiscal española). Para fondos
  denominados en USD, la P&L latente en la vista de cartera puede mezclar
  divisa; la cifra fiscal es correcta.

## [1.6.20] — 2026-06-01

### Añadido

- **Botón "Listar todos"** en el explorador Yahoo Finance por mercado.
  Trae el listado COMPLETO de acciones del exchange (vía screener de Yahoo,
  `yf.screen` + `EquityQuery`, paginando hasta 2000), marcando cuáles ya
  están en el catálogo y ordenando primero las que faltan por añadir.
  Muestra contador "N valores en el mercado · M sin añadir".
- Nuevo endpoint: `GET /api/admin/markets/{code}/yahoo-list-all` (admin).

### Nota / limitación

- El listado completo usa `EquityQuery`, que devuelve **acciones** (EQUITY).
  Los ETFs y cripto usan otro tipo de query de Yahoo y pueden no aparecer
  en el listado completo; para esos casos sigue disponible la búsqueda por texto.
- Tope de seguridad de 2000 valores por exchange para evitar tiempos excesivos.

## [1.6.19] — 2026-06-01

### Añadido

- **Explorador Yahoo Finance por mercado** (AdminPanel → Catálogo → Mercados).
  Cada mercado puede tener configurado un código de **exchange de Yahoo Finance**
  (ej: `MCE`=Madrid, `NMS`=NasdaqGS, `LSE`=Londres). Cuando está configurado,
  aparece un botón 🔍 en la fila del mercado que abre un buscador filtrado solo
  a ese exchange: muestra qué valores están ya en el catálogo (✓ con su mercado)
  y permite añadir los que faltan con un clic directamente a ese mercado.
- Campo "Exchange Yahoo Finance" en el formulario de creación/edición de mercados.
- Nuevo endpoint: `GET /api/admin/markets/{code}/yahoo-securities?q=<texto>` (admin).
- Migración Alembic `c3d4e5f6a1b2`: añade columna `yahoo_exchange` a `markets`.

### Nota

- Yahoo Finance no ofrece API pública para listar exhaustivamente todos los
  valores de un exchange, por lo que el explorador es un **descubridor asistido**:
  el admin busca por nombre/sector y ve los resultados filtrados a ese exchange.

## [1.6.18] — 2026-06-01

### Añadido

- **Explorador Yahoo Finance** (AdminPanel → Catálogo). Panel plegable con
  un buscador de texto libre (por nombre de empresa o ticker). El backend
  llama a `yf.Search()` y devuelve hasta 15 resultados con ticker, nombre,
  exchange, tipo (EQUITY/ETF/CRYPTO) y divisa. Cada resultado muestra si ya
  está en el catálogo (con el mercado) o un botón "+ Añadir" que pre-rellena
  el formulario de nuevo valor con los datos de Yahoo.
- Nuevo endpoint: `GET /api/admin/securities/search?q=<texto>` (admin).

## [1.6.17] — 2026-06-01

### Añadido / Mejorado

**AdminPanel → Usuarios:**
- Buscador de usuarios (filtra en tiempo real por nombre de usuario).
- Scroll vertical automático cuando hay más de 10 usuarios en la lista.
- Nueva columna **Último acceso**: fecha del último login exitoso del usuario
  (`last_login_at`); muestra "Nunca" si no ha iniciado sesión todavía.
- Nueva columna **Operaciones**: Sí/No según si el usuario tiene al menos
  una transacción registrada.
- Migración Alembic `b2c3d4e5f6a1`: añade columna `last_login_at` a `users`.

**AdminPanel → Catálogo:**
- Buscador por nombre o ticker (filtra en tiempo real).
- Scroll vertical automático cuando hay más de 10 valores en la lista.

## [1.6.16] — 2026-06-01

### Añadido

- **Divisas configurables** (AdminPanel → Configuración). El administrador puede
  añadir divisas adicionales (GBP, CHF, JPY…) más allá de EUR y USD. Las divisas
  nuevas son válidas en transacciones, dividendos, importación CSV y Ghostfolio.
  El tipo de cambio EUR/{divisa} se consulta automáticamente vía Yahoo Finance.
- `PATCH /api/admin/config/currencies` — actualiza la lista de divisas activas.
- `GET /api/config` y `GET /api/admin/config` devuelven `supported_currencies`.
- `GET /api/markets/exchange-rate` acepta ahora el parámetro `currency` (antes
  solo devolvía EUR/USD; ahora admite cualquier par `EUR{code}=X` de Yahoo).
- **Migración Alembic `a1b2c3d4e5f6`**: elimina los CHECK constraints
  `ck_tx_currency` y `ck_div_currency` para permitir divisas no EUR/USD en la BD.

### Cambiado

- **Catálogo de valores** (AdminPanel → Catálogo): pestañas por mercado para
  filtrar los valores. Opción "Todos" para ver el catálogo completo. Al crear
  un valor con un mercado filtrado activo, ese mercado se preselecciona.
- Los formularios de transacción y dividendo en SecurityDetail ahora muestran
  todas las divisas configuradas (no solo EUR/USD) y el auto-fetch del tipo de
  cambio funciona para cualquier divisa no-EUR.

## [1.6.15] — 2026-06-01

### Añadido

- **Importación desde Ghostfolio** (Utilidades). Sube el JSON exportado desde
  Ghostfolio para importar tu historial directamente. Los tipos BUY, SELL y
  DIVIDEND se mapean a compra, venta y dividendo; FEE, INTEREST e ITEM se
  ignoran. El tipo de cambio EUR/USD se resuelve automáticamente desde la base
  de datos BCE o Yahoo Finance como fallback.
- Endpoint nuevo: `POST /api/portfolio/import-ghostfolio`.

### Cambiado

- **AdminPanel reorganizado en pestañas** (Usuarios / Catálogo /
  Configuración / Herramientas). Mejora la navegabilidad del panel de
  administración, que había crecido significativamente.

## [1.6.14] — 2026-06-01

### Añadido

- **Importación CSV de operaciones** (Utilidades). Los usuarios pueden subir
  un CSV con compras, ventas y dividendos de una o varias acciones. Flujo:
  seleccionar fichero → preview en tabla → confirmar importación.
  - Un único CSV con columna `type` (`buy`/`sell`/`dividend`) e `ticker` Yahoo.
  - `gross_amount` del dividendo se calcula automáticamente si se omite.
  - Deduplicación idéntica al backup import: reimportar el mismo fichero
    es seguro.
  - Tickers no encontrados en catálogo generan error por fila sin bloquear
    el resto de la importación.
  - Enlace "Descargar plantilla de ejemplo" junto al botón de importación.
- Endpoint nuevo: `POST /api/portfolio/import-csv` (usuario autenticado).

## [1.6.13] — 2026-05-31

### Añadido

- **Logotipo personalizable de la aplicación.** El administrador puede subir
  una imagen (PNG/JPEG/WebP/SVG, máx. 1 MB) desde ordenador o móvil en
  AdminPanel → Configuración del sistema. El logo aparece en:
  - la pantalla de **login** (junto al nombre y la versión),
  - el **menú principal** (sidebar de escritorio y cabecera móvil),
  - el **icono de la PWA** instalada, mediante un manifest dinámico servido
    por el backend (`GET /manifest.webmanifest`).
- Endpoints nuevos: `PUT`/`DELETE /api/admin/config/logo` (admin),
  `GET /api/config/logo` (público) y `has_logo`/`logo_updated_at` en
  `GET /api/config`.
- Botón "Quitar logo" para revertir a los iconos por defecto.

### Notas

- La imagen se guarda tal cual en la BD (`app_config`), sin reprocesar; se
  recomienda subir una imagen cuadrada para el mejor resultado en la PWA.
- Una PWA ya instalada no actualiza su icono hasta reinstalarla (caché del
  sistema/navegador).

## [1.6.12] — 2026-05-30

### Cambiado

- **Scatter "Rentabilidad vs. tiempo en cartera"**: paletas separadas para
  positivos y negativos, para evitar que una ganancia parezca pérdida.
  - **Positivos**: verde aceituna `#71732B` (peor, 3 %/año) → verde intenso
    `#16a34a` (mejor, 60 %/año).
  - **Negativos**: naranja `#D24608` (menos malo) → rojo oscuro `#7f1d1d`
    (mayor pérdida en mayor tiempo).

---

## [1.6.11] — 2026-05-30

### Cambiado

- **Scatter "Rentabilidad vs. tiempo en cartera"**: el color de cada punto
  ya no depende solo del % de rentabilidad — ahora combina rentabilidad y
  tiempo en cartera:
  - **Positivos**: color basado en la rentabilidad **anualizada** (`pct/años`).
    Operaciones muy rentables en poco tiempo (>=60 %/año) → verde intenso.
    Operaciones poco rentables en mucho tiempo (<=3 %/año) → naranja oscuro.
  - **Negativos**: siempre rojo. Intensidad mayor (rojo más oscuro) cuanto
    mayor sea la pérdida y más tiempo se mantuvo. Pérdidas pequeñas en poco
    tiempo → rojo claro.

---

## [1.6.10] — 2026-05-30

### Añadido

- **Hora real de Yahoo Finance**: el snapshot de precios ahora guarda el
  timestamp del último trade reportado por Yahoo (campo `LiveQuote.quote_time`),
  en lugar de "ahora mismo". Resultado: la marca "Precios actualizados:" en
  Mercados muestra la hora real de la cotización en origen, no la hora local
  del scheduler.
- **Gráfico "Total dividendos por acción"**: al pulsar sobre una barra navega
  al detalle de la acción correspondiente.
- **Scroll vertical >10 filas** aplicado a la tabla de Mercados (SecurityTable)
  y a las tres tablas de SecurityDetail (compras, ventas, dividendos).
  Cabeceras "pegajosas" (sticky) para que sean visibles durante el scroll.

### Corregido

- **Bug**: `get_closed_analytics` ya no puede dividir por cero. Si un dato
  corrupto produce `cost_eur=0` o `shares_sold=0` la posición se omite.
- **Tests**: 13 tests nuevos en `test_portfolio_analytics.py` que cubren los
  endpoints `closed-analytics`, `dividends-by-security` y `markets/exchange-rate`.
  Incluye test de regresión para el bug v1.6.8 (NameError DivRow).

---

## [1.6.9] — 2026-05-30

### Cambiado

- **Mi Cartera — tabla dividendos**: columna "Tiempo en cartera" ahora muestra
  "X año(s) y Y mes(es)" en lugar de un número de meses. Las filas de la tabla
  navegan al detalle de la acción al pulsarlas.
- **Mi Cartera — gráficos**: eliminados subtítulos redundantes "Posiciones abiertas"
  sobre los gráficos de distribución y B/P. Altura del donut igualada al de barras.
- **Scatter dividendos**: título cambiado a "Rentabilidad sobre coste vs. antigüedad".
  Toggle de escala con el mismo estilo que el scatter de posiciones cerradas
  ("Eje X lineal / logarítmico"). En escala log se filtran los valores con
  `years_held = 0` para evitar log(0).
- **Mercados**: nuevo hint "Para registrar operaciones, pulsa sobre el valor deseado."
  El timestamp de precios añade la nota "(puede acumular retraso en origen)".
- **Dashboard**: mensaje vacío simplificado (eliminada la referencia a "Utilidades").
- **Scrollbar horizontal** en tablas ahora usa el color de borde del tema (oscuro
  en tema oscuro, claro en tema claro). Compatible Chrome, Firefox, Safari.
- **Scroll vertical** en tablas con más de 10 filas (posiciones abiertas, cerradas
  y dividendos por acción).

### Corregido

- **Bug**: timeout ausente en llamada a Yahoo Finance para tipo de cambio
  (`GET /markets/exchange-rate`). Ahora se establece timeout=5 s para evitar
  bloqueos indefinidos del servidor.
- **Bug**: `CustomDot` en gráficos scatter usaba `!cx || !cy` (falsy), lo que
  ocultaba puntos con coordenada x=0. Corregido a `typeof cx !== 'number'`.
- **Bug**: null safety en `closedAnalytics` y `dividendsBySec` al cargar Portfolio.

---

## [1.6.8] — 2026-05-29

### Corregido

- **Bug dividendos por acción**: el endpoint `GET /portfolio/dividends-by-security`
  fallaba con `NameError: DivRow` (import local eliminado pero referencia no
  actualizada). La tabla y las gráficas de dividendos ahora aparecen correctamente.

### Cambiado

- **Layout Mi Cartera**: el gráfico de Distribución de cartera se mueve debajo
  de la tabla de posiciones abiertas, en paralelo con el gráfico B/P por acción.
  En pantallas anchas aparecen en la misma fila; en estrechas apilados. La
  Evolución de cartera permanece en la cabecera, ancho completo.
  Ambos gráficos inferiores llevan una etiqueta "Posiciones abiertas".

- **Scatter posiciones cerradas**: nuevo toggle lineal / logarítmico en el eje X
  (días en cartera). Útil cuando hay posiciones muy largas que distorsionan la
  escala. El tick del eje muestra días (d) o años (a) según la magnitud.

- **Scatter yield on cost**: mismo toggle lineal / logarítmico para el eje X
  (años en cartera).

---

## [1.6.7] — 2026-05-29

### Cambiado

- **Rediseño completo de Mi Cartera**: nueva estructura de secciones con orden
  mejorado y gráficas de distribución y evolución en la misma línea horizontal
  (responsive: apiladas en móvil).

### Añadido

- **Gráfico scatter de posiciones cerradas**: eje X = días en cartera (media
  ponderada por lote FIFO), eje Y = rentabilidad (%), tamaño del punto proporcional
  al capital invertido, color gradiente rojo→amarillo→verde por % de ganancia.
  Etiqueta en cada punto con nombre y fecha de la última venta.

- **Tabla de dividendos por acción**: agrupa todos los dividendos cobrados por
  valor (cualquier posición, abierta o cerrada). Columnas: cobros, meses en
  cartera activos, yield medio (%), media por acción, total €.

- **Gráfico de barras horizontal de dividendos**: total cobrado por acción,
  ordenado de mayor a menor.

- **Gráfico scatter yield on cost**: eje X = años con acciones en posesión,
  eje Y = yield anualizado (%), tamaño = total dividendos cobrados. Objetivo:
  identificar posiciones maduras y compras rentables en dividendos.

- Dos nuevos endpoints de backend:
  - `GET /portfolio/closed-analytics` — posiciones cerradas con días medios y % rentabilidad.
  - `GET /portfolio/dividends-by-security` — dividendos agrupados por acción con
    cálculo de months_held (solo periodos activos) y yield on cost.

---

## [1.6.6] — 2026-05-29

### Añadido

- **PWA instalable**: creados los iconos `icon-192.png` e `icon-512.png`
  en `frontend/public/icons/`. Sin ellos los navegadores no mostraban el botón
  de instalación aunque VitePWA estaba correctamente configurado.

### Cambiado

- **Formulario de dividendos — cálculo automático**:
  - Al abrir el formulario de nuevo dividendo, el campo "Acciones" se pre-rellena
    con las acciones actuales de la posición (editable).
  - Cálculo bidireccional entre los tres campos: al modificar cualquiera de
    `shares_at_date`, `gross_per_share` o `gross_amount`, los demás se
    recalculan automáticamente.
  - Validación de coherencia al guardar: `shares × per_share` debe coincidir
    con `gross_amount` (tolerancia de 1 céntimo).

- **Botón "Editar" en detalle de valor**: ya no se muestra para usuarios
  normales. Solo los administradores ven y pueden usar ese botón.

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
