import mosaik_api
from mosaik_api import Simulator
from example_sim import simulator
from networkx.drawing.tests.test_pylab import plt
from web3 import Web3, HTTPProvider
import csv
import json
from time import sleep
import pandas as pandas

__version__ = '0.0.0'
meta = {
    'models': {
        'Ethereum': {
            'public': True,
            'any_inputs': True,
            'params': [],
            'attrs': ['load', 'gene'],
        },
    },
}


class Ethereum(mosaik_api.Simulator):
    def __init__(self):
        super().__init__(meta)
        # self.simulator = Simulator
        self.step_size = None
        self.eids = []
        self.sid = None

        # blockchain parameters
        self.web3 = None
        self.accounts = None
        self.contract = None
        self.contract_addr = None
        # self.cache = None

    def init(self, sid, step_size):
        # Initialize some meta information about the model
        self.sid = sid
        self.step_size = step_size
        return self.meta

    def create(self, num, model):
        print("in Create()")
        if model != 'Ethereum':
            raise ValueError('Invalid model "%s" % model')

        # Initialize the connection to the blockchain network
        self.web3 = Web3(HTTPProvider('http://localhost:8545'))

        # Get contract signature
        with open('ethereum/build/contracts/Market.json') as energy_file:
            energy_json = json.load(energy_file)
        energy_abi = energy_json['abi']
        network_id = list(energy_json['networks'].keys())[-1]
        self.contract_addr = energy_json['networks'][network_id]['address']

        # List accounts and set default account
        self.accounts = self.web3.eth.accounts
        self.web3.eth.defaultAccount = self.accounts[0]

        # Create reference to the contract
        self.contract = self.web3.eth.contract(address=self.contract_addr, abi=energy_abi)

        # Create instances of the model
        start_idx = len(self.eids)
        entities = []
        for i in range(num):
            # Transact to the blockchain to add a participant
            temp = {'from': self.accounts[i], 'to': self.contract_addr, 'gas': 900000}
            trans_hash = self.contract.functions.add_participant().transact(temp)
            self._wait_until_trans_receipt(trans_hash)

            # Normal Mosaik protocol
            eid = '%s_%s' % (model, i + start_idx)
            entities.append({
                'eid': eid,
                'type': model,
                'rel': [],
            })
            self.eids.append(eid)
        print(entities)
        return entities

    def step(self, time, inputs=None):
        print("in Step()")
        # For all the participants on the blockchain
        for eid, attrs in inputs.items():
            # Pick account
            account = self.accounts[int(eid.split('_')[1])]
            netload = 0

            # For all the attributes to post to the blockchain
            for attr, attr_data in attrs.items():

                # For all the sources of those attributes
                for source, value in attr_data.items():
                    # Update the net load with all sources
                    netload += value

            # Post net load per account to the market
            temp = {'from': account, 'to': self.contract_addr, 'gas': 1000000}
            trans_hash = self.contract.functions.post_energy_balance(int(netload)).transact(temp)
            self._wait_until_trans_receipt(trans_hash)

        # Attempt to clear the market once all the participant posted their netload
        temp = {'from': self.accounts[0], 'to': self.contract_addr, 'gas': 900000}
        trans_hash = self.contract.functions.clear_market().transact(temp)
        self._wait_until_trans_receipt(trans_hash)

        # # Bill all participants
        # temp = {'to': contract_address, 'gas': 1000000}
        # self.contract.transact(temp).bill_all_participants()

        return time + self.step_size

    def get_data(self, outputs=None):
        print("in get_data()")
        self.web3 = Web3(HTTPProvider('http://localhost:8545'))

        # Get contract signature
        with open('ethereum/build/contracts/Market.json') as energy_file:
            energy_json = json.load(energy_file)
        contract_abi = energy_json['abi']
        network_id = list(energy_json['networks'].keys())[-1]
        self.contract_address = energy_json['networks'][network_id]['address']

        # List accounts and set default account
        accounts = self.web3.eth.accounts
        self.web3.eth.defaultAccount = accounts[0]
        contract = self.web3.eth.contract(abi=contract_abi, address=self.contract_address)
        energy_posted_event = contract.events.energy_posted_event().createFilter(fromBlock='earliest')
        market_cleared_event = contract.events.market_cleared_event().createFilter(fromBlock='earliest')
        bill_sent_event = contract.events.bill_sent_event().createFilter(fromBlock='earliest')
        participant_at_clearing_request = contract.events.participant_at_clearing_request().createFilter(
            fromBlock='earliest')
        print(accounts)
        # print(energy_posted_event.get_all_entries())
        print(market_cleared_event.get_all_entries())
        # print('Number of accounts ' + str(len(accounts)))
        # print('Number of participants ' + str(contract.functions.number_of_participant().call()))
        mar = market_cleared_event.get_all_entries()
        # time = pandas.date_range(start='2017-09-21 00:00:00', periods=len(market_cleared_event.get_all_entries()),freq='15T')
        yc = [block['args']['_cons'] / 1000 for block in mar]
        yg = [block['args']['_gen'] / 1000 for block in mar]

        print(yc)
        print(yg)
        # Create plot
        data = {}

        for eid, attrs in outputs.items():
            if eid not in self.eids:
                raise ValueError('Unknown entity ID "%s"' % eid)
            data[eid] = {'load': yc[-1], 'gene': yg[-1]}

        print(data)
        return data



    def _init_network_connection(self):
        # Connect to the network
        self.web3 = Web3(HTTPProvider('http://localhost:8545'))

        # Get contract signature
        with open('ethereum/build/contracts/Market.json') as energy_file:
            energy_json = json.load(energy_file)
        energy_abi = energy_json['abi']
        network_id = list(energy_json['networks'].keys())[-1]
        self.contract_addr = energy_json['networks'][network_id]['address']

        # List accounts and set default account
        self.accounts = self.web3.eth.accounts
        self.web3.eth.defaultAccount = self.accounts[0]

        # Create reference to the contract
        self.contract = self.web3.eth.contract(energy_abi, self.contract_addr)

    def _wait_until_trans_receipt(self, trans_hash):
        status = None
        sleep(0.2)
        while status is None:
            status = self.web3.eth.getTransactionReceipt(trans_hash)
            sleep(0.1)


def main():
    return mosaik_api.start_simulation(Ethereum(), 'mosaik-ethereum simulator')


if __name__ == '__main__':
    main()
