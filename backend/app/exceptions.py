"""
统一自定义异常
"""


class TradingError(Exception):
    """
    不可恢复的交易错误
    如：配置错误、权限不足、数据不一致
    遇到此类错误应停止相关操作并告警
    """
    pass


class TransientError(Exception):
    """
    可重试的瞬时错误
    如：网络超时、服务暂时不可用
    遇到此类错误可记录日志后继续或稍后重试
    """
    pass


class ConnectionError(TradingError):
    """券商连接错误"""
    pass


class OrderError(TradingError):
    """下单错误"""
    pass
