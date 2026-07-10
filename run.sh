#!/bin/bash
# ============================================================
# Trading Grid Unified - 启动脚本
# 同时启动后端 (FastAPI) 和前端 (Vite Dev Server)
#
# 用法:
#   ./run.sh                   使用 backend/.venv 或系统 Python
#   ./run.sh <conda_env>       使用指定的 conda 虚拟环境
#   CONDA_ENV=myenv ./run.sh   同上，通过环境变量指定
#
# 示例:
#   ./run.sh trading           激活 conda 环境 "trading" 后启动
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ==================== 用户配置 ====================
# 指定 conda 虚拟环境名称 (留空则使用 backend/.venv 或系统 Python)
# 用法:
#   ./run.sh                  # 使用默认 (.venv 或系统 Python)
#   ./run.sh trading          # 使用 conda 环境 "trading"
#   CONDA_ENV=trading ./run.sh  # 同上，通过环境变量指定
CONDA_ENV="${1:-${CONDA_ENV:-}}"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# PID 文件
BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"

# ==================== 清理函数 ====================

cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止服务...${NC}"

    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            kill "$BACKEND_PID" 2>/dev/null
            echo -e "${GREEN}[OK]${NC} 后端已停止 (PID: $BACKEND_PID)"
        fi
        rm -f "$BACKEND_PID_FILE"
    fi

    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            kill "$FRONTEND_PID" 2>/dev/null
            echo -e "${GREEN}[OK]${NC} 前端已停止 (PID: $FRONTEND_PID)"
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi

    # 清理子进程
    jobs -p | xargs -r kill 2>/dev/null
    echo -e "${GREEN}所有服务已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ==================== 停止旧进程 ====================

stop_existing() {
    if [ -f "$BACKEND_PID_FILE" ]; then
        OLD_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "${YELLOW}停止旧的后端进程 (PID: $OLD_PID)${NC}"
            kill "$OLD_PID" 2>/dev/null
            sleep 1
        fi
        rm -f "$BACKEND_PID_FILE"
    fi

    if [ -f "$FRONTEND_PID_FILE" ]; then
        OLD_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "${YELLOW}停止旧的前端进程 (PID: $OLD_PID)${NC}"
            kill "$OLD_PID" 2>/dev/null
            sleep 1
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi
}

# ==================== 启动 ====================

echo "================================================"
echo "  Trading Grid Unified - 启动"
echo "================================================"
echo ""

stop_existing

# --- 启动后端 ---

echo "--- 启动后端 (FastAPI) ---"

BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_PATH="$BACKEND_DIR/.venv"

# Python 环境激活优先级: conda 环境 > backend/.venv > 系统 Python
if [ -n "$CONDA_ENV" ]; then
    # 使用指定的 conda 环境
    echo "激活 conda 环境: $CONDA_ENV"

    # 查找 conda 初始化脚本
    if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
    elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
    elif [ -f "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
        source "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    elif command -v conda &>/dev/null; then
        eval "$(conda shell.bash hook)"
    else
        echo -e "${RED}[ERROR]${NC} 未找到 conda，请确认已安装"
        exit 1
    fi

    conda activate "$CONDA_ENV" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR]${NC} conda 环境 '$CONDA_ENV' 不存在"
        echo "可用环境:"
        conda env list
        exit 1
    fi
    echo -e "${GREEN}[OK]${NC} 已激活 conda 环境: $CONDA_ENV"

