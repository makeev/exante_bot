import asyncio
import logging
import sys
import time
from decimal import Decimal

from bots.rsi_bot.bot import RsiBot
from bots.stupid_bot.money_manager import SimpleMoneyManager
from exante_api import ExanteApi, Event, HistoricalData
from exante_api.client import TooManyRequests, PositionAlreadyClosed, PositionNotFound, PositionOrdersNotFound
from helpers import get_mid_price, send_admin_message

import settings

symbol = 'EUR/NZD.E.FX'
account_name = 'demo_1'
prefix = '#exante #%s #%s' % (symbol, account_name)
time_interval = 300
money_manager = SimpleMoneyManager(
    order_amount=50000,
    diff=Decimal(0.001),
    stop_loss_factor=2,
    take_profit_factor=10,
)
bot_params = {
    'upper_band': 80,
    'lower_band': 20,
}
breakeven_profit = 100

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    stream=sys.stdout)
logging.info("logging test")


class Processor:
    def __init__(self, historical_data: HistoricalData, bot: RsiBot, api: ExanteApi):
        self.historical_data = historical_data
        self.bot = bot
        self.api = api
        self.last_check_ts = time.time()

    async def on_event(self, data):
        e = Event(data)
        if e.type == 'new_price':
            # пришла новая цена
            last_ts = self.historical_data.last_ts
            # добавляем ее в исторические данные
            self.historical_data.add_data(e.ts, e.bid, e.ask)

            if last_ts and last_ts != self.historical_data.last_ts:
                logging.info('свеча сформирована: %s' % self.historical_data.get_last_candle().raw_data)
                # начала формироваться новая цена
                self.bot.add_candle(self.historical_data.get_last_candle())

                price = get_mid_price(bid=e.bid, ask=e.ask)
                deal = await self.bot.check_price(price)
                if deal:
                    # закрываем позицию, если открыта
                    try:
                        position = await self.api.get_position(symbol)
                        if position:
                            position_side = 'sell' if float(position['quantity']) < 0 else 'buy'
                            # закрываем позицию только если она открыта в противоположную сторону
                            if position_side != deal.side:
                                # закрываем, надо открыть в другую сторону
                                await self.api.close_position(symbol, position=position)
                                # даем время позиции закрыться
                                await asyncio.sleep(0.5)
                                position = None
                    except (PositionAlreadyClosed, PositionNotFound):
                        # нечего закрывать, все ок
                        position = None

                    # открываем новую позицию
                    if not position:
                        await self.api.open_position(
                            symbol=symbol,
                            side=deal.side,
                            quantity=deal.amount,
                            take_profit=deal.take_profit,
                            stop_loss=deal.stop_loss,
                        )

                        await send_admin_message("new deal {side}: \namount={amount} \ntp={take_profit} \nsl={stop_loss}".format(
                            side=deal.side,
                            amount=deal.amount,
                            take_profit=deal.take_profit,
                            stop_loss=deal.stop_loss,
                        ), prefix)

            # проверяем можно ли двинуть в безубыток
            time_since_last_check = time.time() - self.last_check_ts
            if time_since_last_check > 10:  # не чаще раз в 5с
                self.last_check_ts = time.time()
                try:
                    position = await self.api.get_position(symbol)
                    if position and float(position['convertedPnl']) >= breakeven_profit:
                        await self.api.move_to_breakeven(symbol)
                except PositionOrdersNotFound:
                    await send_admin_message('PositionOrdersNotFound: %s' % position, prefix)
                except AssertionError as e:
                    await send_admin_message('AssertionError: %s' % str(e), prefix)


async def main():
    while True:
        api = ExanteApi(**settings.ACCOUNTS[account_name])

        try:
            # берем исторические данные, чтобы нарисовать линию SMA
            r = await api.get_ohlcv(symbol, time_interval, size=1000)
            data = await r.json()
            historical_data = HistoricalData(time_interval, data)
            print('исторчиеские данные загружены: %d' % len(data))

            # инициируем бота которым будем торговать
            bot = RsiBot(
                money_manager=money_manager,
                historical_ohlcv=historical_data.get_list(),
                **bot_params
            )

            # процессор будет обрабатывать все события из стрима
            processor = Processor(historical_data, bot=bot, api=api)
            # открываем стрим и слушаем
            logging.info('открываем стрим')
            await api.quote_stream(symbol, processor.on_event)
        except TooManyRequests:
            # иногда бросает get_ohlcv, надо просто подождать
            logging.error('TooManyRequests')
            await send_admin_message("TooManyRequests", prefix)
            await asyncio.sleep(60)
        except Exception as e:
            logging.exception('неведомая хуйня:')
            await send_admin_message("неведомая хуйня: %s" % e, prefix)
            await asyncio.sleep(3)
        finally:
            await api.close()


if __name__ == '__main__':
    asyncio.run(main())
