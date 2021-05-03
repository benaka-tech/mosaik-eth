import pandas as pandas
from networkx.drawing.tests.test_pylab import plt
import pytest
from web3 import Web3, HTTPProvider
import numpy as np
import json
import csv
web3 = Web3(HTTPProvider('http://localhost:8545'))

# Get contract signature
with open('../ethereum/build/contracts/Market.json') as energy_file:
    energy_json = json.load(energy_file)
contract_abi = energy_json['abi']
network_id = list(energy_json['networks'].keys())[-1]
contract_address = energy_json['networks'][network_id]['address']

# List accounts and set default account
accounts = web3.eth.accounts
web3.eth.defaultAccount = accounts[0]
contract = web3.eth.contract(abi=contract_abi, address=contract_address)
energy_posted_event = contract.events.energy_posted_event().createFilter(fromBlock='earliest')
market_cleared_event = contract.events.market_cleared_event().createFilter(fromBlock='earliest')
bill_sent_event = contract.events.bill_sent_event().createFilter(fromBlock='earliest')
participant_at_clearing_request = contract.events.participant_at_clearing_request().createFilter(fromBlock='earliest')
print(accounts)
#print(energy_posted_event.get_all_entries())
print(market_cleared_event.get_all_entries())
#print('Number of accounts ' + str(len(accounts)))
#print('Number of participants ' + str(contract.functions.number_of_participant().call()))
mar=market_cleared_event.get_all_entries()
time = pandas.date_range(start='2017-09-21 00:00:00', periods=len(market_cleared_event.get_all_entries()), freq='15T')
yb = [block['args']['_buy'] for block in mar]
ys = [block['args']['_sell'] for block in mar]
yr = [block['args']['_ratio'] for block in mar]

# Create plot
plt.figure(figsize=(11, 5), dpi=200)
plt.plot(time, yb, label='Local buy price', linewidth=2, alpha=1)
plt.plot(time, ys, label='Local sell price', linewidth=2, alpha=0.7)
plt.plot(time, [100] * len(time), '--', label='Utility sell price', linewidth=4, alpha=0.5)
plt.plot(time, [70] * len(time), '--',label='Utility buy price', linewidth=4, alpha=0.5)
plt.ylabel('Price [$/kWh]')
plt.ylim([60, 120])
plt.legend(loc=2)
ax = plt.gca()
ax2 = ax.twinx()
ax2.plot(time, yr, label='Ratio', linewidth=4, color='black', alpha=0.4)
ax2.set_yticks(np.linspace(ax2.get_yticks()[0],ax2.get_yticks()[-1],len(ax.get_yticks())))
ax2.grid(False)
plt.ylabel('Ratio')
plt.title('Market prices')
plt.xlabel('Time of the day')
plt.legend(loc=0)
plt.savefig("filname1.png")

# Plot market prices
# time = pandas.date_range('2017-09-21 00:00:00', periods=len(market_15min_info), freq='15T')
yc = [block['args']['_cons'] / 1000 for block in mar]
yg = [block['args']['_gen'] / 1000 for block in mar]

print(yc)
print(yg)
# Create plot
plt.figure(figsize=(11, 5), dpi=200)
plt.plot(time, yc, label='Total consumption')
plt.plot(time, yg, label='Total production')
plt.xlabel('Time of the day')
plt.ylabel('Energy [kWh]')
plt.legend(loc=0)
plt.savefig("filname.png")
rows = zip(time, yc, yg)
f1 = ['Ethereum']
f2 = ['Date', 'load', 'gene']
with open('block.csv', "w") as f:
    writer = csv.writer(f)
    writer.writerow(f1)
    writer.writerow(f2)
    for row in rows:
        writer.writerow(row)