elif [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
    echo -e "${GREEN}[OK]${NC} 已激活 .venv ($(python3 --version))"
else
    echo -e "${YELLOW}虚拟环境不存在，使用系统 Python ($(python3 --version))${NC}"
fi

if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo -e "${YELLOW}未找到 .env 文件，复制默认配置${NC}"
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
fi

cd "$BACKEND_DIR"

# 确定当前 Python 解释器路径
# conda 环境中可能只有 python 而没有 python3 链接，优先用 $CONDA_PREFIX/bin/python
if [ -n "$CONDA_PREFIX" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
    PYTHON_BIN="$CONDA_PREFIX/bin/python"
elif command -v python &>/dev/null && python -c "import sys; sys.exit(0 if sys.prefix != sys.base_prefix or 'conda' in sys.prefix else 1)" 2>/dev/null; then
    PYTHON_BIN=$(which python)
else
    PYTHON_BIN=$(which python3)
fi
echo -e "  Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

# 检查 uvicorn 是否可用，未安装则自动安装到当前环境
if ! "$PYTHON_BIN" -c "import uvicorn" 2>/dev/null; then
    echo -e "${YELLOW}uvicorn 未安装，正在自动安装依赖到当前环境...${NC}"
    "$PYTHON_BIN" -m pip install fastapi "uvicorn[standard]" python-dotenv pandas numpy pydantic websockets -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR]${NC} 依赖安装失败"
        exit 1
    fi
    success_msg="依赖安装完成"
    echo -e "${GREEN}[OK]${NC} $success_msg"
fi

"$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
echo -e "${GREEN}[OK]${NC} 后端启动成功 (PID: $BACKEND_PID, Port: 8000)"
echo ""

# --- 启动前端 ---

echo "--- 启动前端 (Vite) ---"

FRONTEND_DIR="$SCRIPT_DIR/frontend"

# 加载 nvm (如果存在)
load_nvm() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        source "$NVM_DIR/nvm.sh"
        return 0
    fi
    return 1
}

# 确保 Node >= 18 可用，否则通过 nvm 自动安装
ensure_node() {
    local NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')

    # 已有合适版本
    if [ -n "$NODE_MAJOR" ] && [ "$NODE_MAJOR" -ge 18 ] 2>/dev/null; then
        echo -e "${GREEN}[OK]${NC} Node.js $(node --version)"
        return 0
    fi

    echo -e "${YELLOW}Node.js 版本不满足要求 (需要 >= 18，当前: $(node --version 2>/dev/null || echo '未安装'))${NC}"

    # 尝试加载 nvm 并切换到已有的 18+ 版本
    if load_nvm; then
        # 尝试 use 已安装的 18+
        if nvm use 18 2>/dev/null || nvm use 20 2>/dev/null || nvm use lts/* 2>/dev/null; then
            echo -e "${GREEN}[OK]${NC} 已切换到 Node.js $(node --version)"
            return 0
        fi

        # 没有可用版本，自动安装
        echo -e "${YELLOW}正在通过 nvm 安装 Node.js 20...${NC}"
        nvm install 20
        nvm use 20
        echo -e "${GREEN}[OK]${NC} 已安装并切换到 Node.js $(node --version)"
        return 0
    fi

    # nvm 不存在，自动安装 nvm + Node
    echo -e "${YELLOW}未找到 nvm，正在自动安装...${NC}"
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash 2>/dev/null
    export NVM_DIR="$HOME/.nvm"
    source "$NVM_DIR/nvm.sh"

    echo -e "${YELLOW}正在通过 nvm 安装 Node.js 20...${NC}"
    nvm install 20
    nvm use 20
    echo -e "${GREEN}[OK]${NC} 已安装 nvm + Node.js $(node --version)"
    return 0
}

ensure_node

# 切换 Node 版本后 node_modules 可能不兼容，需要重新安装
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "安装前端依赖..."
    cd "$FRONTEND_DIR"
    npm install
    echo -e "${GREEN}[OK]${NC} 前端依赖安装完成"
else
    # 检查 node_modules 是否与当前 Node 版本兼容 (检查 rollup 平台绑定)
    if [ ! -d "$FRONTEND_DIR/node_modules/@rollup/rollup-darwin-arm64" ] && [ "$(uname -m)" = "arm64" ]; then
        echo -e "${YELLOW}node_modules 与当前 Node/平台不兼容，重新安装...${NC}"
        cd "$FRONTEND_DIR"
        rm -rf node_modules package-lock.json
        npm install
        echo -e "${GREEN}[OK]${NC} 前端依赖重新安装完成"
    fi
fi

cd "$FRONTEND_DIR"
npx vite --port 5173 --host &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"
echo -e "${GREEN}[OK]${NC} 前端启动成功 (PID: $FRONTEND_PID, Port: 5173)"

echo ""
echo "================================================"
echo -e "${GREEN}  启动完成！${NC}"
echo "================================================"
echo ""
echo "  前端: http://localhost:5173"
echo "  API:  http://localhost:8000"
echo "  文档: http://localhost:8000/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo ""

# 等待子进程
wait
