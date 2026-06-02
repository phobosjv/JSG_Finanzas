-- =====================================================================
--  Configuración de SQLite
-- =====================================================================
PRAGMA foreign_keys = ON;   -- SQLite NO aplica claves foráneas si no se activa

-- =====================================================================
--  USUARIOS
-- =====================================================================
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,            -- hash bcrypt/argon2, nunca texto plano
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- =====================================================================
--  CATÁLOGO DE VALORES  (lo introduce el usuario en Utilidades)
-- =====================================================================
CREATE TABLE securities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    isin          TEXT,
    yahoo_ticker  TEXT    NOT NULL,
    google_ticker TEXT,                        -- informativo, no se usa para datos
    market        TEXT    NOT NULL CHECK (market IN ('ibex35','continuo','nasdaq')),
    currency      TEXT    NOT NULL CHECK (currency IN ('EUR','USD')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_securities_ticker ON securities (yahoo_ticker);

-- =====================================================================
--  HISTÓRICO DE COTIZACIONES  (lo rellena el scheduler nocturno)
-- =====================================================================
CREATE TABLE price_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    security_id  INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    date         TEXT    NOT NULL,             -- 'YYYY-MM-DD'
    close        REAL    NOT NULL,             -- cierre en la divisa nativa del valor
    volume       INTEGER,
    UNIQUE (security_id, date)
);

CREATE INDEX idx_history_security_date ON price_history (security_id, date);

-- =====================================================================
--  SNAPSHOT  (última cotización + indicadores precalculados, 1 fila/valor)
-- =====================================================================
CREATE TABLE price_snapshots (
    security_id      INTEGER PRIMARY KEY REFERENCES securities(id) ON DELETE CASCADE,
    last_price       REAL,
    prev_close       REAL,                     -- cierre del día de bolsa anterior
    daily_change_pct REAL,
    min_1y           REAL,
    min_2y           REAL,
    min_5y           REAL,
    max_1y           REAL,
    last_dividend    REAL,                     -- último dividendo por acción conocido
    updated_at       TEXT
);

-- =====================================================================
--  TIPOS DE CAMBIO OFICIALES DEL BCE  (caché, dato congelado)
-- =====================================================================
CREATE TABLE ecb_rates (
    date  TEXT PRIMARY KEY,                    -- 'YYYY-MM-DD'
    rate  REAL NOT NULL                        -- EUR/USD de referencia del BCE
);

-- =====================================================================
--  FAVORITOS  (relación usuario <-> valor)
-- =====================================================================
CREATE TABLE favorites (
    user_id          INTEGER NOT NULL REFERENCES users(id)      ON DELETE CASCADE,
    security_id      INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    target_buy_price REAL,                     -- precio objetivo de compra (divisa nativa)
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, security_id)
);

-- =====================================================================
--  POSICIONES  (un registro por valor que se tiene o se ha tenido)
--  NO almacena nº de acciones ni precio medio: son datos derivados.
-- =====================================================================
CREATE TABLE positions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id)      ON DELETE CASCADE,
    security_id       INTEGER NOT NULL REFERENCES securities(id) ON DELETE RESTRICT,
    target_sell_price REAL,                    -- precio objetivo de venta (divisa nativa)
    notes             TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, security_id)
);

-- =====================================================================
--  TRANSACCIONES  (compras y ventas)
-- =====================================================================
CREATE TABLE transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id   INTEGER NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    -- transfer_in / transfer_out (v1.7.0): traspasos de fondos fiscalmente neutros
    type          TEXT    NOT NULL CHECK (type IN ('buy','sell','transfer_in','transfer_out')),
    date          TEXT    NOT NULL,            -- 'YYYY-MM-DD'
    shares        REAL    NOT NULL CHECK (shares > 0),
    price         REAL    NOT NULL,            -- precio por acción, divisa de la operación
    fee           REAL    NOT NULL DEFAULT 0,  -- comisión, misma divisa
    currency      TEXT    NOT NULL,            -- divisa configurable (multi-divisa v1.6.16)
    exchange_rate REAL    NOT NULL DEFAULT 1,  -- EUR/USD del BCE de 'date'; 1 si EUR
    -- vincula transfer_out + transfer_in de un mismo traspaso para deshacerlo (v1.7.2)
    transfer_group_id TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_tx_position_date ON transactions (position_id, date);

-- =====================================================================
--  DIVIDENDOS
-- =====================================================================
CREATE TABLE dividends (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id      INTEGER NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    date             TEXT    NOT NULL,         -- fecha de cobro
    shares_at_date   REAL    NOT NULL,         -- acciones poseídas ESE día
    gross_per_share  REAL    NOT NULL,         -- bruto por acción, divisa de la operación
    gross_amount     REAL    NOT NULL,         -- bruto total
    withholding_tax  REAL    NOT NULL DEFAULT 0, -- retención en origen
    currency         TEXT    NOT NULL CHECK (currency IN ('EUR','USD')),
    exchange_rate    REAL    NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_div_position_date ON dividends (position_id, date);

-- =====================================================================
--  APORTACIONES PERIÓDICAS (DCA) — planes futuros (v1.7.4)
-- =====================================================================
-- El scheduler crea las compras cuando llega cada fecha. Las aportaciones
-- pasadas se registran como compras directas y no viven aquí.
CREATE TABLE recurring_plans (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id       INTEGER NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    amount_per_period REAL    NOT NULL,          -- importe por aportación, divisa nativa
    fee_per_period    REAL    NOT NULL DEFAULT 0,
    frequency         TEXT    NOT NULL CHECK (frequency IN ('weekly','monthly','quarterly','yearly')),
    start_date        TEXT    NOT NULL,          -- ancla del calendario 'YYYY-MM-DD'
    total_count       INTEGER NOT NULL,          -- nº total de aportaciones del plan
    done_count        INTEGER NOT NULL DEFAULT 0,-- aportaciones ya consumidas (pasadas/ejecutadas)
    currency          TEXT    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_recplan_position ON recurring_plans (position_id);