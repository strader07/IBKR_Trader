
class Tick(object):

    def __init__(self,price,quantity,exchange,symbol,entryTime):
        self.price = price
        self.quantity = quantity
        self.exchange = exchange
        self.symbol = symbol
        self.entryTime = entryTime

        self.buy_trade = None
        self.sell_trade = None
        self.buy_filled = False
        self.sell_filled = False

        self.current_threshold = 0