import argparse
import asyncio
from datetime import datetime

from pymongo import MongoClient, ReplaceOne
from slugify import slugify

import settings
from exante_api import ExanteApi
from exante_api.client import TooManyRequests

MONGO_HOST = 'localhost'
MONGO_PORT = 27017

parser = argparse.ArgumentParser(description='OHLCV data parser')
parser.add_argument('--symbol', dest='symbol', action='store', required=True)
parser.add_argument('--time-interval', dest='time_interval', action='store', type=int,
                    required=True, help='interval in seconds, 60 - 1min, 300 - 5min, etc')
parser.add_argument('--from-date', dest='from_date', action='store', required=False,
                    help='date format %Y-%m-%d %H:%M')
parser.add_argument('--to-date', dest='to_date', action='store', required=False,
                    help='date format %Y-%m-%d %H:%M')


async def main(symbol, time_interval, from_date=None, to_date=None):
    date_format = '%Y-%m-%d %H:%M'
    from_ts = None
    if from_date is not None:
        from_ts = int(datetime.timestamp(datetime.strptime(from_date, date_format)) * 1000)

    to_ts = None
    if to_date is not None:
        to_ts = int(datetime.timestamp(datetime.strptime(to_date, date_format)) * 1000)

    # init db
    collection_name = slugify('exante_%s_%s' % (symbol, time_interval))
    mongo = MongoClient(MONGO_HOST, MONGO_PORT)
    db = mongo.ohlcv
    collection = db[collection_name]
    collection.create_index('timestamp')
    print('collection: %s' % collection_name)

    # init api
    api = ExanteApi(**settings.ACCOUNTS['demo_2'])

    max_ohlcv_size = 5000
    last_parsed_ts = None
    while True:
        try:
            r = await api.get_ohlcv(symbol, time_interval, from_ts=from_ts, to_ts=to_ts, size=max_ohlcv_size)
            data = await r.json()
            data = list(reversed(data))

            if last_parsed_ts and data[-1]['timestamp'] == last_parsed_ts:
                print('last ts %s' % last_parsed_ts)
                break

            mongo_requests = []
            for row in data:
                last_parsed_ts = row['timestamp']
                if last_parsed_ts == to_ts:
                    print('stop by to_ts')
                    break
                mongo_requests.append(ReplaceOne({"timestamp": last_parsed_ts}, row, upsert=True))

            collection.bulk_write(mongo_requests)

            if len(data) < max_ohlcv_size:
                print('%d rows returned, stop' % len(data))
                break

            from_ts = last_parsed_ts
        except TooManyRequests:
            print('TooManyRequests')
            await asyncio.sleep(60)


if __name__ == '__main__':
    args = parser.parse_args()
    asyncio.run(main(**vars(args)))
