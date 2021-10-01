import asyncio
from datetime import datetime
from decimal import Decimal

import plotly.graph_objects as go

from exante_api import ExanteApi, Event, HistoricalData

application_id = 'e2b62931-4cf2-4b6f-a319-b94f1a6341f5'
access_key = 'jf5ODSu3jZ8DQXhxdlTN'
demo = True
api = ExanteApi(application_id=application_id, access_key=access_key, demo=demo)
symbol = 'BTC.USD'


async def main():
    try:
        time_interval = 60
        r = await api.get_ohlcv(symbol, time_interval, size=100)
        data = await r.json()
        # data = []
        historical_data = HistoricalData(time_interval, data)

        fig = historical_data.get_plotly_figure()
        fig.show()
    finally:
        await api.close()

    print('done')


if __name__ == '__main__':
    asyncio.run(main())
