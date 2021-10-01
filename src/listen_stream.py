import asyncio
from datetime import datetime

import plotly.graph_objects as go

from exante_api import ExanteApi, Event, HistoricalData

application_id = 'e2b62931-4cf2-4b6f-a319-b94f1a6341f5'
access_key = 'jf5ODSu3jZ8DQXhxdlTN'
demo = True
api = ExanteApi(application_id=application_id, access_key=access_key, demo=demo)
# symbol = 'EUR/USD.E.FX'
symbol = 'BTC.USD'
time_interval = 60


class Processor:
    def __init__(self, historical_data: HistoricalData):
        self.historical_data = historical_data

    async def on_event(self, data):
        e = Event(data)
        if e.type == 'new_price':
            last_ts = self.historical_data.last_ts
            self.historical_data.add_data(e.ts, e.bid, e.ask)
            if last_ts and last_ts != self.historical_data.last_ts:
                # new candle created
                print('new candle started')
                print(datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S.%f'))
                print(datetime.fromtimestamp(self.historical_data.last_ts).strftime('%Y-%m-%d %H:%M:%S.%f'))
                print(last_ts, self.historical_data.last_ts)
                self.historical_data.get_plotly_figure().show()


async def main():
    try:
        r = await api.get_ohlcv(symbol, time_interval, size=100)
        data = await r.json()
        # data = []
        historical_data = HistoricalData(time_interval, data)

        fig = historical_data.get_plotly_figure()
        fig.show()

        processor = Processor(historical_data)

        # await api.quote_stream('BTC.USD', processor)
        await api.quote_stream(symbol, processor.on_event)
    finally:
        await api.close()

    print('done')


if __name__ == '__main__':
    asyncio.run(main())
