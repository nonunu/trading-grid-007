"""
券商客户端统一抽象接口
所有券商适配器必须实现此接口
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Callable


class BrokerClient(ABC):
    """
    券商客户端抽象基类

    统一接口规范：
    - 连接管理: connect / disconnect / is_connected
    - 交易时间: is_trading_time
    - 下单撤单: place_order / cancel_order
    - 行情查询: get_latest_price / get_latest_prices
    - 订单查询: query_orders
    - 行情订阅: subscribe_quotes (带回调)
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        连接券商服务
        幂等: 已连接时直接返回 True
        Returns: 是否连接成功
        """
        ...

    @abstractmethod
    def disconnect(self):
        """断开连接，清理资源"""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """当前是否已连接"""
        ...

    @abstractmethod
    def is_trading_time(self) -> bool:
        """当前是否为交易时间"""
        ...

    @abstractmethod
    def place_order(self, stock_code: str, side: str,
                    price: float, qty: int,
                    remark: str = '') -> Optional[str]:
        """
        下单

        Args:
            stock_code: 股票代码
            side: 'BUY' or 'SELL'
            price: 委托价格
            qty: 委托数量
            remark: 备注

        Returns:
            order_id (字符串), 失败返回 None
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        撤单

        Args:
            order_id: 订单ID

        Returns:
            是否成功发起撤单
        """
        ...

    @abstractmethod
    def get_latest_price(self, stock_code: str) -> Optional[float]:
        """
        获取单只股票最新价格

        Returns:
            最新价格, 失败返回 None
        """
        ...

    @abstractmethod
    def get_latest_prices(self, stock_codes: List[str]) -> Dict[str, float]:
        """
        批量获取多只股票最新价格

        Returns:
            {stock_code: last_price}
        """
        ...

    @abstractmethod
    def query_orders(self, stock_code: str) -> Dict[str, Dict]:
        """
        查询指定股票的订单 (含今日未完成 + 历史)

        Returns:
            {order_id: order_info_dict}
            order_info_dict 包含:
                - order_id: str
                - order_status: str (内部统一状态)
                - dealt_avg_price: float
                - dealt_qty: float
                - create_time: str
                - updated_time: str
        """
        ...

    @abstractmethod
    def subscribe_quotes(self, stock_codes: List[str],
                         callback: Callable[[str, float], None]) -> bool:
        """
        订阅实时行情

        Args:
            stock_codes: 股票代码列表
            callback: 回调函数 fn(stock_code, last_price)

        Returns:
            是否订阅成功
        """
        ...

    @abstractmethod
    def unsubscribe_quotes(self):
        """取消所有行情订阅"""
        ...

    def health_check(self) -> bool:
        """
        健康检查，断线时尝试重连
        默认实现: 检查连接状态，断开则重连
        """
        if self.is_connected:
            return True
        return self.connect()
