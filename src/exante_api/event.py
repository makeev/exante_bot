from decimal import Decimal


class Event:
    type = None
    bid = None
    ask = None
    spread = None
    ts = None

    def __init__(self, data):
        self.type = data.get('event')
        self.ts = data.get('timestamp')

        if not self.type:
            self.type = 'undefined'

        if data.get('ask') and data.get('bid'):
            self.type = 'new_price'
            self.bid = Decimal(data.get('bid')[0]['price'])
            self.ask = Decimal(data.get('ask')[0]['price'])
            self.spread = self.ask - self.bid

