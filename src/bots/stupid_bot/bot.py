from typing import Union, List
import numpy as np

from talib import SMA

from bots.base import Result, BaseBot, Signal, CandleStick, Deal
from helpers import get_trend_for


class StupidBot(BaseBot):
    min_candles = 4
    name = 'stupid_bot'

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

    async def _test_price(self, price) -> Union[Result, None]:
        if len(self.historical_ohlcv) < self.min_candles:
            # недостаточно свечек для принятия решения
            return

        # конфигурируемые параметры
        sma_size = self.params.get('sma_size', 100)
        trend_len = self.params.get('trend_len', 15)
        pinbar_size = self.params.get('pinbar_size', 2)
        super_pinbar_size = self.params.get('super_pinbar_size', None)

        last_candle = self.get_last_candle()
        if not last_candle.is_long_pinbar(pinbar_size):
            # последняя свеча должна быть пинбаром с длинным хвостом
            return

        # отключаем дополнительные проверки, если пинбар ну очень хорош
        disable_extra_check = super_pinbar_size and last_candle.is_long_pinbar(super_pinbar_size)

        if last_candle.tail > 0.00002:
            # короткая тень должна быть короткой
            return

        if last_candle.body_size < 0.0001:
            # слишком маленькая свеча
            return

        print(last_candle.tail)
        # определяем тренд по SMA закрытия
        close_array = [float(c.close) for c in self.historical_ohlcv]
        sma = SMA(np.array(close_array), sma_size)
        trend = get_trend_for(list(sma[-trend_len:]))

        if last_candle.pinbar_direction() == Signal.BUY:  # пинбар смотрит вверх
            order_type = Signal.BUY

            if not disable_extra_check:
                if trend != order_type:  # тренд вниз
                    return

                # три свечи до этого выше
                for c in self.historical_ohlcv[-4:-1]:
                    if min(c.raw_data) < min(last_candle.raw_data):
                        return
        else:  # пинбар смотрит вниз
            order_type = Signal.SELL

            if not disable_extra_check:
                if trend != order_type:  # тренд вверх
                    return

                # три последних свечи ниже
                for c in self.historical_ohlcv[-4:-1]:
                    if max(c.raw_data) > max(last_candle.raw_data):
                        return

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
        return self.historical_ohlcv[-1]
