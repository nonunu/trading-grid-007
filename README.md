# Trading Grid Unified - 统一网格交易系统

A股(miniQMT) + 港美股(FUTU OpenD) 统一网格交易系统，基于 FastAPI + Vue 3 构建。

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                  Vue 3 Frontend                      │
│         (TypeScript + Element Plus)                  │
│    Dashboard │ 策略信息 │ 管理维护                      │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────┐
│                FastAPI Backend                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ API 路由  │  │ 交易引擎  │  │ Broker 适配器层   │  │
│  └──────────┘  └──────────┘  └────────┬─────────┘  │
│                                        │            │
│                              ┌─────────┴─────────┐  │
│                              │                   │  │
│                        FutuBroker          QmtBroker │
│                        (港/美股)            (A股)    │
└─────────────────────────────────────────────────────┘
                       │
              SQLite (trading_grid.db)
```

## 功能特性

- **多市场支持**: 港股(HK)、美股(US)、A股(SH/SZ) 统一管理
- **自动路由**: 根据股票代码自动选择对应券商通道
- **1:N 网格模型**: 支持父子单元格买卖比配置
- **双向策略**: 做多(MULTI) / 做空(SHORT) / 双向(ALL)
- **实时行情**: WebSocket 推送最新价格和系统状态
- **Web 管理界面**: 替代原 PyQt5 桌面应用，支持远程访问

## 环境要求

- Python >= 3.10
- Node.js >= 18 (前端构建)
- FUTU OpenD (港美股交易需要)
- miniQMT (A股交易需要)

## 快速开始

### 一键部署

```bash
chmod +x setup.sh run.sh
./setup.sh py39
```

### 启动应用

```bash
./run.sh py39
```

启动后访问:
- 前端界面: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 脚本使用说明

### setup.sh - 一键部署

自动安装后端 Python 依赖和前端 Node 依赖。支持指定 conda 环境或使用默认 `.venv`。

```bash
# 使用 conda 环境 (推荐)
./setup.sh py39              # 后端依赖安装到 conda 环境 py39

# 使用环境变量指定
CONDA_ENV=py39 ./setup.sh

# 使用默认 .venv (不指定参数时自动创建 backend/.venv)
./setup.sh
```

脚本执行的操作：
1. 激活指定的 Python 环境 (conda 或 .venv)
2. `pip install -r requirements.txt` 安装后端依赖
3. 复制 `.env.example` → `.env`（如果不存在）
4. 检查 Node.js 版本，不足 18 时自动通过 nvm 安装 Node 20
5. `npm install` 安装前端依赖

### run.sh - 启动应用

同时启动后端 (FastAPI:8000) 和前端 (Vite:5173)，按 Ctrl+C 统一停止。

```bash
# 使用 conda 环境
./run.sh py39                # 激活 py39 后启动后端

# 使用环境变量指定
CONDA_ENV=py39 ./run.sh

# 使用默认环境 (backend/.venv 或系统 Python)
./run.sh
```

脚本执行的操作：
1. 停止已有的旧进程（如果存在）
2. 激活 Python 环境，确认 uvicorn 可用（缺失时自动安装）
3. 启动后端: `python -m uvicorn app.main:app --port 8000`
4. 检查 Node.js 版本，不足 18 时通过 nvm 自动切换/安装
5. 检查 `node_modules` 兼容性，必要时重新 `npm install`
6. 启动前端: `npx vite --port 5173`

Python 环境选择优先级：
```
conda 环境 (指定参数时) > backend/.venv > 系统 Python
```

> **注意**: conda 环境中 `python` 和 `python3` 可能指向不同解释器。
> 脚本使用 `$CONDA_PREFIX/bin/python` 确保指向 conda 环境内的正确 Python。

## 手动部署

### 1. 后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写实际配置

# 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. 前端

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build
```

## 配置说明

编辑 `backend/.env`:

```env
# 通用
TRADING_ENV=SIMULATE          # SIMULATE 或 REAL

# FUTU OpenD (港美股)
FUTU_OPEND_HOST=127.0.0.1
FUTU_OPEND_PORT=11111
FUTU_TRADING_PWD=你的交易密码
FUTU_RSA_KEY_PATH=./futu_opend_rsa.key

# miniQMT (A股)
QMT_PATH=D:\QMT\userdata_mini
QMT_ACCOUNT=你的账号
QMT_SESSION_ID=999999
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/configs` | 获取所有股票配置 |
| POST | `/api/configs` | 添加股票配置 |
| PUT | `/api/configs/{code}` | 更新配置 |
| DELETE | `/api/configs/{code}` | 删除配置 |
| GET | `/api/cells` | 获取网格单元格 |
| POST | `/api/cells` | 创建单元格 |
| DELETE | `/api/cells/{id}` | 删除单元格 |
| POST | `/api/cells/{id}/clear` | 重置订单信息 |
| GET | `/api/engine/status` | 引擎状态 |
| POST | `/api/engine/start` | 启动引擎 |
| POST | `/api/engine/stop` | 停止引擎 |
| GET | `/api/dashboard/summary` | 仪表盘汇总 |
| GET | `/api/dashboard/filled_orders` | 成交记录 |
| WS | `/ws` | 实时数据推送 |

## 股票代码规范

| 市场 | 格式 | 示例 | 券商通道 |
|------|------|------|----------|
| 港股 | HK.XXXXX | HK.08017 | FUTU OpenD |
| 美股 | US.XXXX | US.AAPL | FUTU OpenD |
| 上海 | XXXXXX.SH | 600519.SH | miniQMT |
| 深圳 | XXXXXX.SZ | 000001.SZ | miniQMT |

## 项目结构

```
trading-grid-unified/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI 路由
│   │   ├── brokers/        # 券商适配器 (FUTU/QMT)
│   │   ├── engine/         # 交易引擎和策略
│   │   ├── models/         # Pydantic 数据模型
│   │   ├── config.py       # 配置加载
│   │   ├── constants.py    # 常量定义
│   │   ├── database.py     # SQLite 数据库层
│   │   ├── exceptions.py   # 自定义异常
│   │   ├── main.py         # FastAPI 入口
│   │   └── schema.sql      # 数据库表结构
│   ├── .env.example
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # Axios API 封装
│   │   ├── components/     # 通用组件
│   │   ├── composables/    # Vue Composables
│   │   ├── router/         # Vue Router
│   │   ├── stores/         # Pinia 状态管理
│   │   ├── views/          # 页面视图
│   │   ├── App.vue         # 根组件
│   │   └── main.ts         # 入口
│   ├── package.json
│   └── vite.config.ts
├── setup.sh                # 一键部署脚本
├── run.sh                  # 启动脚本
└── README.md
```

## 从旧项目迁移

如果你之前使用 `trading-grid_01` (港股) 或 `trading_grid_sh` (A股)，数据库可以直接复制:

```bash
# 复制港股数据
cp trading-grid_01/trading_grid.db backend/trading_grid.db

# 或复制A股数据
cp trading_grid_sh/trading_grid.db backend/trading_grid.db
```

新系统兼容旧的数据库表结构，首次启动时会自动添加 `market` 等新字段。

## License

Private - Internal Use Only
