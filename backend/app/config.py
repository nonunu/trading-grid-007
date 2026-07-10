"""
统一配置加载模块
从 .env 文件加载环境变量，提供全局配置
"""

import os
import logging
import logging.config
from os import path
from dotenv import load_dotenv

# 项目根目录 (backend/)
BASE_DIR = path.dirname(path.dirname(path.abspath(__file__)))

# 加载 .env
load_dotenv(path.join(BASE_DIR, '.env'))

# ==================== 日志配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# ==================== 通用配置 ====================

TRADING_ENV = os.getenv('TRADING_ENV', 'SIMULATE').upper()
DB_PATH = os.getenv('DB_PATH', path.join(BASE_DIR, 'trading_grid.db'))

# ==================== FUTU OpenD 配置 (港/美股) ====================

FUTU_OPEND_HOST = os.getenv('FUTU_OPEND_HOST', '127.0.0.1')
FUTU_OPEND_PORT = int(os.getenv('FUTU_OPEND_PORT', '11111'))
FUTU_TRADING_PWD = os.getenv('FUTU_TRADING_PWD', '')
FUTU_RSA_KEY_PATH = os.getenv('FUTU_RSA_KEY_PATH', path.join(BASE_DIR, 'futu_opend_rsa.key'))

# ==================== miniQMT 配置 (A股) ====================

QMT_PATH = os.getenv('QMT_PATH', r'D:\QMT\userdata_mini')
QMT_ACCOUNT = os.getenv('QMT_ACCOUNT', '')
QMT_SESSION_ID = int(os.getenv('QMT_SESSION_ID', '999999'))

logger.info(f"配置加载完成: TRADING_ENV={TRADING_ENV}, DB_PATH={DB_PATH}")
