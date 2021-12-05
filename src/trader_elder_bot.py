import asyncio
import logging
import sys
import time

import settings
from bots.base import CloseOpenedDeal, Signal
from bots.elder_bot.bot import ElderBot
from bots.multibot.bot import MultiBot
from bots.stupid_bot.money_manager import SimpleMoneyManager
from exante_api import ExanteApi, Event, HistoricalData
from exante_api.client import TooManyRequests, PositionAlreadyClosed, PositionNotFound
from helpers import get_mid_price, send_admin_message

symbol = 'URA.ARCA'
account_name = 'demo_1'
prefix = '#exante #%s #%s' % (symbol, account_name)
time_interval = 300
breakeven_profit = 100

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    stream=sys.stdout)
logging.info("logging test")


def bot_factory(historical_data):
    bot_1 = ElderBot(
        money_manager=SimpleMoneyManager(
            order_amount=300,
            diff=0.2,
            stop_loss_factor=5,
            take_profit_factor=22,
        ),
        historical_ohlcv=historical_data,
        **{
            "is_short_allowed": True,
            "only_main_session": True,
            "close_signal": Signal.CLOSE,
        }
    )
    # инициируем бота которым будем торговать
    return MultiBot(bot_1)


class Processor:
    def __init__(self, historical_data: HistoricalData, bot, api: ExanteApi):
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
                logging.info('new candle: %s' % data)
                # начала формироваться новая цена
                self.bot.add_candle(self.historical_data.get_last_candle())

                price = get_mid_price(bid=e.bid, ask=e.ask)
                try:
                    deal = await self.bot.check_price(price)
                    if deal:
                        logging.info('new deal: %s' % deal)

                        try:
                            position = await self.api.get_position(symbol)
                        except (PositionAlreadyClosed, PositionNotFound):
                            position = None

                        logging.info('position: %s' % position)

                        if position:
                            position_side = 'sell' if float(position['quantity']) < 0 else 'buy'
                            # закрываем позицию только если она открыта в противоположную сторону
                            if position_side != deal.side:
                                # закрываем, надо открыть в другую сторону
                                await self.api.close_position(symbol, position=position)
                                # даем время позиции закрыться
                                await asyncio.sleep(0.5)
                                position = None

                        # открываем новую позицию
                        if not position:
                            await self.api.open_position(
                                symbol=symbol,
                                side=deal.side,
                                quantity=deal.amount,
                                take_profit=deal.take_profit,
                                stop_loss=deal.stop_loss,
                                duration='day',
                            )

                            await send_admin_message("{symbol} new deal {side}: \namount={amount} \ntp={take_profit} \nsl={stop_loss}".format(
                                symbol=symbol,
                                side=deal.side,
                                amount=deal.amount,
                                take_profit=deal.take_profit,
                                stop_loss=deal.stop_loss,
                            ), prefix=prefix)
                except CloseOpenedDeal:
                    logging.info('close signal')

                    last_candle = self.bot.get_last_candle()

                    if not last_candle:
                        pass
                    elif last_candle.datetime.hour < 16 \
                            or (last_candle.datetime.hour == 16 and last_candle.datetime.minute < 30) \
                            or last_candle.datetime.hour >= 23:
                        # торгуем только в основную сессию
                        pass
                    else:
                        position = await self.api.get_position(symbol)
                        if position:
                            await self.api.close_position(symbol, position=position, duration='day')
                            # даем время позиции закрыться
                            await asyncio.sleep(0.5)
                            position = None
                            await send_admin_message('%s close position signal' % symbol, prefix=prefix)


async def main():
    while True:
        api = ExanteApi(**settings.ACCOUNTS[account_name])

        try:
            # берем исторические данные, чтобы нарисовать линию SMA
            r = await api.get_ohlcv(symbol, time_interval, size=5000)
            data = await r.json()
            historical_data = HistoricalData(time_interval, data)
            print('исторические данные загружены: %d' % len(data))

            # процессор будет обрабатывать все события из стрима
            bot = bot_factory(historical_data.get_list())
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