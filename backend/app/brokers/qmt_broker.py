"""
miniQMT 券商适配器
适用于 A 股 (SH / SZ)
"""

import logging
import threading
from typing import Optional, Dict, List, Callable
from datetime import datetime

from app.brokers.base import BrokerClient
from app.constants import (
    SUBMITTED, FILLED_ALL, FILLED_PART,
    CANCELLED_ALL, CANCELLED_PART, FAILED,
    A_SHARE_TRADING_SESSIONS,
)
from app.config import QMT_PATH, QMT_ACCOUNT, QMT_SESSION_ID, TRADING_ENV

logger = logging.getLogger(__name__)

# 延迟导入 xtquant
xtdata = None
XtQuantTrader = None
XtQuantTraderCallback = None
StockAccount = None
xtconstant = None


def _lazy_import():
    """延迟导入 xtquant 模块"""
    global xtdata, XtQuantTrader, XtQuantTraderCallback, StockAccount, xtconstant
    if xtdata is None:
        from xtquant import xtdata as _xtdata
        from xtquant.xttrader import XtQuantTrader as _XtQuantTrader
        from xtquant.xttrader import XtQuantTraderCallback as _Callback
        from xtquant.xttype import StockAccount as _StockAccount
        from xtquant import xtconstant as _xtconstant

        xtdata = _xtdata
        XtQuantTrader = _XtQuantTrader
        XtQuantTraderCallback = _Callback
        StockAccount = _StockAccount
        xtconstant = _xtconstant


# QMT 订单状态码 → 内部统一状态映射
QMT_STATUS_MAP = {
    48: SUBMITTED,      # 未知
    49: SUBMITTED,      # 已提交
    50: SUBMITTED,      # 已报
    51: SUBMITTED,      # 已报待撤
    52: FILLED_PART,    # 部成待撤
    53: CANCELLED_PART, # 部撤
    54: CANCELLED_ALL,  # 已撤
    55: FILLED_PART,    # 部成
    56: FILLED_ALL,     # 已成
    57: FAILED,         # 废单
}


def _map_qmt_order_status(status_code: int) -> str:
    """将 QMT 订单状态码映射为内部统一状态"""
    return QMT_STATUS_MAP.get(status_code, SUBMITTED)


