"""
统一交易引擎
管理多个 Broker、策略实例，调度行情回调和订单回调
"""

import logging
import threading
from typing import Dict, Optional

from app.constants import GridDirection, Market, FILLED_ALL, CANCELLED_PART
from app.database import GridDatabase
from app.brokers import (
    BrokerClient, get_broker, get_broker_for_market,
    connect_all_brokers, disconnect_all_brokers,
)
from app.engine.grid import DatabaseGrid
from app.engine.multi_strategy import MultiStrategy
from app.engine.short_strategy import ShortStrategy
from app.exceptions import TransientError

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    统一交易引擎

    管理:
    - 多个 Broker (FUTU + QMT)
    - 所有股票的策略实例
    - 行情订阅和回调
    - 订单回调处理
    """

    def __init__(self, db: GridDatabase):
        self.db = db
        self.running = False
        self._initialized = False
        self._state_lock = threading.Lock()

        # 股票配置和策略
        self._stock_grids: Dict[str, dict] = {}
        self._stock_locks: Dict[str, threading.RLock] = {}

    def start(self) -> bool:
        """启动交易系统"""
        with self._state_lock:
            if self.running:
                logger.warning("交易系统已在运行")
                return False

            if not self._initialized:
                logger.info("首次启动，正在初始化交易系统...")
                success = self._initialize()
                if not success:
                    return False
                self._initialized = True

            self.running = True
            logger.info("网格交易系统启动成功！")
            logger.info(f"监控股票: {list(self._stock_grids.keys())}")

            # 更新价格并执行策略
            self._update_all_prices()
            self._execute_all_strategies()
            return True

    def stop(self) -> bool:
        """停止交易系统"""
        with self._state_lock:
            if not self.running:
                logger.warning("交易系统未运行")
                return False
            self.running = False
            logger.info("网格交易系统已停止")
            return True

    def disconnect(self):
        """断开所有 Broker"""
        disconnect_all_brokers()
        logger.info("所有 Broker 已断开")

    def is_running(self) -> bool:
        return self.running

    def get_status(self) -> dict:
        """获取系统状态"""
        strategies_count = 0
        for config in self._stock_grids.values():
            if config.get('multi_strategy'):
                strategies_count += 1
            if config.get('short_strategy'):
                strategies_count += 1
        return {
            'running': self.running,
            'strategies_count': strategies_count,
            'stocks': list(self._stock_grids.keys()),
        }

    def reload_data(self, stock_code: Optional[str] = None):
        """从数据库重新加载数据到引擎内存"""
        if not self._initialized:
            return

        target_codes = [stock_code] if stock_code else list(self._stock_grids.keys())
        for code in target_codes:
            config = self._stock_grids.get(code, {})
            multi = config.get('multi_strategy')
            short = config.get('short_strategy')
            if multi and hasattr(multi, 'grid'):
                multi.grid.reload_from_db()
            if short and hasattr(short, 'grid'):
                short.grid.reload_from_db()
        logger.info(f"引擎数据已同步: {target_codes}")

    # ==================== 初始化 ====================

    def _initialize(self) -> bool:
        """初始化: 加载配置、连接 Broker、创建策略、订阅行情"""
        # 1. 加载活跃配置
        configs = self.db.load_all_configs(active_only=True)
        if not configs:
            logger.warning("没有活跃的股票配置")
            return True  # 空配置也允许启动

        # 收集需要的市场
        markets_needed = set()
        for config in configs:
            markets_needed.add(config['market'])

        logger.info(f"加载了 {len(configs)} 个股票配置, 涉及市场: {markets_needed}")

        # 2. 连接所需 Broker
        logger.info("=" * 50)
        logger.info("开始连接券商...")
        results = connect_all_brokers(markets_needed)
        for broker_name, connected in results.items():
            status = "成功 ✓" if connected else "失败 ✗"
            logger.info(f"  {broker_name}: {status}")
        logger.info("=" * 50)

        any_connected = any(results.values()) if results else True
        if not any_connected:
            logger.error("所有 Broker 连接失败")
            return False

        # 3. 创建策略实例
        logger.info("初始化策略...")
        self._init_strategies(configs)

        # 4. 设置订单回调
        logger.info("注册订单回调...")
        self._setup_order_callbacks(markets_needed)

        # 5. 订阅行情
        logger.info("订阅行情...")
        self._subscribe_quotes(configs)

        logger.info("=" * 50)
        logger.info("交易系统初始化完成:")
        logger.info(f"  券商连接: {results}")
        logger.info(f"  监控股票: {[c['stock_code'] for c in configs]}")
        logger.info(f"  策略数量: {sum(1 for c in self._stock_grids.values() if c.get('multi_strategy') or c.get('short_strategy'))}")
        logger.info("=" * 50)

        return True

    def _init_strategies(self, configs: list):
        """初始化网格策略"""
        for config in configs:
            code = config['stock_code']
            direction = config.get('direction', GridDirection.ALL)
            market = config['market']

            # per-stock 锁
            if code not in self._stock_locks:
                self._stock_locks[code] = threading.RLock()
            lock = self._stock_locks[code]

            broker = get_broker(code)
            stock_config = config.copy()
            self._stock_grids[code] = stock_config

            # 查询券商订单用于核对
            order_dict = {}
            if broker.is_connected:
                try:
                    order_dict = broker.query_orders(code)
                except Exception as e:
                    logger.warning(f"{code} 查询订单失败: {e}")

            with lock:
                # 做多策略
                if direction in (GridDirection.ALL, GridDirection.MULTI):
                    multi_grid = DatabaseGrid(
                        db=self.db, stock_code=code, strategy_type='MULTI'
                    )
                    multi = MultiStrategy(
                        code=code, grid=multi_grid,
                        broker=broker, stock_config=stock_config,
                        stock_lock=lock,
                    )
                    self._stock_grids[code]['multi_strategy'] = multi
                    log = multi.init_grid_orders(order_dict)
                    logger.info(f"{code} MULTI init: {log}")

                # 做空策略
                if direction in (GridDirection.ALL, GridDirection.SHORT):
                    short_grid = DatabaseGrid(
                        db=self.db, stock_code=code, strategy_type='SHORT'
                    )
                    short = ShortStrategy(
                        code=code, grid=short_grid,
                        broker=broker, stock_config=stock_config,
                        stock_lock=lock,
                    )
                    self._stock_grids[code]['short_strategy'] = short
                    log = short.init_grid_orders(order_dict)
                    logger.info(f"{code} SHORT init: {log}")

    def _setup_order_callbacks(self, markets: set):
        """设置订单回调"""
        from app.brokers.factory import get_futu_broker, get_qmt_broker

        if markets & Market.FUTU_MARKETS:
            try:
                futu = get_futu_broker()
                if hasattr(futu, 'set_order_callback'):
                    futu.set_order_callback(self._on_order_update)
            except Exception as e:
                logger.warning(f"FUTU 订单回调设置失败: {e}")

        if markets & Market.A_SHARE_MARKETS:
            try:
                qmt = get_qmt_broker()
                if hasattr(qmt, 'set_order_callback'):
                    qmt.set_order_callback(self._on_order_update)
                if hasattr(qmt, 'start_xtdata_daemon'):
                    qmt.start_xtdata_daemon()
            except Exception as e:
                logger.warning(f"QMT 订单回调设置失败: {e}")

    def _subscribe_quotes(self, configs: list):
        """按市场分组订阅行情"""
        futu_codes = []
        qmt_codes = []
        for config in configs:
            code = config['stock_code']
            market = config['market']
            if market in Market.FUTU_MARKETS:
                futu_codes.append(code)
            elif market in Market.A_SHARE_MARKETS:
                qmt_codes.append(code)

        from app.brokers.factory import get_futu_broker, get_qmt_broker

        if futu_codes:
            try:
                broker = get_futu_broker()
                broker.subscribe_quotes(futu_codes, self._on_quote_update)
            except Exception as e:
                logger.error(f"FUTU 行情订阅失败: {e}")

        if qmt_codes:
            try:
                broker = get_qmt_broker()
                broker.subscribe_quotes(qmt_codes, self._on_quote_update)
            except Exception as e:
                logger.error(f"QMT 行情订阅失败: {e}")

    # ==================== 回调处理 ====================

    def _on_quote_update(self, stock_code: str, last_price: float):
        """行情推送回调"""
        if not self.running:
            return

        stock_config = self._stock_grids.get(stock_code)
        if not stock_config:
            return

        # 价格未变化则跳过
        old_price = stock_config.get('last_price')
        if old_price and abs(last_price - old_price) < 0.001:
            return

        lock = self._stock_locks.get(stock_code, threading.RLock())
        try:
            with lock:
                stock_config['last_price'] = last_price

                # 检查对应 broker 是否在交易时间
                broker = get_broker(stock_code)
                if not broker.is_trading_time():
                    return

                multi_buy, multi_sell = 0, 0
                short_buy, short_sell = 0, 0

                multi = stock_config.get('multi_strategy')
                if multi:
                    result = multi.run_strategy(cur_price=last_price)
                    if result:
                        multi_buy, multi_sell = result

                short = stock_config.get('short_strategy')
                if short:
                    result = short.run_strategy(cur_price=last_price)
                    if result:
                        short_buy, short_sell = result

                total_buy = multi_buy + short_buy
                total_sell = multi_sell + short_sell
                logger.info(
                    f"{stock_code} price={last_price} | "
                    f"MULTI 买单:{multi_buy} 卖单:{multi_sell} | "
                    f"SHORT 买单:{short_buy} 卖单:{short_sell}"
                )

        except TransientError as e:
            logger.warning(f"行情处理瞬时错误({stock_code}): {e}")
        except Exception as e:
            logger.error(f"行情处理异常({stock_code}): {e}", exc_info=True)

    def _on_order_update(self, order_info: dict):
        """订单状态回调"""
        if not self.running:
            return

        stock_code = order_info.get('stock_code', '')
        stock_config = self._stock_grids.get(stock_code)
        if not stock_config:
            return

        lock = self._stock_locks.get(stock_code, threading.RLock())
        status = order_info.get('order_status', '')

        try:
            with lock:
                multi = stock_config.get('multi_strategy')
                if multi:
                    log = multi.process_order_status(order_info)
                    if 'not found' not in log:
                        logger.info(f"{stock_code} MULTI: {log}")
                        if status in (FILLED_ALL, CANCELLED_PART):
                            last_price = stock_config.get('last_price')
                            if last_price:
                                multi.run_strategy(cur_price=last_price)
                        return

                short = stock_config.get('short_strategy')
                if short:
                    log = short.process_order_status(order_info)
                    if 'not found' not in log:
                        logger.info(f"{stock_code} SHORT: {log}")
                        if status in (FILLED_ALL, CANCELLED_PART):
                            last_price = stock_config.get('last_price')
                            if last_price:
                                short.run_strategy(cur_price=last_price)

        except Exception as e:
            logger.error(f"订单回调异常({stock_code}): {e}", exc_info=True)

    # ==================== 价格更新 & 策略执行 ====================

    def _update_all_prices(self):
        """获取所有股票最新价格"""
        # 按 broker 分组
        futu_codes = []
        qmt_codes = []
        for code, config in self._stock_grids.items():
            market = config.get('market', '')
            if market in Market.FUTU_MARKETS:
                futu_codes.append(code)
            elif market in Market.A_SHARE_MARKETS:
                qmt_codes.append(code)

        from app.brokers.factory import get_futu_broker, get_qmt_broker

        # FUTU 批量获取
        if futu_codes:
            try:
                broker = get_futu_broker()
                prices = broker.get_latest_prices(futu_codes)
                for code, price in prices.items():
                    if code in self._stock_grids:
                        self._stock_grids[code]['last_price'] = price
            except Exception as e:
                logger.warning(f"FUTU 批量获取价格失败: {e}")

        # QMT 批量获取
        if qmt_codes:
            try:
                broker = get_qmt_broker()
                prices = broker.get_latest_prices(qmt_codes)
                for code, price in prices.items():
                    if code in self._stock_grids:
                        self._stock_grids[code]['last_price'] = price
            except Exception as e:
                logger.warning(f"QMT 批量获取价格失败: {e}")

        logger.info(f"价格更新完成: {len(futu_codes)} FUTU + {len(qmt_codes)} QMT")

    def _execute_all_strategies(self):
        """对所有股票执行一次策略"""
        for code, config in self._stock_grids.items():
            last_price = config.get('last_price')
            if not last_price:
                continue

            broker = get_broker(code)
            if not broker.is_trading_time():
                continue

            lock = self._stock_locks.get(code, threading.RLock())
            try:
                with lock:
                    multi_buy, multi_sell = 0, 0
                    short_buy, short_sell = 0, 0

                    multi = config.get('multi_strategy')
                    if multi:
                        result = multi.run_strategy(cur_price=last_price)
                        if result:
                            multi_buy, multi_sell = result

                    short = config.get('short_strategy')
                    if short:
                        result = short.run_strategy(cur_price=last_price)
                        if result:
                            short_buy, short_sell = result

                    logger.info(
                        f"{code} price={last_price} | "
                        f"MULTI 买单:{multi_buy} 卖单:{multi_sell} | "
                        f"SHORT 买单:{short_buy} 卖单:{short_sell}"
                    )
            except Exception as e:
                logger.error(f"策略执行异常({code}): {e}", exc_info=True)
