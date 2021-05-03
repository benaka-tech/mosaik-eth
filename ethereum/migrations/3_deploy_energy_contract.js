var MarketLib = artifacts.require("./Market.sol");

module.exports = function(deployer) {
  deployer.deploy(MarketLib);
};
