import asyncio
import json
from decimal import Decimal

import settings
from bots.base import CloseOpenedDeal
from bots.stock_sma_bot.bot import StockSmaBot
from bots.stupid_bot.money_manager import SimpleMoneyManager
from exante_api import ExanteApi, HistoricalData

api = ExanteApi(**settings.ACCOUNTS['demo_2'])
symbol = 'URA.ARCA'
# symbol = 'BOTZ.NASDAQ'
time_interval = 300
money_manager = SimpleMoneyManager(
    order_amount=100,
    diff=0.2,
    stop_loss_factor=2,
    take_profit_factor=8,
)
bot_params = {
    "trend_len": 2,
    "is_short_allowed": False,
    "only_main_session": True
}
max_candles = 5000
update_file = False
bot_class = StockSmaBot
show_plot = True


class Tester:
    def __init__(self):
        self.annotations = []
        self.take_profit_deals = 0
        self.stop_loss_deals = 0
        self.profit = Decimal(0)
        self.loss = Decimal(0)
        self.drawdown = Decimal(0)
        self.all_drawdowns = []

    def get_profit_factor(self):
        return '%.2f' % float(self.profit / self.loss) if self.loss else 0

    def get_total_profit(self):
        return self.profit - self.loss

    def get_max_drawdown(self):
        return max(self.all_drawdowns) if self.all_drawdowns else 0

    def _handle_deal_profit(self, deal_profit, date, price):
        if deal_profit >= 0:
            self.annotations.append(
                dict(
                    x=date, y=price, xref='x', yref='y',
                    showarrow=True, xanchor='center', text='+%.2f' % deal_profit,
                    font=dict(color="green", size=16), arrowcolor="green",
                    arrowhead=1, hovertext=str(deal_profit)
                )
            )
            self.take_profit_deals += 1
            self.profit += deal_profit
            self.all_drawdowns.append(self.drawdown)
            self.drawdown = Decimal(0)
        else:
            self.annotations.append(
                dict(
                    x=date, y=price, xref='x', yref='y',
                    showarrow=True, xanchor='center', text='-%.2f' % deal_profit,
                    font=dict(color="red"), arrowcolor="red",
                    arrowhead=1, hovertext=str(deal_profit)
                )
            )
            self.stop_loss_deals += 1
            self.loss += abs(deal_profit)
            self.drawdown += abs(deal_profit)

    def _add_deal_to_chart(self, deal, date):
        # наносим на график
        self.annotations.append(
            dict(
                x=date, y=1, xref='x', yref='paper',
                showarrow=True, xanchor='left', text=str(deal)
            )
        )
        # рисуем stop loss и take profit
        self.annotations.append(
            dict(
                x=date, y=deal.stop_loss, xref='x', yref='y',
                showarrow=True, xanchor='center', text='sl',
                font=dict(color="red"), arrowcolor="red",
                arrowhead=2, hovertext=str(deal.stop_loss)
            )
        )
        self.annotations.append(
            dict(
                x=date, y=deal.take_profit, xref='x', yref='y',
                showarrow=True, xanchor='center', text='tp',
                font=dict(color="green"), arrowcolor="green",
                arrowhead=2, hovertext=str(deal.take_profit)
            )
        )

    async def do(self):
        try:
            filename = 'history_%s' % symbol.replace('/', '_')

            if update_file:
                r = await api.get_ohlcv(symbol, time_interval, size=5000)
                data = await r.json()

                with open(filename, 'w+') as output_file:
                    json.dump(data, output_file)
            else:
                with open(filename, 'r') as json_file:
                    data = json.load(json_file)

            data = data[:max_candles]
            historical_data = HistoricalData(time_interval, data)
            # fig = historical_data.get_plotly_figure()
            # fig.show()
            # exit()

            # инициируем бота которого будем тестировать
            bot = bot_class(
                money_manager=money_manager,
                historical_ohlcv=[],
                **bot_params
            )

            fig = historical_data.get_plotly_figure()
            open_deal = None

            for candle in historical_data.get_list():
                price = candle.close
                dt = candle.formatted_date

                # проверяем открытую сделку
                if open_deal:
                    profit = open_deal.check(candle)
                    if profit is not None:
                        # закрываем сделку и наносим на график
                        open_deal = None
                        self._handle_deal_profit(profit, dt, price)

                # добавляем свечку к историческим данным
                bot.add_candle(candle)

                # проверяем есть ли сигнал на сделку
                try:
                    possible_deal = await bot.check_price(price)
                    # есть сделка
                    if possible_deal:
                        # если уже есть открытая сделка
                        if open_deal:
                            # если новая сделка в другую сторону
                            if open_deal.side != possible_deal.side:
                                # то закрываем старую сделку и открываем новую
                                profit = open_deal.close(price)
                                if profit is not None:
                                    # закрываем сделку и наносим на график
                                    self._handle_deal_profit(profit, dt, price)

                                open_deal = possible_deal
                                self._add_deal_to_chart(open_deal, dt)
                            else:
                                # сделка в ту же сторону что и уже открытая
                                # @TODO возможно есть смысл переоткрыть сделку
                                pass
                        else:
                            open_deal = possible_deal
                            self._add_deal_to_chart(open_deal, dt)
                except CloseOpenedDeal:
                    if open_deal:
                        profit = open_deal.close(price)
                        if profit is not None:
                            # закрываем сделку и наносим на график
                            self._handle_deal_profit(profit, dt, price)
                        open_deal = None

            fig.update_layout(annotations=self.annotations)
            if show_plot:
                fig.show()
            print("""
            take_profit_deals: {take_profit_deals}
            stop_loss_deals: {stop_loss_deals}
            profit_factor: {profit_factor}
            profit: {profit:.2f}
            loss: {loss:.2f}
            total profit: {total_profit:.2f}$
            max_drawdown: {max_drawdown:.2f}
            """.format(
                take_profit_deals=self.take_profit_deals,
                stop_loss_deals=self.stop_loss_deals,
                profit_factor=self.get_profit_factor(),
                profit=self.profit,
                loss=self.loss,
                total_profit=self.get_total_profit(),
                max_drawdown=self.get_max_drawdown(),
            ))
        finally:
            await api.close()


async def main():
    tester = Tester()
    await tester.do()

    print('done')


if __name__ == '__main__':
    asyncio.run(main())
