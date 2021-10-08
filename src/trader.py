import asyncio
import logging
import sys
from decimal import Decimal

from bots.stupid_bot import StupidBot
from bots.stupid_bot.money_manager import SimpleMoneyManager
from exante_api import ExanteApi, Event, HistoricalData
from exante_api.client import TooManyRequests, PositionAlreadyClosed, PositionNotFound
from helpers import get_mid_price, send_admin_message

application_id = 'e2b62931-4cf2-4b6f-a319-b94f1a6341f5'
access_key = 'jf5ODSu3jZ8DQXhxdlTN'
account_id = 'PFC1032.006'
demo = True
symbol = 'BTC.USD'
time_interval = 300  # 5 min

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    stream=sys.stdout)
logging.info("logging test")


class Processor:
    def __init__(self, historical_data: HistoricalData, bot: StupidBot, api: ExanteApi):
        self.historical_data = historical_data
        self.bot = bot
        self.api = api

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
                        await self.api.close_position(account_id, symbol)
                    except (PositionAlreadyClosed, PositionNotFound):
                        # нечего закрывать, все ок
                        pass
                    else:
                        # даем время позиции закрыться
                        await asyncio.sleep(0.5)

                    # открываем новую позицию
                    await self.api.open_position(
                        account_id=account_id,
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
                    ))


async def main():
    while True:
        api = ExanteApi(application_id=application_id, access_key=access_key, demo=demo)

        try:
            # берем исторические данные, чтобы нарисовать линию SMA
            r = await api.get_ohlcv(symbol, time_interval, size=1000)
            data = await r.json()
            historical_data = HistoricalData(time_interval, data)
            print('исторчиеские данные загружены: %d' % len(data))

            # инициируем бота которым будем торговать
            params = {
                'sma_size': 100,
                'trend_len': 5,
                'pinbar_size': 1.5,
                'super_pinbar_size': None
            }
            bot = StupidBot(
                money_manager=SimpleMoneyManager(
                    order_amount=0.45,
                    diff=Decimal(100),
                    stop_loss_factor=1.2,
                    take_profit_factor=6,
                    trailing_stop=False
                ),
                historical_ohlcv=historical_data.get_list(),
                **params
            )

            # процессор будет обрабатывать все события из стрима
            processor = Processor(historical_data, bot=bot, api=api)
            # открываем стрим и слушаем
            logging.info('открываем стрим')
            await api.quote_stream(symbol, processor.on_event)
        except TooManyRequests:
            # иногда бросает get_ohlcv, надо просто подождать
            logging.error('TooManyRequests')
            await send_admin_message("TooManyRequests")
            await asyncio.sleep(60)
        except Exception as e:
            logging.exception('неведомая хуйня:')
            await send_admin_message("неведомая хуйня: %s" % e)
            await asyncio.sleep(3)
        finally:
            await api.close()
            await send_admin_message("api закрыто")


if __name__ == '__main__':
    asyncio.run(main())
