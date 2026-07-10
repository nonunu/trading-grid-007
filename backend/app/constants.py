"""
统一常量定义
包含订单状态、策略方向、市场代码等
"""


# ==================== 订单状态 (内部统一用字符串) ====================

SUBMITTED = 'SUBMITTED'
FILLED_ALL = 'FILLED_ALL'
FILLED_PART = 'FILLED_PART'
CANCELLED_ALL = 'CANCELLED_ALL'
CANCELLED_PART = 'CANCELLED_PART'
FAILED = 'FAILED'
WAITING_SUBMIT = 'WAITING_SUBMIT'
TRANSFERRED = 'TRANSFERRED'

# 成功状态集合 (全部成交 or 部分成交后撤单)
SUCCESS = {FILLED_ALL, FILLED_PART, CANCELLED_PART}

# 终态集合 (不再变化)
TERMINAL = {FILLED_ALL, CANCELLED_ALL, CANCELLED_PART, FAILED, TRANSFERRED}

# 提交中状态集合
SUBMITTED_SET = {SUBMITTED, WAITING_SUBMIT}


# ==================== 策略方向 ====================

class GridDirection:
    ALL = 'ALL'       # 双向 (做多 + 做空)
    MULTI = 'MULTI'   # 仅做多
    SHORT = 'SHORT'   # 仅做空


# ==================== 交易方向 ====================

class TradeSide:
    BUY = 'BUY'
    SELL = 'SELL'


# ==================== 市场代码 ====================

class Market:
    HK = 'HK'    # 港股
    US = 'US'    # 美股
    SH = 'SH'    # 上海
    SZ = 'SZ'    # 深圳

    # A股市场
    A_SHARE_MARKETS = {SH, SZ}
    # 港美股市场
    FUTU_MARKETS = {HK, US}

    @classmethod
    def from_stock_code(cls, stock_code: str) -> str:
        """
        从股票代码推断市场
        HK.08017 -> HK
        US.AAPL  -> US
        600519.SH -> SH
        000001.SZ -> SZ
        """
        if stock_code.startswith('HK.'):
            return cls.HK
        elif stock_code.startswith('US.'):
            return cls.US
        elif stock_code.endswith('.SH'):
            return cls.SH
        elif stock_code.endswith('.SZ'):
            return cls.SZ
        else:
            raise ValueError(f"无法识别股票代码的市场: {stock_code}")

    @classmethod
    def is_a_share(cls, stock_code: str) -> bool:
        """判断是否为A股"""
        return cls.from_stock_code(stock_code) in cls.A_SHARE_MARKETS

    @classmethod
    def is_futu_market(cls, stock_code: str) -> bool:
        """判断是否为港美股 (走FUTU通道)"""
        return cls.from_stock_code(stock_code) in cls.FUTU_MARKETS


# ==================== A 股特殊常量 ====================

# A 股最小交易单位 (手 = 100 股)
A_SHARE_MIN_LOT_SIZE = 100

# A 股交易时段
A_SHARE_TRADING_SESSIONS = [
    ('09:30', '11:30'),
    ('13:00', '15:00'),
]

# 港股交易时段
HK_TRADING_SESSIONS = [
    ('09:30', '12:00'),
    ('13:00', '16:00'),
]
