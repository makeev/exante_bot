"""
curl -u user:password 'https://api-demo.exante.eu/md/3.0/symbols' > src/symbols.json

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS symbols_id_seq;

-- Table Definition
CREATE TABLE "public"."symbols" (
    "id" int4 NOT NULL DEFAULT nextval('symbols_id_seq'::regclass),
    "name" bpchar(1000),
    "symbol_id" bpchar(101),
    "description" bpchar(2000),
    "exchange" bpchar(103),
    "symbol_type" bpchar(104),
    "currency" bpchar(105),
    "ticker" bpchar(106),
    "symbol_group" bpchar(107),
    PRIMARY KEY ("id")
);
"""
import argparse
import json

import psycopg2


if __name__ == '__main__':
    conn = psycopg2.connect(
        host="localhost",
        database="exante",
        user="user2",
        password="user2"
    )

    parser = argparse.ArgumentParser()
    parser.add_argument('--file', dest='file', type=argparse.FileType('r'))
    args = parser.parse_args()

    f = args.file
    json_data = json.loads(f.read())

    cur = conn.cursor()
    try:
        for row in json_data:
            print(row)
            sql = "INSERT INTO symbols(name, symbol_id, description, exchange, symbol_type, currency, ticker, symbol_group, underlying_symbol_id) " \
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            cur.execute(sql, (
                row['name'],
                row['symbolId'],
                row['description'],
                row['exchange'],
                row['symbolType'],
                row['currency'],
                row['ticker'],
                row['group'],
                row['underlyingSymbolId']
            ))

        conn.commit()
    finally:
        cur.close()

