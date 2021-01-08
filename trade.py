
from classes import Tick
from __init__ import *

import json
from sortedcontainers import SortedDict
from datetime import date, datetime
from pytz.reference import Eastern
import time

global tickers
tickers = SortedDict()
BUY = 1
SELL = 2


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
    price = tick.marketPrice() // 0.01 / 100

    return price


def num_trades(tickers):
    return len(tickers)


def check_trigger():
    if num_trades(tickers) >= 50:
        print("There are 50 concurrent trades in use now.")
        return None

    print("\n============ Checking a new trigger...")

    with open('trigger/trigger.json') as f:
        trigger = json.load(f)

    symbol = trigger['ticker']
    exchange = trigger['exchange']
    signal = trigger['signal']
    key = symbol

    if key not in tickers.keys() and signal==BUY:
        print("Hey, there comes a new ticker...")
        ticker = get_ticker(symbol, exchange)
        tickers[key] = ticker
        tickers[key] = buy_ticker(ticker)
        return None

    if signal==BUY and key in tickers.keys():
        print("New ticker not found")
        return None

    if signal==SELL and key not in tickers.keys():
        print(f"Sell signal, but {key} is not in trade. Skip selling...")
        return None

    if signal==SELL and key in tickers.keys() and not tickers[key].buy_filled:
        print(f"Sell signal, but {key} buy order is not filled. Skip selling and cancel the order...")
        cancel_trade = ib.cancelOrder(tickers[key].buy_trade.order)
        ib.sleep(2)
        del tickers[key]
        return None

    if signal==SELL and tickers[key].buy_filled and not tickers[key].sell_trade:
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


def sell_ticker(ticker, price=None):
    contracts = [Stock(ticker.symbol, ticker.exchange, 'USD')]
    ib.qualifyContracts(*contracts)

    if not price:
        limitPrice = get_current_price(ticker.symbol, ticker.exchange)
    else:
        limitPrice = price
    order = LimitOrder('SELL', ticker.quantity, limitPrice)
    try:
        if ticker.sell_trade.order.orderId == order.orderId:
            order.orderId += 1
    except Exception as e:
        print(e)

    trade = ib.placeOrder(contracts[0], order)
    ticker.sell_trade = trade
    ib.sleep(4)

    return ticker


def check_order_filled():
    print("\n============ Checking buy/sell order status...")
    if len(tickers.keys()) < 1:
        print("No trades have been made yet")
        return None

    del_keys = []
    for key in tickers.keys():
        buy_status = tickers[key].buy_trade.orderStatus.status
        if buy_status == 'Filled':
            tickers[key].buy_filled = True
        else:
            print(f"{key} || Buy: {buy_status} || Sell: Not Triggered")
            continue
        if tickers[key].buy_filled:
            if tickers[key].sell_trade:
                sell_status = tickers[key].sell_trade.orderStatus.status
                if sell_status == "Filled":
                    tickers[key].sell_filled = True
                    del_keys.append(key)
                    print(f"{key} || Buy: {buy_status} || Sell: {sell_status}")
                else:
                    print(f"{key} || Buy: {buy_status} || Sell: {sell_status}")
                continue
            print(f"{key} || Buy: {buy_status} || Sell: Not Triggered")
            continue

    for key in del_keys:
        print(f"{key} has been sold. Removing {key} from ticker dictionary...")
        del tickers[key]

    print("There are {} active trades!".format(str(num_trades(tickers))))


def check_to_sell_by_pricechange():
    print("\n============ Checking sell by price change...")
    for key in tickers.keys():
        if tickers[key].buy_filled:
            try:
                if tickers[key].sell_trade.orderStatus.status != "Filled":
                    print(f"{key}: sell already triggered.")
                    continue
            except:
                pass

            price_now = get_current_price(tickers[key].symbol, tickers[key].exchange)
            price_fill = tickers[key].buy_trade.orderStatus.avgFillPrice
            price_chng = int((price_now - price_fill)*100/price_fill)
            if price_chng <= -3:
                print(f"{key} - price going down by (3%) below the fill price. Sell it.")
                ticker = tickers[key]
                tickers[key] = sell_ticker(ticker, price_now)
                continue
            print(f"{key} - price change: {price_chng} %")


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
    rth = True
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        if current_time < "07:30":
            print("Market is not open!")
            print(f"Current time: {datetime.now()}\n")
            time.sleep(60)
            continue
        if current_time > "15:59" and rth==True:
            print("End of regular trading hours!")
            sell_leftovers()
            rth = False
            print("Start trading extended hours!")
        if current_time > "19:59":
            print("End of the day trading. Close all open positions!")
            sell_leftovers()
            print("Closing the program.")
            break

        print("\n\n************ Time: ", datetime.now(), " ***********")

        check_order_filled()
        check_to_sell_by_pricechange()
        check_trigger()

        print("\n**************************** * ****************************")
        time.sleep(1)


if __name__=="__main__":
    trade()