import csv
import time

import ujson

filepath = 'data/1yr_aapl_5min.csv'

json_l = []
with open(filepath) as csvfile:
    reader = csv.reader(csvfile)

    counter = 0
    for row in reader:
        counter += 1
        dt_str = '%s %s' % (row[1], row[2])
        try:
            ts = time.strptime(dt_str, '%Y%m%d %H%M')
        except ValueError as e:
            print(e)
            continue

        o = row[3]
        h = row[4]
        l = row[5]
        c = row[6]
        timestamp = int(time.mktime(ts)) * 1000

        json_dict = {
            "timestamp": timestamp,
            "open": o,
            "low": l,
            "close": c,
            "high": h,
        }
        json_l.append(json_dict)
        # print(json_dict)

        # if counter > 5:
        #     break

if len(json_l) > 0:
    json_l = list(reversed(json_l))
    with open("data/aapl_5min.jsonl", 'w+') as output_file:
        ujson.dump(json_l, output_file)
