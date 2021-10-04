import asyncio
import json
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


class ExanteApi:
    def __init__(self, application_id: str, access_key: str, demo: bool = False):
        self.demo = demo
        self.endpoint_url = 'https://api-demo.exante.eu' if demo else 'https://api-live.exante.eu'
        self.application_id = application_id
        self.access_key = access_key
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
                cprint(e, "red")

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

    async def get_summary(self, account_id, currency):
        currency = currency.upper()
        url = self.get_url('summary', params=[account_id, currency])
        r = await self.client.get(url)
        return await self.process_response(r)

    async def get_active_orders(self):
        url = self.get_url('orders', params=['active'], type='trade')
        r = await self.client.get(url)
        return await self.process_response(r)

    async def get_orders(self):
        url = self.get_url('orders', type='trade')
        r = await self.client.get(url)
        return await self.process_response(r)

    async def place_order(self, data):
        url = self.get_url('orders', type='trade')
        r = await self.client.post(url, json=data)
        return await self.process_response(r)

    async def open_position(self, account_id, symbol, side, quantity, take_profit, stop_loss):
        return await self.place_order({
            "accountId": account_id,
            "symbolId": symbol,
            "side": side,
            "quantity": str(quantity),
            "orderType": "market",
            "duration": "good_till_cancel",
            "takeProfit": str(take_profit),
            "stopLoss": str(stop_loss),
        })

    async def close_position(self, account_id, symbol):
        """
        raise PositionNotFound and PositionAlreadyClosed
        :param account_id:
        :param symbol:
        :return: response object
        """
        # получаем данные по открытой позиции
        account_summary = await self.get_summary(account_id, 'EUR')
        position = None
        for pos in account_summary.get('positions', []):
            if pos['symbolId'] == symbol:
                position = pos
                break

        if not position:
            raise PositionNotFound()

        if float(position['quantity']) == 0:
            raise PositionAlreadyClosed()

        if float(position['quantity']) > 0:
            side = 'sell'
        else:
            side = 'buy'

        quantity = str(abs(float(position['quantity'])))

        # закрываем позицию по рынку
        return await self.place_order({
            "accountId": account_id,
            "symbolId": symbol,
            "side": side,
            "quantity": quantity,
            "orderType": "market",
            "duration": "good_till_cancel",
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
