# Mosaik demo running an Ethereum node

Goals:
- Explore Mosaik's API(compare to the FMI standard)
- Run an Ethereum network and interface with it in Python
- Test research ideas around decentralized grid controls and energy market

## Ethereum

Dependencies: testrpc, truffle
- $ testrpc
- $ rm build/contracts/Market.json & truffle compile & truffle migrate --reset

Note: after deploying your contract on multiple testrpc networks you might want
to remove "contracts/Market.json". The "network" field seems to accumulate network ids.
The file will be rebuild/reset next time you compile and migrate.

## Mosaik

Dependencies: running python 3 and requirements.txt
- $ python demo.py
- open your browser at 0.0.0.0:8000
- $ c (press c and enter to continue the simulation)
- A few jupyter notebooks allow you to explore transactions on the blockchain
