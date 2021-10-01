import asyncio
import json
import urllib.parse
from json import JSONDecodeError

from termcolor import cprint
import aiohttp
from aiohttp import ServerTimeoutError, ClientConnectorError


class TooManyRequests(Exception):
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

    def get_url(self, method, params, type=None, version=None):
        if not type:
            type = 'md'
        if not version:
            version = '3.0'

        quoted_params = []
        for p in params:
            p = str(p)
            quoted_params.append(urllib.parse.quote_plus(p))

        return '{endpoint_url}/{type}/{version}/{method}/{params}'.format(
            endpoint_url=self.endpoint_url,
            type=type,
            version=version,
            method=method,
            params="/".join(quoted_params)
        ).rstrip('/')

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
