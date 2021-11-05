import asyncio
import json
import logging
import urllib.parse
from json import JSONDecodeError

from termcolor import cprint
import aiohttp
from aiohttp import ServerTimeoutError, ClientConnectorError


class TooManyRequests(Exception):
    pass


class PositionNotFound(Exception):
    pass


class PositionAlreadyClosed(Exception):
    pass


class PositionOrdersNotFound(Exception):
    pass


class ExanteApi:
    def __init__(self, application_id: str, access_key: str, demo: bool, account_id: str, currency: str):
        self.demo = demo
        self.application_id = application_id
        self.access_key = access_key
        self.account_id = account_id
        self.currency = currency.upper()

        self.endpoint_url = 'https://api-demo.exante.eu' if demo else 'https://api-live.exante.eu'
        self._client = None

    def get_auth(self):
        return aiohttp.helpers.BasicAuth(
            login=self.application_id,
            password=self.access_key,
        )

    def get_client(self):
        if not self._client:
            self._client = aiohttp.ClientSession(
                auth=self.get_auth()
            )
        return self._client

    @property
    def client(self):
        return self.get_client()

    @property
    def stream_headers(self):
        return {"Accept": "application/x-json-stream"}

    @property
    def timeout(self):
        return aiohttp.ClientTimeout(total=None, sock_read=30)

    def get_url(self, method, params=None, type=None, version=None):
        if not type:
            type = 'md'
        if not version:
            version = '3.0'
        if params is None:
            params = []

        url = '{endpoint_url}/{type}/{version}/{method}'.format(
            endpoint_url=self.endpoint_url,
            type=type,
            version=version,
            method=method,
        ).rstrip('/')

        quoted_params = []
        for p in params:
            p = str(p)
            quoted_params.append(urllib.parse.quote_plus(p))

        if quoted_params:
            url += '/%s' % "/".join(quoted_params)

        return url.rstrip('/')

    async def close(self):
        if self.client and not self.client.closed:
            await self.client.close()

    async def process_response(self, response, silent=False):
        """
        Ловим тут известные ошибки и логируем запросы
        """
        if not silent:
            if response.status == 429:
                raise TooManyRequests()

        return response

    async def data_stream(self, url, processor):
        """
        Подписка на стрим биржи.
        """
        min_delay = 0.5
        max_delay = 30
        delay = min_delay
        while True:
            cprint(f"Start listening {url}", "blue")
            try:
                async with self.client.get(url, headers=self.stream_headers, timeout=self.timeout) as resp:
                    async for data in resp.content.iter_any():
                        events = self.parse_stream_lines(data)
                        for e in events:
                            await processor(e)
                        delay = min_delay  # reset the delay
            except ServerTimeoutError as e:
                cprint(e, "yellow")
            except ClientConnectorError as e:
                cprint(e, "red")
            except Exception as e:
                logging.exception('on event error:')

            await asyncio.sleep(delay)
            delay = min(max_delay, delay * 2)  # exponential delay

    async def quote_stream(self, symbol, processor):
        """
        Подписка на обновления инструмента
        """
        url_quotes = self.get_url('feed', [symbol], type='md')
        return await self.data_stream(url_quotes, processor)

    # async def trade_stream(self, on_event):
    #     return await self.data_stream(self.url_trades, processor)

    def parse_stream_lines(self, data):
        """
        Распарсить данные стрима
        """
        events = []
        data = data.decode().strip()
        for line in data.split("\n"):
            if not line.strip():
                continue

            try:
                event = json.loads(line)
                events.append(event)
            except JSONDecodeError as e:
                print("JSONDecodeError", line, data)
                raise e
        return events

    async def get_ohlcv(self, symbol_id, duration, size=60, silent=False):
        """
        Получение исторических данных
        """
        url = self.get_url('ohlc', [symbol_id, duration], 'md')
        r = await self.client.get(url, params={"size": size})
        return await self.process_response(r, silent)

    async def get_accounts(self):
        url = self.get_url('accounts')
        r = await self.client.get(url)
        return await self.process_response(r)

    async def get_summary(self, currency=None, account_id=None):
        if currency is None:
            currency = self.currency
        else:
            currency = currency.upper()

        if account_id is None:
            account_id = self.account_id
        else:
            account_id = account_id.upper()

        url = self.get_url('summary', params=[account_id, currency])
        r = await self.client.get(url)
        return await self.process_response(r)

    async def get_active_orders(self):
        url = self.get_url('orders', params=['active'], type='trade')
        r = await self.client.get(url)
        return await self.process_response(r)

    async def get_orders(self, **params):
        url = self.get_url('orders', type='trade')
        r = await self.client.get(url, params=params)
        return await self.process_response(r)

    async def cancel_order(self, order_id):
        url = self.get_url('orders', type='trade', params=[order_id])
        data = {"action": "cancel"}
        r = await self.client.post(url, json=data)
        return await self.process_response(r)

    async def update_order(self, order_id, data):
        url = self.get_url('orders', type='trade', params=[order_id])
        data = {"action": "replace", "parameters": data}
        r = await self.client.post(url, json=data)
        return await self.process_response(r)

    async def place_order(self, data):
        url = self.get_url('orders', type='trade')
        r = await self.client.post(url, json=data)
        return await self.process_response(r)

    async def move_to_breakeven(self, symbol):
        r = await self.get_orders(limit=20)
        orders = await r.json()

        sl_order = None
        tp_order = None
        initial_order = None
        for o in orders:
            if o['orderParameters']['symbolId'] != symbol:
                continue

            if initial_order and sl_order and tp_order:
                break

            if o['orderParameters'].get('stopPrice') and o['orderState']['status'] == 'working':
                sl_order = o
            elif o['orderParameters'].get('limitPrice') and o['orderState']['status'] == 'working':
                tp_order = o
            elif o['orderParameters'].get('orderType') == 'market':
                initial_order = o

        if not initial_order or not sl_order or not tp_order:
            raise PositionOrdersNotFound()

        stop_loss = float(sl_order['orderParameters']['stopPrice'])
        new_stop_loss = float(initial_order['orderState']['fills'][0]['price']) * 1.0002
        if stop_loss < new_stop_loss:
            r = await self.update_order(
                sl_order['orderId'],
                {
                    "stopPrice": '%.2f' % new_stop_loss,
                    "quantity": sl_order['orderParameters']['quantity']
                }
            )
            text = await r.text()
            error = '%s %s' % (r.status, text)
            assert r.status == 202, error
            return r

    async def open_position(self,symbol, side, quantity, take_profit, stop_loss, account_id=None, duration=None):
        if account_id is None:
            account_id = self.account_id
        else:
            account_id = account_id.upper()

        if not duration:
            duration = 'good_till_cancel'

        r = await self.place_order({
            "accountId": account_id,
            "symbolId": symbol,
            "side": side,
            "quantity": str(quantity),
            "orderType": "market",
            "duration": duration,
            "takeProfit": str(take_profit),
            "stopLoss": str(stop_loss),
        })

        # костыль, т.к. метод не дает поставить разные duration для stop и market ордеров
        placed_orders = await r.json()
        for o in placed_orders:
            if o['orderParameters']['orderType'] in ['stop', 'limit']:
                # отменяем старые ордера
                await self.cancel_order(o['orderId'])

                # ставим новые с правильным duration
                data = {
                    "duration": "good_till_cancel",
                    "quantity": o['orderParameters']['quantity'],
                    "accountId": self.account_id,
                    "symbolId": symbol,
                    "side": o['orderParameters']['side'],
                    "orderType": o['orderParameters']['orderType'],
                }

                stop_price = o['orderParameters'].get('stopPrice')
                if stop_price:
                    data['stopPrice'] = stop_price

                limit_price = o['orderParameters'].get('limitPrice')
                if limit_price:
                    data['limitPrice'] = limit_price

                await self.place_order(data)

    async def get_position(self, symbol, account_id=None):
        r = await self.get_summary(account_id=account_id, currency='EUR')
        account_summary = await r.json()
        position = None

        for pos in account_summary.get('positions', []):
            if pos['symbolId'] == symbol:
                position = pos
                break

        if position and float(position['quantity']) != 0:
            return position

    async def cancel_active_orders(self, symbol):
        r = await self.get_active_orders()
        orders = await r.json()

        result = []
        for o in orders:
            if o['orderParameters']['symbolId'] != symbol:
                continue

            r = await self.cancel_order(o['orderId'])
            result.append(r)

        return result

    async def close_position(self, symbol, account_id=None, position=None, duration=None):
        """
        raise PositionNotFound and PositionAlreadyClosed
        """
        if account_id is None:
            account_id = self.account_id
        else:
            account_id = account_id.upper()

        if not duration:
            duration = 'good_till_cancel'

        # получаем данные по открытой позиции
        if not position:
            position = await self.get_position(symbol=symbol, account_id=account_id)

        if not position:
            raise PositionNotFound()

        if float(position['quantity']) == 0:
            raise PositionAlreadyClosed()

        if float(position['quantity']) > 0:
            side = 'sell'
        else:
            side = 'buy'

        quantity = str(abs(float(position['quantity'])))

        # отменяем все открытые ордера
        await self.cancel_active_orders(symbol=symbol)

        # закрываем позицию по рынку
        return await self.place_order({
            "accountId": account_id,
            "symbolId": symbol,
            "side": side,
            "quantity": quantity,
            "orderType": "market",
            "duration": duration,
        })

    async def get_last_quote(self, symbol):
        """
        [
           {
              "timestamp":1633349235472,
              "symbolId":"BTC.USD",
              "bid":[
                 {
                    "price":"47647.69",
                    "size":"0.34000000"
                 }
              ],
              "ask":[
                 {
                    "price":"47677.23",
                    "size":"0.24000000"
                 }
              ]
           }
        ]
        """
        url = self.get_url('feed', params=[symbol, 'last'])
        r = await self.client.get(url)
        return await self.process_response(r)
