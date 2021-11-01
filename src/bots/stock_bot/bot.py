import logging
from typing import Union, List

import numpy as np
from talib import RSI

from bots.base import Result, BaseBot, Signal, Deal, CloseOpenedDeal


class StockBot(BaseBot):
    min_candles = 10
    name = 'stock_bot'

    def __init__(self, money_manager, historical_ohlcv: List = None, **params):
        """
        params:
          sma_size - размер SMA для определения тренда
          trend_len - сколько свечей проверять при определении тренда
        """
        # прошедшие данные
        self.historical_ohlcv = historical_ohlcv or []
        self.money_manager = money_manager
        self.params = params

        self.overbought = False
        self.oversold = False

    async def _test_price(self, price) -> Union[Result, None]:
        if len(self.historical_ohlcv) < self.min_candles:
            # недостаточно свечек для принятия решения
            return

        # конфигурируемые параметры
        rsi_length = self.params.get('rsi_length', 14)
        upper_band = self.params.get('upper_band', 70)
        lower_band = self.params.get('lower_band', 30)
        is_short_allowed = self.params.get('is_short_allowed', False)
        only_main_session = self.params.get('only_main_session', False)
        close_signal = self.params.get('close_signal', Signal.CLOSE)

        if only_main_session:
            last_candle = self.get_last_candle()
            if last_candle.datetime.hour < 16 \
                    or (last_candle.datetime.hour == 16 and last_candle.datetime.minute < 30) \
                    or last_candle.datetime.hour >= 23:
                # торгуем только в основную сессию
                logging.info('%s не основное время %s-%s' % (self.name, last_candle.datetime.hour, last_candle.datetime.minute))
                return

        close_array = [float(c.close) for c in self.historical_ohlcv]
        rsi = RSI(np.array(close_array), rsi_length)

        order_type = False
        logging.info('%s rsi[-3] %s' % (self.name, rsi[-3]))
        if not self.overbought and not self.oversold:
            # смотрим не вышел ли RSI за нужные нам пределы
            last_rsi = rsi[-3]
            if last_rsi >= upper_band:
                # перекупленность
                self.overbought = True
                self.oversold = False
            elif last_rsi <= lower_band:
                # перепроданность
                self.oversold = True
                self.overbought = False
            else:
                self.overbought = False
                self.oversold = False

        # мы уже в зоне перекупленности/перепроданности
        # ждем когда индикатор вернется обратно, чтобы открыть сделку
        current_rsi = rsi[-2]
        logging.info('%s rsi[-2] %s' % (self.name, rsi[-2]))
        if self.overbought:
            if current_rsi <= upper_band:
                self.overbought = False
                order_type = Signal.SELL if is_short_allowed else close_signal
        elif self.oversold:  # нас интересует только покупка
            if current_rsi >= lower_band:
                self.oversold = False
                order_type = Signal.BUY

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
