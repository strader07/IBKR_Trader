
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

    print("======================= checking if there is a new trigger...")

    with open('trigger/trigger.json') as f:
        trigger = json.load(f)

    symbol = trigger['ticker']
    if "." in symbol:
        print(f"Discarding {symbol}...")
        return None
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

    order = MidPriceOrder('BUY', ticker.quantity, None)
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

    order = MidPriceOrder('SELL', ticker.quantity, None)
    try:
        if ticker.sell_trade.order.orderId == order.orderId:
            order.orderId += 1
    except Exception as e:
        print(e)

    trade = ib.placeOrder(contracts[0], order)
    ticker.sell_trade = trade
    ib.sleep(4)

    return ticker


def check_buy_filled():
    print("======================= checking if buy order is filled...")
    for key in tickers.keys():
        # print(tickers[key].buy_trade)
        if tickers[key].buy_filled:
            print(key, "=> buy order already filled")
            continue
        else:
            print(key, ": buy order status => ", tickers[key].buy_trade.orderStatus.status)
            if tickers[key].buy_trade.orderStatus.status == 'Filled':
                print("... just filled")
                tickers[key].buy_filled = True
                tickers[key].filled_time = tickers[key].buy_trade.log[-1].time

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

    for key in del_keys:
        print(f"{key} has been sold. Removing {key} from dictionary...")
        del tickers[key]


def update_threshold(key, price_now):
    price_fill = tickers[key].buy_trade.orderStatus.avgFillPrice
    price_chng = int((price_now - price_fill)*100/price_fill)
    if price_chng >= 1 and price_chng < 2:
        threshold = 1
    elif price_chng >= 2 and price_chng < 10:
        threshold = 2
    else:
        threshold = int( price_chng / 10 ) * 10

    if threshold > 0:
        print(f"{key} updating price threshold...")
        print(f"{key} original price threshold: ", tickers[key].current_threshold)
        print(f"{key} current price threshold: {threshold}")
        tickers[key].current_threshold = threshold
    else:
        print(f"{key} current price threshold: ", tickers[key].current_threshold)
        print(f"{key} current price, filled price: {price_now}, {price_fill}")
        print(f"{key} price change: {(price_now - price_fill)*100/price_fill}")


def check_to_sell_by_pricechange():
    print("======================= checking if price change can trigger selling...")
    for key in tickers.keys():
        if tickers[key].buy_filled:
            try:
                if tickers[key].sell_trade.orderStatus.status != "Filled":
                    continue
            except:
                pass

            price_now = get_current_price(tickers[key].symbol, tickers[key].exchange)
            price_fill = tickers[key].buy_trade.orderStatus.avgFillPrice
            price_chng = int((price_now - price_fill)*100/price_fill)
            if price_chng <= -2:
                print(f"{key} price going down by (2%) below the fill price. Sell it.")
                ticker = tickers[key]
                tickers[key] = sell_ticker(ticker)
                continue
            if tickers[key].current_threshold > 0:
                if price_chng <= tickers[key].current_threshold:
                    print(f"{key} Price Change: ", price_chng)
                    print(f"{key}'s price going down to the current threshold. Selling {key}...")
                    ticker = tickers[key]
                    tickers[key] = sell_ticker(ticker)
                    continue

            update_threshold(key, price_now)


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

        print("\n\ncurrent time: ", datetime.now())

        check_sell_filled()
        check_buy_filled()
        check_to_sell_by_pricechange()
        check_trigger()
        time.sleep(1)


if __name__=="__main__":
    trade()