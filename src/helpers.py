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


async def send_admin_message(message, prefix=None):
    import aiogram
    import settings
    b = aiogram.Bot(token=settings.TELEGRAM_TOKEN)
    if not prefix:
        prefix = "#exantebot"
    await b.send_message(settings.TELEGRAM_CHAT_ID, prefix+' '+message)


def max_diff(a):
    vmin = a[0]
    dmax = 0
    for i in range(len(a)):
        if (a[i] < vmin):
            vmin = a[i]
        elif (a[i] - vmin > dmax):
            dmax = a[i] - vmin
    return dmax
