"""
FUTU OpenD 券商适配器
适用于港股 (HK) 和美股 (US)
"""

import logging
import functools
import time
from typing import Optional, Dict, List, Callable
from datetime import datetime

from app.brokers.base import BrokerClient
from app.constants import (
    SUBMITTED, FILLED_ALL, FILLED_PART,
    CANCELLED_ALL, CANCELLED_PART, FAILED,
)
from app.config import (
    FUTU_OPEND_HOST, FUTU_OPEND_PORT,
    FUTU_TRADING_PWD, FUTU_RSA_KEY_PATH, TRADING_ENV,
)

logger = logging.getLogger(__name__)

# 延迟导入 futu SDK
ft = None


def _lazy_import_futu():
    """延迟导入 futu SDK，便于在未安装时跳过"""
    global ft
    if ft is None:
        import futu as _ft
        ft = _ft
        # 协议加密
        ft.SysConfig.enable_proto_encrypt(True)
        ft.SysConfig.set_init_rsa_file(FUTU_RSA_KEY_PATH)


def _retry_with_backoff(max_retries=3, base_delay=1.0):
    """指数退避重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt+1}), "
                        f"retry in {delay}s: {e}"
                    )
                    time.sleep(delay)
        return wrapper
    return decorator


# FUTU 订单状态 → 内部统一状态映射
def _map_futu_order_status(futu_status: str) -> str:
    """将 FUTU 订单状态映射为内部统一状态"""
    _lazy_import_futu()
    mapping = {
        ft.OrderStatus.WAITING_SUBMIT: SUBMITTED,
        ft.OrderStatus.SUBMITTING: SUBMITTED,
        ft.OrderStatus.SUBMITTED: SUBMITTED,
        ft.OrderStatus.FILLED_PART: FILLED_PART,
        ft.OrderStatus.FILLED_ALL: FILLED_ALL,
        ft.OrderStatus.CANCELLED_PART: CANCELLED_PART,
        ft.OrderStatus.CANCELLED_ALL: CANCELLED_ALL,
        ft.OrderStatus.FAILED: FAILED,
        ft.OrderStatus.DISABLED: FAILED,
        ft.OrderStatus.DELETED: FAILED,
    }
    return mapping.get(futu_status, SUBMITTED)


class FutuBroker(BrokerClient):
    """
    FUTU OpenD 券商适配器

    支持港股和美股交易
    """

    def __init__(self):
        self._quote_ctx = None
        self._trade_ctx = None
        self._connected = False
        self._today_trade_status = None
        self._quote_callback: Optional[Callable] = None

    def connect(self) -> bool:
        if self._connected and self._quote_ctx and self._trade_ctx:
            return True

        try:
            _lazy_import_futu()

            self._quote_ctx = ft.OpenQuoteContext(
                host=FUTU_OPEND_HOST, port=FUTU_OPEND_PORT
            )
            self._trade_ctx = ft.OpenSecTradeContext(
                host=FUTU_OPEND_HOST, port=FUTU_OPEND_PORT
            )

            # 真实环境需要解锁交易
            trd_env = ft.TrdEnv.REAL if TRADING_ENV == 'REAL' else ft.TrdEnv.SIMULATE
            if trd_env == ft.TrdEnv.REAL and FUTU_TRADING_PWD:
                ret, data = self._trade_ctx.unlock_trade(
                    password=FUTU_TRADING_PWD, is_unlock=True
                )
                if ret != ft.RET_OK:
                    logger.error(f"交易解锁失败: {data}")
                    return False

            self._connected = True
            logger.info("FUTU OpenD 连接成功")
            return True

        except Exception as e:
            logger.error(f"FUTU OpenD 连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        try:
            if self._quote_ctx:
                self._quote_ctx.close()
            if self._trade_ctx:
                self._trade_ctx.close()
        except Exception as e:
            logger.warning(f"FUTU 断开连接异常(忽略): {e}")
        finally:
            self._connected = False
            self._quote_ctx = None
            self._trade_ctx = None
            logger.info("FUTU OpenD 已断开连接")

    @property
    def is_connected(self) -> bool:
        if not self._connected or not self._quote_ctx:
            return False
        try:
            ret, _ = self._quote_ctx.get_global_state()
            return ret == ft.RET_OK
        except Exception:
            self._connected = False
            return False

    def is_trading_time(self) -> bool:
        """判断港股是否在交易时间"""
        if not self._connected:
            return False

        now = datetime.now()
        today = now.date().strftime('%Y-%m-%d')
        current_time = now.time()

        # 缓存当日交易状态
        if (self._today_trade_status is None or
                self._today_trade_status.get('date') != today):
            try:
                ret, data = self._quote_ctx.request_trading_days(
                    market=ft.TradeDateMarket.HK,
                    start=today, end=today
                )
                if ret == ft.RET_OK and len(data) > 0:
                    self._today_trade_status = {
                        'date': today,
                        'type': data[0].get('trade_date_type'),
                    }
                else:
                    self._today_trade_status = {'date': today, 'type': None}
            except Exception:
                self._today_trade_status = {'date': today, 'type': None}

        trade_type = self._today_trade_status.get('type')
        if trade_type is None:
            return False

        morning_start = datetime.strptime('09:00:00', '%H:%M:%S').time()
        morning_end = datetime.strptime('12:00:00', '%H:%M:%S').time()
        afternoon_start = datetime.strptime('13:00:00', '%H:%M:%S').time()
        afternoon_end = datetime.strptime('16:00:00', '%H:%M:%S').time()

        if trade_type == ft.TradeDateType.WHOLE:
            return ((morning_start <= current_time <= morning_end) or
                    (afternoon_start <= current_time <= afternoon_end))
        elif trade_type == ft.TradeDateType.MORNING:
            return morning_start <= current_time <= morning_end
        else:
            return afternoon_start <= current_time <= afternoon_end

    @_retry_with_backoff(max_retries=3)
    def place_order(self, stock_code: str, side: str,
                    price: float, qty: int,
                    remark: str = '') -> Optional[str]:
        if not self._connected:
            return None

        _lazy_import_futu()
        trd_side = ft.TrdSide.BUY if side == 'BUY' else ft.TrdSide.SELL
        trd_env = ft.TrdEnv.REAL if TRADING_ENV == 'REAL' else ft.TrdEnv.SIMULATE

        ret, data = self._trade_ctx.place_order(
            price=price, qty=qty, code=stock_code,
            trd_side=trd_side, order_type=ft.OrderType.NORMAL,
            adjust_limit=0, trd_env=trd_env,
            acc_id=0, acc_index=0, remark=remark,
            time_in_force=ft.TimeInForce.GTC,
            fill_outside_rth=False, aux_price=None,
            trail_type=None, trail_value=None,
            trail_spread=None, session=ft.Session.NONE
        )

        if ret == ft.RET_OK:
            order_id = str(data['order_id'][0])
            logger.info(
                f"FUTU 下单成功: {stock_code} {side} "
                f"price={price} qty={qty} order_id={order_id}"
            )
            return order_id
        else:
            logger.error(
                f"FUTU 下单失败: {stock_code} {side} "
                f"price={price} qty={qty} error={data}"
            )
            return None

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected:
            return False

        _lazy_import_futu()
        trd_env = ft.TrdEnv.REAL if TRADING_ENV == 'REAL' else ft.TrdEnv.SIMULATE
        ret, data = self._trade_ctx.modify_order(
            ft.ModifyOrderOp.CANCEL, order_id, 0, 0, trd_env=trd_env
        )
        if ret == ft.RET_OK:
            logger.info(f"FUTU 撤单成功: order_id={order_id}")
            return True
        else:
            # 已撤/已成交等情况不算真正的错误
            logger.debug(f"FUTU 撤单返回: order_id={order_id}, {data}")
            return False

    def get_latest_price(self, stock_code: str) -> Optional[float]:
        if not self._connected:
            return None
        try:
            ret, data = self._quote_ctx.get_market_snapshot([stock_code])
            if ret == ft.RET_OK and len(data) > 0:
                return float(data.iloc[0]['last_price'])
            return None
        except Exception as e:
            logger.warning(f"FUTU 获取价格失败({stock_code}): {e}")
            return None

    def get_latest_prices(self, stock_codes: List[str]) -> Dict[str, float]:
        if not self._connected or not stock_codes:
            return {}
        try:
            ret, data = self._quote_ctx.get_market_snapshot(stock_codes)
            if ret != ft.RET_OK:
                return {}
            result = {}
            for row in data.to_dict('records'):
                result[row['code']] = float(row['last_price'])
            return result
        except Exception as e:
            logger.warning(f"FUTU 批量获取价格失败: {e}")
            return {}

    def query_orders(self, stock_code: str) -> Dict[str, Dict]:
        """查询指定股票的全部订单 (未完成 + 历史)"""
        if not self._connected:
            return {}

        _lazy_import_futu()
        trd_env = ft.TrdEnv.REAL if TRADING_ENV == 'REAL' else ft.TrdEnv.SIMULATE
        order_dict = {}

        try:
            # 未完成订单
            ret, order_list = self._trade_ctx.order_list_query(
                code=stock_code, trd_env=trd_env, refresh_cache=False
            )
            if ret == ft.RET_OK and len(order_list) > 0:
                for row in order_list.to_dict('records'):
                    order_dict[str(row['order_id'])] = self._normalize_order(row)

            # 历史订单
            from datetime import timedelta
            now = datetime.now()
            start = (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
            end = now.strftime("%Y-%m-%d %H:%M:%S")
            ret, hist = self._trade_ctx.history_order_list_query(
                code=stock_code, start=start, end=end, trd_env=trd_env
            )
            if ret == ft.RET_OK and len(hist) > 0:
                for row in hist.to_dict('records'):
                    order_dict[str(row['order_id'])] = self._normalize_order(row)

        except Exception as e:
            logger.warning(f"FUTU 查询订单失败({stock_code}): {e}")

        return order_dict

    def _normalize_order(self, row: dict) -> dict:
        """将 FUTU 订单数据标准化为内部格式"""
        return {
            'order_id': str(row['order_id']),
            'order_status': _map_futu_order_status(row['order_status']),
            'dealt_avg_price': row.get('dealt_avg_price', 0),
            'dealt_qty': row.get('dealt_qty', 0),
            'create_time': row.get('create_time', ''),
            'updated_time': row.get('updated_time', ''),
        }

    def subscribe_quotes(self, stock_codes: List[str],
                         callback: Callable[[str, float], None]) -> bool:
        """订阅实时行情"""
        if not self._connected or not stock_codes:
            return False

        self._quote_callback = callback

        class QuoteHandler(ft.StockQuoteHandlerBase):
            def __init__(self, outer_callback):
                super().__init__()
                self._cb = outer_callback

            def on_recv_rsp(self, rsp_pb):
                ret_code, data = super().on_recv_rsp(rsp_pb)
                if ret_code != ft.RET_OK:
                    return ft.RET_ERROR, data
                if self._cb:
                    for stock in data.to_dict('records'):
                        self._cb(stock['code'], float(stock['last_price']))
                return ft.RET_OK, data

        self._quote_ctx.set_handler(QuoteHandler(callback))
        ret, data = self._quote_ctx.subscribe(stock_codes, [ft.SubType.QUOTE])
        if ret == ft.RET_OK:
            logger.info(f"FUTU 行情订阅成功: {stock_codes}")
            return True
        else:
            logger.error(f"FUTU 行情订阅失败: {data}")
            return False

    def unsubscribe_quotes(self):
        """取消所有行情订阅"""
        # FUTU SDK 关闭 context 时会自动取消订阅
        pass

    def set_order_callback(self, callback: Callable[[dict], None]):
        """
        设置订单回调 (FUTU 特有)

        callback 接收标准化后的订单字典
        """
        if not self._connected:
            return

        _lazy_import_futu()
        trd_env = ft.TrdEnv.REAL if TRADING_ENV == 'REAL' else ft.TrdEnv.SIMULATE
        broker_self = self

        class OrderHandler(ft.TradeOrderHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret, data = super().on_recv_rsp(rsp_pb)
                if ret == ft.RET_OK and callback:
                    for row in data.to_dict('records'):
                        normalized = broker_self._normalize_order(row)
                        normalized['stock_code'] = row.get('code', '')
                        callback(normalized)
                return ret, data

        self._trade_ctx.set_handler(OrderHandler())
        logger.info("FUTU 订单回调已注册")
