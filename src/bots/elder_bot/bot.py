import logging
from datetime import date
from decimal import Decimal
from typing import Union, List

import numpy as np
from talib import RSI, SMA, EMA

from bots.base import Result, BaseBot, Signal, Deal


class ElderBot(BaseBot):
    name = 'elder_bot'

    def __init__(self, money_manager, historical_ohlcv: List = None, **params):
        """
        params:
          sma_size - размер SMA для определения тренда
          trend_len - сколько свечей проверять при определении тренда
        """
        # прошедшие данные
        self.historical_ohlcv = historical_ohlcv or []
        self.day_ohlc_data = {}
        for row in self.historical_ohlcv:
            ts = row['timestamp']
            d = date.fromtimestamp(ts // 1000)
            self.day_ohlc_data.setdefault(d,
                {
                    "open": row['open'],
                    "high": row['high'],
                    "low": row['low'],
                    "close": row['close']
                }
            )
            self.day_ohlc_data[d]['high'] = max(self.day_ohlc_data[d]['high'], row['high'])
            self.day_ohlc_data[d]['low'] = min(self.day_ohlc_data[d]['low'], row['low'])
            self.day_ohlc_data[d]['close'] = row['close']

        self.money_manager = money_manager
        self.params = params

        self.lower = False
        self.upper = False
        self.last_order_type = None
        self.last_signal_length = 0

    async def _test_price(self, price) -> Union[Result, None]:
        # конфигурируемые параметры
        rsi_length = self.params.get('rsi_length', 14)
        upper_band = self.params.get('upper_band', 90)
        lower_band = self.params.get('lower_band', 10)
        only_main_session = self.params.get('only_main_session', False)
        close_signal = self.params.get('close_signal', Signal.CLOSE)
        is_short_allowed = self.params.get('is_short_allowed', False)

        if only_main_session:
            last_candle = self.get_last_candle()
            if last_candle.datetime.hour < 16 \
                    or (last_candle.datetime.hour == 16 and last_candle.datetime.minute < 30) \
                    or last_candle.datetime.hour >= 23:
                # торгуем только в основную сессию
                logging.info('%s не основное время %s-%s' % (self.name, last_candle.datetime.hour, last_candle.datetime.minute))
                return

        close_array = [float(c.close) for c in self.historical_ohlcv]
        hlc3_array = [(float(c['high']) + float(c['low']) + float(c['close'])) / 3 for c in self.day_ohlc_data.values()]

        rsi = RSI(np.array(close_array), rsi_length)
        sma = SMA(np.array(close_array), 14)
        ema = EMA(np.array(hlc3_array), 14)

        last_sma = Decimal(sma[-1])
        last_ema = Decimal(ema[-1])
        last_rsi = Decimal(rsi[-1])

        if last_sma.is_nan() or last_ema.is_nan() or last_rsi.is_nan():
            return

        if last_sma > last_ema:
            order_type = Signal.BUY
            # if self.last_order_type != order_type:
            #     if last_sma - last_ema < price_threshold:
            #         order_type = None
        else:
            order_type = Signal.SELL
            # if self.last_order_type != order_type:
            #     if last_ema - last_sma < price_threshold:
            #         order_type = None

        # if rsi[-1] > 90 or rsi[-1] < 10:
        #     order_type = close_signal

        if order_type:
            self.last_order_type = order_type
            return Result(signal=order_type, price=price)

    def add_candle(self, candle):
        """
        Последняя свеча в OHLCV формате,
        добавляется в конец исторических данных

        self.historical_ohlcv.append(ohlcv)
        """
        # прибавляем новую свечку
        self.historical_ohlcv.append(candle)
        # храним только последние
        self.historical_ohlcv = self.historical_ohlcv[-5000:]

        ts = candle.timestamp
        d = date.fromtimestamp(ts)
        self.day_ohlc_data.setdefault(d,
              {
                  "open": candle.open,
                  "high": candle.high,
                  "low": candle.low,
                  "close": candle.close
              }
        )
        self.day_ohlc_data[d]['high'] = max(self.day_ohlc_data[d]['high'], candle.high)
        self.day_ohlc_data[d]['low'] = min(self.day_ohlc_data[d]['low'], candle.low)
        self.day_ohlc_data[d]['close'] = candle.close

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
