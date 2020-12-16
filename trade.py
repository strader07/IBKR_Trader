
from classes import Tick
from __init__ import *

import json
from sortedcontainers import SortedDict
from datetime import date, datetime
from pytz.reference import Eastern
import time

global tickers
tickers = SortedDict()


def get_ticker(symbol, exchange):
    contracts = [Stock(symbol, exchange, 'USD')]
    ib.qualifyContracts(*contracts)
    ib.reqMarketDataType(4)
    for contract in contracts:
        ib.reqMktData(contract, '', False, False)
    ib.sleep(2)

    tick = ib.ticker(contracts[0])
    ib.sleep(2)
    entryTime = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    price = round(tick.marketPrice(), 2)
    quantity = int(Dollar_Per_Thread/float(price))

    ticker = Tick(price, quantity, exchange, symbol, entryTime)

    return ticker


def get_current_price(symbol, exchange):
    contracts = [Stock(symbol, exchange, 'USD')]
    ib.qualifyContracts(*contracts)
    ib.reqMarketDataType(4)
    for contract in contracts:
        ib.reqMktData(contract, '', False, False)
    ib.sleep(2)

    tick = ib.ticker(contracts[0])
    ib.sleep(2)
    price = round(tick.marketPrice(), 2)

    return price


def num_trades(tickers):
    return len(tickers)


def check_trigger():
    if num_trades(tickers) >= 50:
        print("There are 50 concurrent trades in use now.")
        return None

    print("======================= checking if there is a new ticker...")

    with open('trigger/trigger.json') as f:
        trigger = json.load(f)

    symbol = trigger['ticker']
    exchange = trigger['exchange']
    signal = trigger['signal']
    key = symbol

    if key not in tickers.keys() and signal==1:
        print("Hey, there comes a new ticker...")
        ticker = get_ticker(symbol, exchange)
        tickers[key] = ticker
        tickers[key] = buy_ticker(ticker)
        return None

    if signal==1 and key in tickers.keys():
        print("New ticker not found")
        return None

    if signal==2 and key not in tickers.keys():
        print(f"Sell signal detected, but {key} is not in trade. Skip selling...")
        return None

    if signal==2 and key in tickers.keys() and not tickers[key].buy_filled:
        print(f"Sell signal detected, but {key} buy order is not filled. Skip selling and cancel the order...")
        cancel_trade = ib.cancelOrder(tickers[key].buy_trade.order)
        ib.sleep(2)
        del tickers[key]
        return None

    if signal==2 and tickers[key].buy_filled and not tickers[key].sell_trade:
        print(f"Selling {key}...")
        ticker = tickers[key]
        tickers[key] = sell_ticker(ticker)


def buy_ticker(ticker):
    contracts = [Stock(ticker.symbol, ticker.exchange, 'USD')]
    ib.qualifyContracts(*contracts)

    order = LimitOrder('BUY', ticker.quantity, ticker.price)
    try:
        if ticker.buy_trade.order.orderId == order.orderId:
            order.orderId += 1
    except Exception as e:
        print(e)

    trade = ib.placeOrder(contracts[0], order)
    ticker.buy_trade = trade
    ib.sleep(4)

    if ticker.buy_trade.orderStatus.status == 'Filled' or ticker.buy_trade.orderStatus.filled == ticker.quantity:
        ticker.buy_filled = True

    return ticker


def sell_ticker(ticker):
    contracts = [Stock(ticker.symbol, ticker.exchange, 'USD')]
    ib.qualifyContracts(*contracts)

    price = get_current_price(ticker.symbol, ticker.exchange)
    order = LimitOrder('SELL', ticker.quantity, price)
    try:
        if ticker.sell_trade.order.orderId == order.orderId:
            order.orderId += 1
    except Exception as e:
        print(e)

    trade = ib.placeOrder(contracts[0], order)
    ticker.sell_trade = trade
    ib.sleep(4)

    return ticker


