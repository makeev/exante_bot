from decimal import Decimal

from bots.base import Signal


class SimpleMoneyManager:

    def __init__(self, order_amount, diff, stop_loss_factor, take_profit_factor, trailing_stop=False):
        self.order_amount = order_amount
        self.diff = Decimal(diff)  # базовая разницу которую умножаем на риски
        self.stop_loss_factor = stop_loss_factor  # размер пропорции sl
        self.take_profit_factor = take_profit_factor  # размер пропорции tp
        self.trailing_stop = trailing_stop

    def get_order_amount(self) -> Decimal:
        """
        Сумма ордера в quote currency
        """
        return self.order_amount

    def get_stop_loss(self, signal, price, factor=None) -> Decimal:
        factor = Decimal(factor or self.stop_loss_factor)

        if signal == Signal.BUY:
            stop_loss = Decimal(price) - Decimal(self.diff * factor)
        else:
            stop_loss = Decimal(price) + Decimal(self.diff * factor)

        return stop_loss

    def get_take_profit(self, signal, price, factor=None) -> Decimal:
        factor = Decimal(factor or self.take_profit_factor)

        if signal == Signal.BUY:
            return Decimal(price) + Decimal(self.diff * factor)
        else:
            return Decimal(price) - Decimal(self.diff * factor)

    async def trailing_stop_check(self, current_price, deal):
        """
        Проверяем надо ли двигать лимиты: перевести сделку в безубыток или трейлить стоп
        """
        if self.trailing_stop:
            if self._is_breakeven_reached(current_price, deal):
                # breakeven
                if deal.side == Signal.BUY:
                    deal.stop_loss = deal.price + 10
                else:
                    deal.stop_loss = deal.price - 10

                # дошли до препрофита
                # deal.stop_loss = self.get_stop_loss(deal.type, current_price, 2)
                # deal.take_profit = self.get_take_profit(deal.type, current_price, 2)

        return deal

    def _is_take_profit_reached(self, price, deal):
        if deal.side == Signal.BUY:
            return price > deal.take_profit - self.diff * 1
        else:
            return price < deal.take_profit + self.diff * 1

    def _is_breakeven_reached(self, price, deal):
        if deal.side == Signal.BUY:
            return price > deal.price + self.diff * 1
        else:
            return price < deal.price - self.diff * 1
