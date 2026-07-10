#!/bin/bash
# ============================================================
# Trading Grid Unified - 一键部署脚本
# 自动安装后端和前端依赖，初始化配置
#
# 用法:
#   ./setup.sh                 使用 backend/.venv 虚拟环境
#   ./setup.sh <conda_env>     使用指定的 conda 虚拟环境
#   CONDA_ENV=myenv ./setup.sh 同上，通过环境变量指定
#
# 示例:
#   ./setup.sh py39            在 conda 环境 "py39" 中安装后端依赖
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONDA_ENV="${1:-${CONDA_ENV:-}}"

echo "================================================"
echo "  Trading Grid Unified - 一键部署"
echo "================================================"
echo ""

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ==================== 后端部署 ====================

echo "--- 部署后端 ---"

cd "$SCRIPT_DIR/backend"

# 激活 Python 环境
if [ -n "$CONDA_ENV" ]; then
    echo "使用 conda 环境: $CONDA_ENV"

    # 查找并初始化 conda
    if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
    elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
    elif [ -f "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
        source "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    elif command -v conda &>/dev/null; then
        eval "$(conda shell.bash hook)"
    else
        error "未找到 conda，请确认已安装"
    fi

    conda activate "$CONDA_ENV" 2>/dev/null
    if [ $? -ne 0 ]; then
        error "conda 环境 '$CONDA_ENV' 不存在。可用环境: $(conda env list | grep -v '^#')"
    fi

    # 确定 conda 环境内的 python (兼容 Linux/macOS 和 Windows)
    if [ -x "$CONDA_PREFIX/bin/python" ]; then
        PYTHON_BIN="$CONDA_PREFIX/bin/python"
    elif [ -x "$CONDA_PREFIX/python.exe" ]; then
        PYTHON_BIN="$CONDA_PREFIX/python.exe"
    elif [ -x "$CONDA_PREFIX/python" ]; then
        PYTHON_BIN="$CONDA_PREFIX/python"
    else
        error "conda 环境中未找到 python: $CONDA_PREFIX"
    fi
    success "已激活 conda 环境: $CONDA_ENV ($($PYTHON_BIN --version 2>&1))"
else
    # 使用 .venv
    if [ ! -d ".venv" ]; then
        echo "创建 Python 虚拟环境..."
        python3 -m venv .venv
        success "虚拟环境已创建"
    else
        success "虚拟环境已存在"
    fi
    source .venv/bin/activate
    PYTHON_BIN=$(which python3)
    success "已激活 .venv ($($PYTHON_BIN --version 2>&1))"
fi

# 安装后端依赖
echo "安装 Python 依赖..."
"$PYTHON_BIN" -m pip install --upgrade pip -q
"$PYTHON_BIN" -m pip install -r requirements.txt -q
success "Python 依赖安装完成"

# 创建 .env 文件
if [ ! -f ".env" ]; then
    cp .env.example .env
    success ".env 配置文件已创建 (请编辑填入实际配置)"
else
    success ".env 已存在"
fi

# 退出 venv (conda 不需要 deactivate)
if [ -z "$CONDA_ENV" ] && command -v deactivate &>/dev/null; then
    deactivate
fi
echo ""

# ==================== 前端部署 ====================

echo "--- 部署前端 ---"

cd "$SCRIPT_DIR/frontend"

# 加载 nvm
load_nvm() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        source "$NVM_DIR/nvm.sh"
        return 0
    fi
    return 1
}

# 确保 Node >= 18
ensure_node() {
    local NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')

    if [ -n "$NODE_MAJOR" ] && [ "$NODE_MAJOR" -ge 18 ] 2>/dev/null; then
        success "Node.js $(node --version)"
        return 0
    fi

    warn "Node.js 版本不满足要求 (需要 >= 18，当前: $(node --version 2>/dev/null || echo '未安装'))"

    # 尝试通过 nvm 切换
    if load_nvm; then
        if nvm use 18 2>/dev/null || nvm use 20 2>/dev/null || nvm use lts/* 2>/dev/null; then
            success "已切换到 Node.js $(node --version)"
            return 0
        fi
        echo "通过 nvm 安装 Node.js 20..."
        nvm install 20
        nvm use 20
        success "已安装并切换到 Node.js $(node --version)"
        return 0
    fi

    # nvm 不存在，自动安装
    echo "未找到 nvm，正在自动安装..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash 2>/dev/null
    export NVM_DIR="$HOME/.nvm"
    source "$NVM_DIR/nvm.sh"
    echo "通过 nvm 安装 Node.js 20..."
    nvm install 20
    nvm use 20
    success "已安装 nvm + Node.js $(node --version)"
    return 0
}

ensure_node

echo "安装前端依赖..."
npm install
success "前端依赖安装完成"

echo ""

# ==================== 完成 ====================

echo "================================================"
echo -e "${GREEN}  部署完成！${NC}"
echo "================================================"
echo ""
echo "下一步:"
echo "  1. 编辑 backend/.env 填入实际的交易配置"
if [ -n "$CONDA_ENV" ]; then
echo "  2. 运行 ./run.sh $CONDA_ENV 启动应用"
else
echo "  2. 运行 ./run.sh 启动应用"
fi
echo ""
echo "访问地址:"
echo "  前端: http://localhost:5173"
echo "  API:  http://localhost:8000"
echo "  文档: http://localhost:8000/docs"
echo ""
