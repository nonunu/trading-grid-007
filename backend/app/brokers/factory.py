"""
券商工厂
根据股票代码/市场自动选择对应的 Broker 实例
"""

import logging
from typing import Dict, Optional

from app.brokers.base import BrokerClient
from app.constants import Market

logger = logging.getLogger(__name__)

# 全局 Broker 单例
_brokers: Dict[str, BrokerClient] = {}


def get_broker(stock_code: str) -> BrokerClient:
    """
    根据股票代码获取对应的 Broker 实例

    路由规则:
    - HK.*, US.* → FutuBroker
    - *.SH, *.SZ → QmtBroker
    """
    market = Market.from_stock_code(stock_code)

    if market in Market.FUTU_MARKETS:
        return get_futu_broker()
    elif market in Market.A_SHARE_MARKETS:
        return get_qmt_broker()
    else:
        raise ValueError(f"不支持的市场: {market} (stock_code={stock_code})")


def get_futu_broker() -> BrokerClient:
    """获取 FUTU Broker 单例"""
    if 'futu' not in _brokers:
        from app.brokers.futu_broker import FutuBroker
        _brokers['futu'] = FutuBroker()
    return _brokers['futu']


def get_qmt_broker() -> BrokerClient:
    """获取 QMT Broker 单例"""
    if 'qmt' not in _brokers:
        from app.brokers.qmt_broker import QmtBroker
        _brokers['qmt'] = QmtBroker()
    return _brokers['qmt']


def get_all_brokers() -> Dict[str, BrokerClient]:
    """获取所有已创建的 Broker 实例"""
    return _brokers


def get_broker_for_market(market: str) -> Optional[BrokerClient]:
    """根据市场标识获取 Broker"""
    if market in Market.FUTU_MARKETS:
        return get_futu_broker()
    elif market in Market.A_SHARE_MARKETS:
        return get_qmt_broker()
    return None


def connect_all_brokers(markets: set) -> Dict[str, bool]:
    """
    连接所需的所有 Broker

    Args:
        markets: 需要连接的市场集合 (如 {'HK', 'SH'})

    Returns:
        {broker_name: connected_bool}
    """
    results = {}

    need_futu = bool(markets & Market.FUTU_MARKETS)
    need_qmt = bool(markets & Market.A_SHARE_MARKETS)

    if need_futu:
        try:
            broker = get_futu_broker()
            results['futu'] = broker.connect()
        except Exception as e:
            logger.error(f"FUTU Broker 连接异常: {e}")
            results['futu'] = False
        if results['futu']:
            logger.info("FUTU Broker 连接成功")
        else:
            logger.error("FUTU Broker 连接失败")

    if need_qmt:
        try:
            broker = get_qmt_broker()
            results['qmt'] = broker.connect()
        except Exception as e:
            logger.error(f"QMT Broker 连接异常: {e}")
            results['qmt'] = False
        if results['qmt']:
            logger.info("QMT Broker 连接成功")
        else:
            logger.error("QMT Broker 连接失败")

    return results


def disconnect_all_brokers():
    """断开所有 Broker 连接"""
    for name, broker in _brokers.items():
        try:
            broker.disconnect()
            logger.info(f"Broker '{name}' 已断开")
        except Exception as e:
            logger.warning(f"Broker '{name}' 断开异常: {e}")
