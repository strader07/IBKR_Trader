
class Tick(object):

    def __init__(self,price,quantity,exchange,symbol,volume,entryTime,triggered_time):
        self.price = price
        self.quantity = quantity
        self.exchange = exchange
        self.symbol = symbol
        self.volume = volume
        self.entryTime = entryTime
        self.triggered_time = triggered_time
        self.exitTime = ""
        self.buy_trade = None
        self.sell_trade = None

        self.buy_filled = False
        self.filled_time = None
