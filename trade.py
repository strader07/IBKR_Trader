
from classes import Tick
from __init__ import *

import json
from sortedcontainers import SortedDict
from datetime import date, datetime
from pytz.reference import Eastern

global tickers
tickers = SortedDict()

def get_ticker():

    with open('trigger/trigger.json') as f:
        trigger = json.load(f)

    symbol = trigger['ticker']
    exchange = trigger['exchange']
    key = trigger['time'] + ' ' + symbol
    if key in tickers.keys():
        ib.sleep(1)
        return tickers[key]

    contracts = [Stock(symbol, exchange, 'USD')]
    ib.qualifyContracts(*contracts)
    ib.reqMarketDataType(4)
    for contract in contracts:
        ib.reqMktData(contract, '', False, False)
    ib.sleep(2)

    tick = ib.ticker(contracts[0])
    ib.sleep(2)
    entryTime = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    price = tick.marketPrice()
    quantity = int(Dollar_Per_Thread/float(price))

    ticker = Tick(price, quantity, trigger['exchange'], trigger['ticker'], trigger['volume'], entryTime, trigger['time'])

    return ticker


def num_trades(tickers):
    return len([1 for ticker in tickers.values() if ticker.buy_filled])


def check_new_ticker():

    print("======================= checking if there is a new ticker...")

    ticker = get_ticker()
    key = ticker.triggered_time + ' ' + ticker.symbol

    if not key in tickers.keys() and num_trades(tickers) < 50:
        print("Hey, there is a new ticker, come added...")
        tickers[key] = ticker
        tickers[key] = buy_ticker(ticker)

    else:
        print("New ticker not found")


def buy_ticker(ticker):
    contracts = [Stock(ticker.symbol, ticker.exchange, 'USD')]
    ib.qualifyContracts(*contracts)

    order = LimitOrder('BUY', ticker.quantity, ticker.price)

    trade = ib.placeOrder(contracts[0], order)
    ticker.buy_trade = trade

    ib.sleep(1)

    return ticker


def sell_ticker(ticker):
    contracts = [Stock(ticker.symbol, ticker.exchange, 'USD')]
    ib.qualifyContracts(*contracts)

    stop_loss = round(ticker.buy_trade.orderStatus.avgFillPrice * (1 - MAX_DOWN/100), 2)
    order = TrailingStopOrder('SELL', ticker.quantity, TRAILING_PERC, stop_loss)

    trade = ib.placeOrder(contracts[0], order)
    ticker.sell_trade = trade

    return ticker


def check_buy_filled():
    print("=================== checking if buy order is filled...")
    for key in tickers.keys():
        if tickers[key].buy_filled:
            print(key, "=> buy order already filled")
            continue
        else:
            print(key, ": buy order status=> ", tickers[key].buy_trade.orderStatus.status)
            if tickers[key].buy_trade.orderStatus.status == 'Filled':
                print("... just filled")
                tickers[key].buy_filled = True
                tickers[key].filled_time = tickers[key].buy_trade.log[-1].time
            if tickers[key].buy_trade.orderStatus.status == 'Cancelled':
                print("buy order has been cancelled, lets buy again")
                tickers[key] = buy_ticker(tickers[key])

    print("There are {} active trades...".format(str(num_trades(tickers))))


def sell_tickers():
    for key in tickers.keys():
        if tickers[key].buy_filled and not tickers[key].sell_trade:
            print("selling {} ...".format(key))
            contracts = [Stock(tickers[key].symbol, tickers[key].exchange, 'USD')]
            ib.qualifyContracts(*contracts)
            stop_loss = round(tickers[key].buy_trade.orderStatus.avgFillPrice * (1 - MAX_DOWN/100), 2)

            order = TrailingStopOrder('SELL', tickers[key].quantity, TRAILING_PERC, stop_loss)
            trade = ib.placeOrder(contracts[0], order)
            tickers[key].sell_trade = trade

            ib.sleep(2)


def check_timer_45():
    print("======================= checking if a trade lasts for more than 45 mins...")
    if len(tickers.keys()) < 1:
        print("No trades have been made yet")

    for key in tickers.keys():
        if tickers[key].buy_filled:
            if (tickers[key].sell_trade and tickers[key].sell_trade.orderStatus.status != "Filled") or not tickers[key].sell_trade:
                diff = datetime.utcnow() - tickers[key].filled_time.replace(tzinfo=None)
                print(key, ": in trade for {} mins by now (trailing not filled)".format(str(round(diff.seconds/60, 2))))
                print(key, ": sell order status=> ", tickers[key].sell_trade.orderStatus.status)

                if diff.seconds > 45*60:
                    print("{} is not sold for 45 mins, selling market order instead...")
                    contracts = [Stock(tickers[key].symbol, tickers[key].exchange, 'USD')]
                    ib.qualifyContracts(*contracts)

                    order = MarketOrder("SELL", tickers[key].quantity)
                    trade = ib.placeOrder(contracts[0], order)
                    ib.sleep(2)

                    tickers[key].sell_trade = trade

            if (tickers[key].sell_trade and tickers[key].sell_trade.orderStatus.status == "Cancelled"):
                print(key, "sell order cancelled, placing sell order again...")
                contracts = [Stock(tickers[key].symbol, tickers[key].exchange, 'USD')]
                ib.qualifyContracts(*contracts)

                stop_loss = round(tickers[key].buy_trade.orderStatus.avgFillPrice * (1 - MAX_DOWN/100), 2)
                order = TrailingStopOrder('SELL', tickers[key].quantity, TRAILING_PERC, stop_loss)

                trade = ib.placeOrder(contracts[0], order)
                tickers[key].sell_trade = trade


def sell_leftovers():
    for key in tickers.keys():
        if tickers[key].buy_filled:
            if (tickers[key].sell_trade and tickers[key].sell_trade.orderStatus.status != "Filled") or not tickers[key].sell_trade:
                print(key, ": not sold until the market close")
                print("lets sell...")
                contracts = [Stock(tickers[key].symbol, tickers[key].exchange, 'USD')]
                ib.qualifyContracts(*contracts)

                order = MarketOrder("SELL", tickers[key].quantity)
                trade = ib.placeOrder(contracts[0], order)
                ib.sleep(2)

                tickers[key].sell_trade = trade


def trade():

    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        if current_time < "07:30" or current_time > "15:55":
            if current_time > "15:55":
                sell_leftovers()
            break

        print("\ncurrent time: ", datetime.now())
        
        check_timer_45()
        check_new_ticker()
        check_buy_filled()
        sell_tickers()


if __name__=="__main__":
    trade()