def update_ticker(ticker, direction):
    contracts = [Stock(ticker.symbol, ticker.exchange, 'USD')]
    ib.qualifyContracts(*contracts)
    ib.reqMarketDataType(4)
    for contract in contracts:
        ib.reqMktData(contract, '', False, False)
    ib.sleep(2)
    tick = ib.ticker(contracts[0])
    ib.sleep(2)

    ticker.price = round(tick.marketPrice(), 2)
    if direction=="BUY":
        if ticker.buy_trade:
            if ticker.buy_trade.orderStatus.filled > 0:
                print("Order partially filled... Updating the buy quantity with the remainder...")
                ticker.quantity = int(ticker.quantity - int(ticker.buy_trade.orderStatus.filled))
    if direction=="SELL":
        if ticker.sell_trade:
            if ticker.sell_trade.orderStatus.filled > 0:
                print("Order partially filled... Updating the sell quantity with the remainder...")
                ticker.quantity = int(ticker.quantity - int(ticker.sell_trade.orderStatus.filled))

    return ticker


def check_buy_filled():
    print("======================= checking if buy order is filled...")
    for key in tickers.keys():
        if tickers[key].buy_filled:
            print(key, "=> buy order already filled")
            continue
        else:
            print(key, ": buy order status => ", tickers[key].buy_trade.orderStatus.status)
            if tickers[key].buy_trade.orderStatus.status == 'Filled':
                print("... just filled")
                tickers[key].buy_filled = True
                tickers[key].filled_time = tickers[key].buy_trade.log[-1].time
            else:
                print("buy order not filled, lets cancel it, update the price and buy again")
                if tickers[key].buy_trade.orderStatus.status != 'Cancelled':
                    cancel_trade = ib.cancelOrder(tickers[key].buy_trade.order)
                    tickers[key].buy_trade = cancel_trade
                    ib.sleep(2)

                ticker = update_ticker(tickers[key], "BUY")
                tickers[key] = buy_ticker(ticker)

    print("There are {} active trades...".format(str(num_trades(tickers))))


def check_sell_filled():
    print("======================= checking if sell order is filled...")
    if len(tickers.keys()) < 1:
        print("No trades have been made yet")

    del_keys = []
    for key in tickers.keys():
        if tickers[key].buy_filled:
            if tickers[key].sell_trade:
                if tickers[key].sell_trade.orderStatus.status == "Filled":
                    del_keys.append(key)
                else:
                    print("sell order not filled, lets cancel it, update the price and sell again")
                    if tickers[key].sell_trade.orderStatus.status != 'Cancelled':
                        cancel_trade = ib.cancelOrder(tickers[key].sell_trade.order)
                        tickers[key].sell_trade = cancel_trade
                        ib.sleep(2)
                    ticker = update_ticker(tickers[key], "SELL")
                    tickers[key] = sell_ticker(ticker)

    for key in del_keys:
        print(f"{key} has been sold. Removing {key} from dictionary...")
        del tickers[key]


def sell_leftovers():
    for key in tickers.keys():
        if tickers[key].buy_filled:
            if (tickers[key].sell_trade and tickers[key].sell_trade.orderStatus.status != "Filled") or not tickers[key].sell_trade:
                print(key, ": not sold until the market close")
                print("lets cancel and sell at market price...")
                tickers[key].sell_trade = ib.cancelOrder(tickers[key].sell_trade.order)
                ib.sleep(2)

                contracts = [Stock(tickers[key].symbol, tickers[key].exchange, 'USD')]
                ib.qualifyContracts(*contracts)

                order = MarketOrder("SELL", tickers[key].quantity)
                trade = ib.placeOrder(contracts[0], order)
                ib.sleep(2)

                tickers[key].sell_trade = trade
                tickers[key].sell_filled = (trade.orderStatus.status == "Filled")


def trade():
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        if current_time < "07:30" or current_time > "15:55":
            if current_time > "15:55":
                sell_leftovers()
            break

        print("\ncurrent time: ", datetime.now())

        check_sell_filled()
        check_buy_filled()
        check_trigger()
        time.sleep(1)


if __name__=="__main__":
    trade()