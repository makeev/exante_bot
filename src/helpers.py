from decimal import Decimal

import numpy as np

from bots.base import Signal


def get_trend_for(data: list) -> int:
    for row in data:
        if np.isnan(row):
            return 0

    trend_up = bool(data == sorted(data))
    trend_down = bool(data == sorted(data, reverse=True))

    if trend_up:
        return Signal.BUY
    elif trend_down:
        return Signal.SELL
    else:
        return 0


def get_mid_price(bid, ask):
    return Decimal(ask) + (Decimal(bid) - Decimal(ask)) / 2
