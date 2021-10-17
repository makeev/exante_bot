from datetime import datetime
from decimal import Decimal, getcontext
from collections import OrderedDict

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from talib._ta_lib import RSI, SMA

from bots.base import CandleStick


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

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.2,
            row_heights=[1000, 250]
            # row_width=[0.5, 0.5]
        )

        # candles
        fig.add_trace(
            go.Candlestick(x=dates,
                           open=open,
                           high=high,
                           low=low,
                           close=close,
                           name="candles"
                           ),
            row=1, col=1
        )

        # SMA
        fig.add_trace(go.Scatter(
            x=dates,
            y=self.get_sma(100),
            name="SMA",
            yaxis="y1",
            line=dict(color='blue', width=2),
            legendgroup="sma",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=dates,
            y=self.get_sma(50),
            name="SMA",
            yaxis="y1",
            line=dict(color='red', width=2),
            legendgroup="sma",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=dates,
            y=self.get_sma(30),
            name="SMA",
            yaxis="y1",
            line=dict(color='green', width=2),
            legendgroup="sma",
        ), row=1, col=1)

        # RSI
        fig.add_trace(go.Scatter(
            x=dates,
            y=self.get_rsi(),
            name="RSI",
            yaxis="y3",
            line=dict(color='purple', width=2),
            legendgroup="rsi",
        ), row=2, col=1)
        fig.add_hrect(y0=30, y1=70,
                      fillcolor="purple",
                      opacity=0.2,
                      line_width=0, row=2, col=1)


        return fig

    def get_list(self):
        return [CandleStick(**{
            "timestamp": ts,
            "open": row['open'],
            "high": row['high'],
            "low": row['low'],
            "close": row['close']
        }) for ts, row in self.ohlc_data.items()]

    def get_last_candle(self):
        # возвращаем последнюю сформированную свечу
        return self.get_list()[-2]

    def get_rsi(self, length=14):
        close_array = [float(c['close']) for c in self.ohlc_data.values()]
        return RSI(np.array(close_array), length)

    def get_sma(self, length=100):
        close_array = [float(c['close']) for c in self.ohlc_data.values()]
        return SMA(np.array(close_array), length)
