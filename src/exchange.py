# core
import logging
import pprint

# 3rd party
from dotmap import DotMap
from forwardable import forwardable
import poloniex

# local
import exception
from mynumbers import F, CF


logging.basicConfig(level=logging.DEBUG)


class APIData(DotMap):
    pass

class PoloniexAPIData(APIData):

    @property
    def lowestAsk(self):
        return F(self['lowestAsk'])

    @property
    def highestBid(self):
        return F(self['highestBid'])

    @property
    def midPoint(self):
        return F(self.highestBid + self.lowestAsk) / 2.0

    # Created to catch failed order placements.
    # When a sell order fails instead of being able
    @property
    def orderNumber(self):
        if 'error' in self:
            exception.identify_and_raise(self['error'])

        return self['orderNumber']

def poloniex_api_data(d, **kwargs):
    if isinstance(d, dict):
        return PoloniexAPIData(d, **kwargs)
    if isinstance(d, list):
        return d

wrapper = dict(polo=poloniex_api_data)

def exchangeFactory(exchange_label, config, **kwargs):

    if exchange_label == 'polo':
        kwargs['extend'] = True
        kwargs['retval_wrapper'] = wrapper[exchange_label]

        kwargs['Key'] = config.get('api', 'key')
        kwargs['Secret'] = config.get('api', 'secret')

        kwargs['loglevel'] = logging.DEBUG

        return PoloniexFacade(**kwargs)

@forwardable()
class PoloniexFacade(poloniex.Poloniex):
    def_delegators('api', 'returnCompleteBalances, returnTicker')

    def __init__(self, **kwargs):
        self.api = poloniex.Poloniex(**kwargs)

    def currency2pair(self, base, quote, uppercase=True):
        v = "{0}_{1}".format(base, quote)
        if uppercase:
            v = v.upper()
        return v

    def cancelAllOpen(self):
        orderdict = self.api.returnOpenOrders()
        print "Open Orders {0}".format(orderdict)
        for pair, orderlist in orderdict.iteritems():
            if orderlist:
                self.cancelOrders([o.orderNumber for o in orderlist])

    def cancelOrders(self, order_numbers):
        logging.debug("cancelOrders {0}".format(order_numbers))
        for order_number in order_numbers:
            order_number = int(order_number)
            logging.debug("cancelling {0}".format(order_number))
            self.api.cancelOrder(int(order_number))

    def tickerFor(self, market):
        all_markets_ticker = self.returnTicker()
        return PoloniexAPIData(all_markets_ticker[market])

    def fillAmount(self, trade_id):
        r = self.api.returnOrderTrades(trade_id)

        if isinstance(r, dict):
            if r.get('error'):
                return 0
            else:
                raise Exception("Received dict but not error in it.")

        amount_filled = F(0)

        logging.debug("R={0}".format(pprint.pformat(r)))

        for v in r:
            logging.debug("V={0}".format(v))
            amount_filled += float(v['amount'])

        logging.debug("amount filled = {0}".format(amount_filled))

        return amount_filled

    def fills(self, trade_id):
        r = self.api.returnOrderTrades(trade_id)

        if isinstance(r, dict):
            if r.get('error'):
                return []
            else:
                raise Exception("Received dict but not error in it.")

        logging.debug("returnOrderTrades={0}".format(pprint.pformat(r)))

        return r

    def buy(self, market, rate, amount):
        r = self.api.buy(market, rate, amount)
        if r.get('error'):
            exception.identify_and_raise(r.get('error'))
        return r

    def sell(self, market, rate, amount):
        r = self.api.sell(market, rate, amount)
        if r.get('error'):
            exception.identify_and_raise(r.get('error'))
        return r
