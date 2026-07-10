-- Trading-Grid Unified 数据库 Schema
-- 统一网格交易系统 (A股 miniQMT + 港美股 FUTU OpenD)

-- Schema 版本表
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 股票网格配置表
CREATE TABLE IF NOT EXISTS grid_configs (
    stock_code TEXT PRIMARY KEY,          -- 股票代码 (HK.08017, US.AAPL, 600519.SH, 000001.SZ)
    market TEXT NOT NULL DEFAULT 'HK',    -- 市场: HK, US, SH, SZ
    direction TEXT NOT NULL DEFAULT 'ALL', -- 策略方向: ALL/MULTI/SHORT
    buy_cell_count INTEGER DEFAULT 3,     -- 每次最多下买单数量
    sell_cell_count INTEGER DEFAULT 3,    -- 每次最多下卖单数量
    order_query_period INTEGER DEFAULT 4, -- 历史订单查询天数
    place_order_scope REAL DEFAULT 0.1,   -- 下单价格偏离阈值
    last_price REAL,                      -- 最新价格
    min_lot_size INTEGER DEFAULT 1,       -- 最小交易单位 (A股=100, 港股按股票)
    is_active INTEGER DEFAULT 1,          -- 是否启用 (1=是, 0=否)
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 网格单元格表
CREATE TABLE IF NOT EXISTS grid_cells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,             -- 股票代码
    strategy_type TEXT NOT NULL,          -- 策略类型: MULTI/SHORT
    cell_type TEXT NOT NULL,              -- 单元格类型: BUY/SELL
    parent_cell_id INTEGER,              -- 父单元格ID (NULL=父单元格自身)
    price REAL NOT NULL,                 -- 网格价格
    qty INTEGER NOT NULL,                -- 下单数量
    allocated_qty REAL DEFAULT 0,        -- 已分配数量
    order_id TEXT,                       -- 券商订单 ID
    order_status TEXT,                   -- 订单状态 (统一内部状态)
    dealt_avg_price REAL,                -- 成交均价
    dealt_qty REAL DEFAULT 0,            -- 成交数量
    create_time TEXT,                    -- 订单创建时间
    updated_time TEXT,                   -- 订单更新时间
    updated_at TEXT,                     -- 记录更新时间
    FOREIGN KEY (stock_code) REFERENCES grid_configs(stock_code),
    FOREIGN KEY (parent_cell_id) REFERENCES grid_cells(id)
);

-- 网格单元格索引
CREATE INDEX IF NOT EXISTS idx_cells_stock_strategy
    ON grid_cells(stock_code, strategy_type);
CREATE INDEX IF NOT EXISTS idx_cells_parent
    ON grid_cells(parent_cell_id);
CREATE INDEX IF NOT EXISTS idx_cells_order_id
    ON grid_cells(order_id);

-- 成交记录表
CREATE TABLE IF NOT EXISTS filled_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    strategy_type TEXT NOT NULL,          -- MULTI/SHORT
    cell_id INTEGER,                     -- 关联的子单元格ID
    cell_price REAL,                     -- 单元格价格
    buy_order_id TEXT,                   -- 买入订单ID
    buy_dealt_avg_price REAL,            -- 买入成交均价
    buy_dealt_qty REAL,                  -- 买入成交数量
    buy_create_time TEXT,
    buy_updated_time TEXT,
    sell_order_id TEXT,                  -- 卖出订单ID
    sell_dealt_avg_price REAL,           -- 卖出成交均价
    sell_dealt_qty REAL,                 -- 卖出成交数量
    sell_create_time TEXT,
    sell_updated_time TEXT,
    buy_amount REAL,                     -- 买入金额
    sell_amount REAL,                    -- 卖出金额
    profit_diff REAL,                    -- 利润差
    completed_at TEXT,                   -- 完成时间
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 成交记录索引
CREATE INDEX IF NOT EXISTS idx_filled_stock
    ON filled_orders(stock_code, strategy_type);
CREATE INDEX IF NOT EXISTS idx_filled_completed
    ON filled_orders(completed_at);

-- 自救转换记录表
CREATE TABLE IF NOT EXISTS rescue_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    source_strategy TEXT NOT NULL,        -- 来源策略 (MULTI)
    target_strategy TEXT NOT NULL,        -- 目标策略 (SHORT)
    source_cell_id INTEGER NOT NULL,     -- 来源单元格ID
    target_cell_id INTEGER,              -- 目标单元格ID
    transfer_qty REAL NOT NULL,          -- 转移数量
    transfer_price REAL NOT NULL,        -- 转移价格
    -- 快照信息（用于还原）
    snapshot_order_id TEXT,
    snapshot_order_status TEXT,
    snapshot_dealt_avg_price REAL,
    snapshot_dealt_qty REAL,
    status TEXT DEFAULT 'ACTIVE',        -- ACTIVE / RESTORED
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    restored_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_rescue_stock
    ON rescue_records(stock_code, status);
