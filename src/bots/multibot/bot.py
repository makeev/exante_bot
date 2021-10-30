from bots.base import BaseBot


class MultiBot(BaseBot):
    min_candles = 10
    name = 'rsi_bot'

    def __init__(self, *bots):
        self.bots = bots

    def add_candle(self, candle):
        for bot in self.bots:
            bot.add_candle(candle)

    async def check_price(self, price):
        for bot in self.bots:
            deal = await bot.check_price(price)
            if deal:
                return deal

    async def check_deal(self, current_price, deal):
        return False

    @property
    def last_candle(self):
        return self.bots[0].get_last_candle()

    def get_last_candle(self):
        return self.bots[0].get_last_candle()