class QmtBroker(BrokerClient):
    """
    miniQMT 券商适配器

    支持 A 股 (上海/深圳) 交易
    """

    def __init__(self):
        self._trader = None
        self._account = None
        self._connected = False
        self._lock = threading.Lock()
        self._subscribe_seqs: List[int] = []
        self._quote_callback: Optional[Callable] = None
        self._order_callback: Optional[Callable] = None

    def connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True

            try:
                _lazy_import()

                logger.info(f"[QMT] 正在连接 miniQMT...")
                logger.info(f"[QMT]   路径: {QMT_PATH}")
                logger.info(f"[QMT]   账号: {QMT_ACCOUNT}")
                logger.info(f"[QMT]   会话ID: {QMT_SESSION_ID}")
                logger.info(f"[QMT]   环境: {TRADING_ENV}")

                self._trader = XtQuantTrader(QMT_PATH, QMT_SESSION_ID)
                self._account = StockAccount(QMT_ACCOUNT)

                self._trader.start()
                logger.info("[QMT] XtQuantTrader 已启动")

                connect_result = self._trader.connect()
                if connect_result != 0:
                    logger.error(f"[QMT] 交易连接失败, 返回码: {connect_result}")
                    return False
                logger.info("[QMT] 交易连接成功")

                subscribe_result = self._trader.subscribe(self._account)
                if subscribe_result == 0:
                    logger.info(f"[QMT] 账户订阅成功: {QMT_ACCOUNT}")
                else:
                    logger.warning(f"[QMT] 账户订阅返回: {subscribe_result}")

                xtdata.connect()
                logger.info("[QMT] 行情连接成功 (xtdata)")

                self._connected = True
                logger.info("[QMT] miniQMT 全部连接完成 ✓")
                return True

            except Exception as e:
                logger.error(f"[QMT] miniQMT 连接失败: {e}", exc_info=True)
                self._connected = False
                return False

    def disconnect(self):
        with self._lock:
            # 取消行情订阅
            if xtdata:
                for seq in self._subscribe_seqs:
                    try:
                        xtdata.unsubscribe_quote(seq)
                    except Exception:
                        pass
            self._subscribe_seqs.clear()

            try:
                if self._trader:
                    self._trader.stop()
                    self._trader = None
            except Exception as e:
                logger.warning(f"QMT 断开异常: {e}")
            self._connected = False
            logger.info("miniQMT 已断开连接")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def is_trading_time(self) -> bool:
        """判断 A 股是否在交易时间"""
        now = datetime.now()
        current_time = now.strftime('%H:%M')

        # 简单判断: 周末非交易日
        if now.weekday() >= 5:
            return False

        for start, end in A_SHARE_TRADING_SESSIONS:
            if start <= current_time <= end:
                return True
        return False

    def place_order(self, stock_code: str, side: str,
                    price: float, qty: int,
                    remark: str = '') -> Optional[str]:
        if not self._connected:
            logger.error(f"[QMT] 下单失败: 未连接")
            return None

        try:
            _lazy_import()
            order_type = (xtconstant.STOCK_BUY if side == 'BUY'
                         else xtconstant.STOCK_SELL)

            # 确保类型正确 (miniQMT 对类型敏感，numpy int64/float 会导致返回 -1)
            price = float(price)
            qty = int(qty)

            logger.info(f"[QMT] 下单请求: {stock_code} {side} price={price} qty={qty}")

            order_id = self._trader.order_stock(
                self._account, stock_code, order_type,
                qty, xtconstant.FIX_PRICE, price,
                'grid', remark
            )

            if order_id and order_id > 0:
                logger.info(
                    f"[QMT] 下单成功: {stock_code} {side} "
                    f"price={price} qty={qty} order_id={order_id}"
                )
                return str(order_id)
            else:
                # -1 通常表示: 未连接/参数错误/账户未订阅/交易时间外
                logger.error(
                    f"[QMT] 下单失败: {stock_code} {side} "
                    f"price={price} qty={qty} result={order_id} "
                    f"(可能原因: miniQMT未登录/账户未订阅/非交易时间/参数异常)"
                )
                # 尝试检测连接状态
                try:
                    connect_status = self._trader.connect()
                    logger.error(f"[QMT] 当前连接状态检测: connect()={connect_status}")
                except Exception:
                    pass
                return None

        except Exception as e:
            logger.error(f"QMT 下单异常: {stock_code} {e}", exc_info=True)
            return None

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected:
            return False

        try:
            result = self._trader.cancel_order_stock(
                self._account, int(order_id)
            )
            if result == 0:
                logger.info(f"QMT 撤单成功: order_id={order_id}")
                return True
            else:
                logger.warning(f"QMT 撤单失败: order_id={order_id}, result={result}")
                return False
        except Exception as e:
            logger.error(f"QMT 撤单异常: order_id={order_id}, {e}")
            return False

    def get_latest_price(self, stock_code: str) -> Optional[float]:
        if not self._connected:
            return None
        try:
            _lazy_import()
            data = xtdata.get_market_data_ex(
                [], [stock_code], period='tick', count=1
            )
            if stock_code in data and len(data[stock_code]) > 0:
                tick = data[stock_code].iloc[-1]
                return float(tick['lastPrice'])
            return None
        except Exception as e:
            logger.warning(f"QMT 获取价格失败({stock_code}): {e}")
            return None

    def get_latest_prices(self, stock_codes: List[str]) -> Dict[str, float]:
        if not self._connected or not stock_codes:
            return {}
        try:
            _lazy_import()
            result = {}
            data = xtdata.get_market_data_ex(
                [], stock_codes, period='tick', count=1
            )
            for code in stock_codes:
                if code in data and len(data[code]) > 0:
                    tick = data[code].iloc[-1]
                    result[code] = float(tick['lastPrice'])
            return result
        except Exception as e:
            logger.warning(f"QMT 批量获取价格失败: {e}")
            return {}

    def query_orders(self, stock_code: str) -> Dict[str, Dict]:
        """查询指定股票的所有委托"""
        if not self._connected:
            return {}

        try:
            orders = self._trader.query_stock_orders(self._account)
            if not orders:
                return {}

            result = {}
            for order in orders:
                if order.stock_code == stock_code:
                    result[str(order.order_id)] = {
                        'order_id': str(order.order_id),
                        'order_status': _map_qmt_order_status(order.order_status),
                        'dealt_avg_price': getattr(order, 'traded_price', 0),
                        'dealt_qty': getattr(order, 'traded_volume', 0),
                        'create_time': getattr(order, 'order_time', ''),
                        'updated_time': '',
                    }
            return result
        except Exception as e:
            logger.warning(f"QMT 查询委托失败({stock_code}): {e}")
            return {}

    def subscribe_quotes(self, stock_codes: List[str],
                         callback: Callable[[str, float], None]) -> bool:
        """订阅实时行情"""
        if not self._connected or not stock_codes:
            return False

        self._quote_callback = callback
        _lazy_import()

        def _on_quote(datas):
            if not self._quote_callback:
                return
            for code, tick_data in datas.items():
                # tick_data 格式: {field: [values...]}，取最后一个值
                if isinstance(tick_data, dict):
                    last_price_list = tick_data.get('lastPrice')
                    if isinstance(last_price_list, list) and last_price_list:
                        price = last_price_list[-1]
                    elif isinstance(last_price_list, (int, float)):
                        price = last_price_list
                    else:
                        continue
                elif isinstance(tick_data, list) and tick_data:
                    # 某些版本可能直接传 list of tick
                    last_tick = tick_data[-1] if tick_data else {}
                    price = last_tick.get('lastPrice', 0) if isinstance(last_tick, dict) else 0
                else:
                    continue
                if price and price > 0:
                    self._quote_callback(code, float(price))

        for code in stock_codes:
            seq = xtdata.subscribe_quote(code, period='tick', callback=_on_quote)
            self._subscribe_seqs.append(seq)

        logger.info(f"[QMT] 行情订阅完成: {stock_codes} (共 {len(stock_codes)} 只)")
        return True

    def unsubscribe_quotes(self):
        """取消所有行情订阅"""
        if xtdata:
            for seq in self._subscribe_seqs:
                try:
                    xtdata.unsubscribe_quote(seq)
                except Exception:
                    pass
        self._subscribe_seqs.clear()

    def set_order_callback(self, callback: Callable[[dict], None]):
        """
        注册 QMT 交易回调

        callback 接收标准化后的订单字典
        """
        if not self._connected:
            return

        _lazy_import()
        broker_self = self

        class GridTradeCallback(XtQuantTraderCallback):
            def on_stock_order(self, order):
                if callback:
                    normalized = {
                        'order_id': str(order.order_id),
                        'stock_code': order.stock_code,
                        'order_status': _map_qmt_order_status(order.order_status),
                        'dealt_avg_price': getattr(order, 'traded_price', 0),
                        'dealt_qty': getattr(order, 'traded_volume', 0),
                        'create_time': '',
                        'updated_time': '',
                    }
                    callback(normalized)

            def on_stock_trade(self, trade):
                logger.debug(
                    f"QMT 成交回报: {trade.stock_code} "
                    f"qty={trade.traded_volume} price={trade.traded_price}"
                )

            def on_order_error(self, order_id, error_id, error_msg):
                logger.error(
                    f"QMT 委托失败: order_id={order_id}, "
                    f"error={error_id}, msg={error_msg}"
                )

            def on_cancel_error(self, order_id, error_id, error_msg):
                logger.warning(
                    f"QMT 撤单失败: order_id={order_id}, "
                    f"error={error_id}, msg={error_msg}"
                )

        self._trader.register_callback(GridTradeCallback())
        logger.info("[QMT] 交易回调已注册 (委托回报/成交回报/异常回报)")

    def start_xtdata_daemon(self):
        """启动 xtdata 数据接收线程"""
        _lazy_import()
        xtdata.run()
        logger.info("[QMT] xtdata 数据接收线程已启动，开始监控行情推送")
