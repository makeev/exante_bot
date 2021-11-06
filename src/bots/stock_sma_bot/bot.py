import logging
from typing import Union, List

import numpy as np
from talib import RSI, SMA

from bots.base import Result, BaseBot, Signal, Deal, CloseOpenedDeal
from helpers import get_trend_for


class StockSmaBot(BaseBot):
    min_candles = 20
    name = 'stock_sma_bot'

    def __init__(self, money_manager, historical_ohlcv: List = None, **params):
        # прошедшие данные
        self.historical_ohlcv = historical_ohlcv or []
        self.money_manager = money_manager
        self.params = params

        self.overbought = False
        self.oversold = False

    async def _test_price(self, price) -> Union[Result, None]:
        if len(self.historical_ohlcv) < self.min_candles:
            # недостаточно свечек для принятия решения
            logging.info('%s недостаточно свечек %d' % (self.name, len(self.historical_ohlcv)))
            return

        is_short_allowed = self.params.get('is_short_allowed', False)
        trend_len = self.params.get('trend_len', 5)
        only_main_session = self.params.get('only_main_session', False)
        close_signal = self.params.get('close_signal', Signal.CLOSE)
        high_sma_value = self.params.get("high_sma_value", 100)
        middle_sma_value = self.params.get("middle_sma_value", 50)
        low_sma_value = self.params.get("low_sma_value", 30)

        if only_main_session:
            last_candle = self.get_last_candle()
            if last_candle.datetime.hour < 16 \
                    or (last_candle.datetime.hour == 16 and last_candle.datetime.minute < 30) \
                    or last_candle.datetime.hour >= 23:
                # торгуем только в основную сессию
                logging.info('%s не основное время %s-%s' % (self.name, last_candle.datetime.hour, last_candle.datetime.minute))
                return

        close_array = [float(c.close) for c in self.historical_ohlcv]
        sma_high = SMA(np.array(close_array), high_sma_value)
        sma_middle = SMA(np.array(close_array), middle_sma_value)
        sma_low = SMA(np.array(close_array), low_sma_value)

        # sma_300 = SMA(np.array(close_array), 300)
        # main_trend = get_trend_for(list(sma_300[-3:]))

        j = -trend_len - 1
        had_trend = sma_high[j] > sma_middle[j] > sma_low[j] or sma_high[j] < sma_middle[j] < sma_low[j]

        has_trend = False
        if had_trend:
            has_trend = True
            for i in range(1, trend_len + 1):
                if not (sma_high[-i] > sma_middle[-i] > sma_low[-i] or sma_high[-i] < sma_middle[-i] < sma_low[-i]):
                    has_trend = False
                    break

        order_type = None
        if has_trend:
            logging.info('%s has trend' % self.name)
            if sma_high[-1] > sma_middle[-1] > sma_low[-1]:
                if price > sma_low[-1] and price < sma_middle[-1]:
                    order_type = Signal.SELL if is_short_allowed else close_signal
                else:
                    logging.info('%s price=%s, sma_30=%s, sma_50=%s' % (self.name, price, sma_low[-1], sma_middle[-1]))
            else:
                order_type = Signal.BUY
                if price < sma_low[-1] and price > sma_middle[-1]:
                    order_type = Signal.BUY
                else:
                    logging.info('%s price=%s, sma_30=%s, sma_50=%s' % (self.name, price, sma_low[-1], sma_middle[-1]))
        else:
            logging.info('%s no trend' % self.name)
            if not (sma_high[-1] > sma_middle[-1] > sma_low[-1] or sma_high[-1] < sma_middle[-1] < sma_low[-1]):
                order_type = close_signal

        if order_type:
            return Result(signal=order_type, price=price)

    def add_candle(self, candle):
        """
        Последняя свеча в OHLCV формате,
        добавляется в конец исторических данных

        self.historical_ohlcv.append(ohlcv)
        """
        # прибавляем новую свечку
        self.historical_ohlcv.append(candle)
        # храним только последние 1000
        self.historical_ohlcv = self.historical_ohlcv[-1000:]

    async def check_price(self, price):
        """
        Проверяем текущую цену,
        решаем входить или не входить в сделку

        сохраняем в self.last_price
        возвращает Deal
        """
        self.last_price = price

        result = await self._test_price(price)

        if result:
            if result.signal == Signal.CLOSE:
                raise CloseOpenedDeal()

            return Deal(**{
                "price": result.price,
                "amount": self.money_manager.get_order_amount(),  # amount в base_currency сколько купили
                "stop_loss": self.money_manager.get_stop_loss(result.signal, result.price),
                "take_profit": self.money_manager.get_take_profit(result.signal, result.price),
                "side": result.signal.value,
                "status": "open",
            })

    async def check_deal(self, current_price, deal):
        """
        Проверяем ордер,
        надо ли поменять SL или TP или закрыть по рынку

        можно проверить self.last_price и self.historical_ohlcv
        """
        # if self.last_candle.is_pinbar():
        #     if self.last_candle.pinbar_direction() != deal.get_side():
        #         deal.stop_loss = current_price
        #         return deal

        return await self.money_manager.trailing_stop_check(current_price, deal)

    @property
    def last_candle(self):
        return self.get_last_candle()

    def get_last_candle(self):
        if self.historical_ohlcv:
            return self.historical_ohlcv[-1]
