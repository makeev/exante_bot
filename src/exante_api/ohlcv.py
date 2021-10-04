from datetime import datetime
from decimal import Decimal, getcontext
from collections import OrderedDict

import plotly.graph_objects as go


class HistoricalData:
    time_interval = None
    bids = []
    asks = []
    mid_prices = []
    ohlc_data = OrderedDict()
    last_ts = None

    def __init__(self, time_interval: int, historical_data: list):
        self.time_interval = time_interval
        self.load_data(historical_data)

    def load_data(self, historical_data: list):
        for row in reversed(historical_data):
            ts = row['timestamp'] // 1000
            if ts not in self.ohlc_data:
                self.last_ts = ts
                self.ohlc_data[ts] = {
                    "open": Decimal(row['open']),
                    "high": Decimal(row['high']),
                    "low": Decimal(row['low']),
                    "close": Decimal(row['close']),
                }

    def add_data(self, ts, bid: Decimal, ask: Decimal):
        ts_interval = ts // (1000 * self.time_interval) * self.time_interval
        if self.last_ts != ts_interval:
            self.bids = []
            self.asks = []
            self.mid_prices = []
            self.last_ts = ts_interval

        getcontext().prec = 6
        mid_price = bid + (ask - bid) / 2
        self.mid_prices.append(mid_price)
        self.bids.append(bid)
        self.asks.append(ask)

        self.ohlc_data[ts_interval] = self.get_ohlc()

    @property
    def open(self):
        try:
            return self.mid_prices[0]
        except IndexError:
            return None

    @property
    def close(self):
        try:
            return self.mid_prices[-1]
        except IndexError:
            return None

    @property
    def high(self):
        return max(self.mid_prices)

    @property
    def low(self):
        return min(self.mid_prices)

    def get_ohlc(self):
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }

    def get_plotly_figure(self):
        dates = []
        open = []
        high = []
        low = []
        close = []
        for ts, row in self.ohlc_data.items():
            dates.append(datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f'))
            open.append(row['open'])
            high.append(row['high'])
            low.append(row['low'])
            close.append(row['close'])

        fig = go.Figure(data=[
            go.Candlestick(x=dates,
                           open=open,
                           high=high,
                           low=low,
                           close=close,
                           name="candles"
                           ),
        ])
        return fig

    def get_list(self):
        return [{
            "timestamp": ts,
            "open": row['open'],
            "high": row['high'],
            "low": row['low'],
            "close": row['close']
        } for ts, row in self.ohlc_data.items()]