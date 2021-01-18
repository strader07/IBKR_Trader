
from ib_insync import *
from config import PAPER_ACCOUNT, MAX_DOWN, TRAILING_PERC


ib = IB()
ib.connect('127.0.0.1', 7497, clientId=23)

Dollar_Per_Thread = 1000.0
accounts = ib.accountSummary(account=PAPER_ACCOUNT)
for account in accounts:
    if account.tag == 'AvailableFunds':
        Dollar_Per_Thread = float(account.value)/50

print(Dollar_Per_Thread)
