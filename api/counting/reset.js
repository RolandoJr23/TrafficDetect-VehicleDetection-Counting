const { proxyRequest } = require("../_proxy");

module.exports = async function handler(req, res) {
  return proxyRequest(req, res, "/api/counting/reset");
};
