from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal


class CloseOpenedDeal(Exception):
    pass


class Signal(Enum):
    BUY = 'buy'
    SELL = 'sell'
    CLOSE = 'close'


@dataclass
class Result:
    signal: Signal  # покупать или продавать
    price: Decimal  # по какой цене

    def __str__(self):
        return '%s: %s' % (self.signal.value, self.price)


class CandleStick:
    def __init__(self, timestamp, open, high, low, close):
        self.timestamp = timestamp
        self.formatted_date = datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')
        self.datetime = datetime.fromtimestamp(self.timestamp)
        self.open = Decimal(open)
        self.high = Decimal(high)
        self.low = Decimal(low)
        self.close = Decimal(close)

        # стандартное представление для рисования графиков
        self.raw_data = [self.open, self.high, self.low, self.close]

    @property
    def body_type(self):
        if self.close > self.open:
            # зеленое тело, цена выросла
            return 1

        if self.close < self.open:
            # красное тело, цена снизилась
            return -1

        # цена не поменялась, у свечи нет тела
        return 0

    @property
    def upper_shadow(self):
        """
        Верхняя тень(хвост)
        """
        if self.body_type > 0:
            return self.high - self.close

        if self.body_type < 0:
            return self.high - self.open

        return 0  # нет тела - нет хвоста

    @property
    def lower_shadow(self):
        """
        Нижняя тень(хвост)
        """
        if self.body_type > 0:
            return self.open - self.low

        if self.body_type < 0:
            return self.close - self.low

        return 0

    @property
    def shadow(self):
        """
        Длинный хвост
        """
        return max(self.lower_shadow, self.upper_shadow)

    @property
    def tail(self):
        """
        Короткий хвост
        """
        return min(self.lower_shadow, self.upper_shadow)

    @property
    def full_size(self):
        """
        Длина свечи
        """
        return max(self.raw_data) - min(self.raw_data)

    @property
    def body_size(self):
        """
        Длина свечи
        """
        if self.body_type > 0:
            return self.close - self.open

        if self.body_type < 0:
            return self.open - self.close

        return 0

    def is_pinbar(self) -> bool:
        return self.shadow > self.body_size

    def is_long_pinbar(self, coef = 2) -> bool:
        return Decimal(self.shadow) > (Decimal(self.body_size+self.tail) * Decimal(coef))

    def pinbar_direction(self):
        if self.upper_shadow > self.lower_shadow:
            return Signal.SELL
        return Signal.BUY

    @property
    def price_range(self):
        return [min(self.raw_data), max(self.raw_data)]


class BaseBot(ABC):
    """
    Методы надо вызывать один за другим
    bot.add_ohlcv(ohlcv)
    bot.check_price(close)
    bot.check_order(order)
    """
    name = '¯\_(ツ)_/¯'
    historical_ohlcv = []
    last_price = []

    @abstractmethod
    def add_candle(self, candle: CandleStick):
        """
        Последняя свеча объекст класса CandleStick
        добавляется в конец исторических данных

        self.historical_ohlcv.append(ohlcv)
        """
        raise NotImplemented

    @abstractmethod
    async def check_price(self, price):
        """
        Проверяем текущую цену,
        решаем входить или не входить в сделку

        сохраняем в self.last_price
        """
        raise NotImplemented

    @abstractmethod
    async def check_deal(self, current_price, deal):
        """
        Проверяем ордер,
        надо ли поменять SL или TP или закрыть по рынку

        можно проверить self.last_price и self.historical_ohlcv
        """
        raise NotImplemented


@dataclass
class Deal:
    amount: Decimal
    price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    status: Literal['open', 'closed']
    side: Literal['buy', 'sell']

    def check(self, candle: CandleStick):
        if not self.is_open():
            return

        # будем пессимистами и сначала проверяем свечу на убыток
        if candle.price_range[0] <= self.stop_loss <= candle.price_range[1]:
            return self.close(self.stop_loss)

        if candle.price_range[0] <= self.take_profit <= candle.price_range[1]:
            return self.close(self.take_profit)

    def is_open(self):
        return self.status == 'open'

    def close(self, price):
        self.status = 'closed'

        if self.side == Signal.BUY.value:
            profit = price - self.price
        else:
            profit = self.price - price

        return Decimal(profit) * Decimal(self.amount)

    def __str__(self):
        return str(self.side)
