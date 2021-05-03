import mosaik_api
from web3 import Web3, HTTPProvider
import json
from time import sleep
import simulator

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
        self.simulator = simulator.Simulator()
        self.step_size = None
        self.eids = []
        self.sid = None

        # blockchain parameters
        self.web3 = None
        self.accounts = None
        self.contract = None
        self.contract_addr = None

    def init(self, sid, step_size):
        # Initialize some meta information about the model
        self.sid = sid
        self.step_size = step_size
        return self.meta

    def create(self, num, model):
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
        self.contract = self.web3.eth.contract(address=self.contract_addr,abi=energy_abi)

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
        return entities

    def step(self, time, inputs=None):
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
        data={}
        return data
        # consumption_filter = self.contract.on('addedConsumption',
        #                                  filter_params={'filter': {'_target': accounts[account_index]},
        #                                                 'fromBlock': 'earliest'})
        # data = consumption_filter.get(only_changes=False)
        # data = [block for block in data if block['args']['_target'] == accounts[account_index]]
        # xc = pandas.date_range('2017-09-21 00:00:00', periods=len(data), freq='15T')
        # yc = [block['args']['_value'] / 1000 for block in data]
        # generation_filter = self.contract.on('addedGeneration',
        #                                 filter_params={'filter': {'_target': accounts[account_index]},
        #                                                'fromBlock': 'earliest'})
        # data = generation_filter.get(only_changes=False)
        # data = [block for block in data if block['args']['_target'] == accounts[account_index]]
        # xg = pandas.date_range('2017-09-21 00:00:00', periods=len(data), freq='15T')
        # yg = [block['args']['_value'] / 1000 for block in data]

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
