#!/usr/bin/env python


# core
import ConfigParser
from datetime import datetime
import logging
import pprint
import sys
import time
import traceback

# 3rd party
from argh import dispatch_command, arg
from tabulate import tabulate

# local
import exception
import exchange as _exchange
from mynumbers import F, CF
from persist import Persist



# If any grid position's limit order has this much or less remaining,
# consider it totally filled
epsilon = 1e-8

def human_readable(attrs, delta):
    return ['%d %s' % (getattr(delta, attr), getattr(delta, attr) > 1 and attr or attr[:-1]) for attr in attrs if getattr(delta, attr)]

def display_session_info(session_args, e, start_time=None):
    logging.debug("dsi args: {}, {}, {}".format(session_args, e, start_time))
    now = datetime.now()
    session_date = now.strftime('%a, %d %b %Y %H:%M:%S +0000')
    forward_slash = "/" if start_time else ""
    if start_time:
        from dateutil.relativedelta import relativedelta
        elapsed_time = relativedelta(start_time, now)
        attrs = ['hours', 'minutes', 'seconds']
        logging.debug("This run took {}", human_readable(attrs, elapsed_time))

    balances = get_balances(e)
    balstr = ""
    for coin in sorted(balances.keys()):
        amounts = balances[coin]
        balstr += "{}={},".format(coin, amounts['TOTAL'])

    logging.debug("<{}session args={} balances={} date={} >".format(
        forward_slash, session_args, balstr, session_date)
    )

    return now



def config_file_name(exch):
    return "config/{0}.ini".format(exch)


def persistence_file_name(exch):
    return "persistence/{0}.storage".format(exch)


def pair2currency(pair):
    btc, currency = pair.split('-')
    return currency


def percent2ratio(i):
    return i / 100.0


def delta_by_percent(v, p, p_is_ratio=False):
    if not p_is_ratio:
        p = percent2ratio(p)

    retval = v + v * p
    logging.debug("%.8f delta %f percent = %.8f", v, p, retval)

    return retval


def percent_difference(a, b):
    diff = a - b
    percent_diff = (diff / a) * 100.0
    logging.debug("percent difference between %.8f and %.8f = %f",
                  a, b, percent_diff)
    return percent_diff


def float_equal(a, b, epsilon=1e-8):
    return abs(a-b) < epsilon


def i_range(a):
    l = len(a)
    if not l:
        return "zero-element list"
    else:
        return "from {0} to {1}".format(0, len(a)-1)


class TallyGoal(object):

    def __init__(self, target=None):
        self.target = target
        self.elems = list()

    def add(self, elem):
        self.elems.append(elem)

    @property
    def meets_target(self):
        logging.debug("Does sum(%s) meet the target of %.8f ?",
                      self.elems, self.target)
        return float_equal(self.target, sum(self.elems))

class Grid(object):
    def __init__(
            self, quote, pair, current_market_price, config):

        logging.debug("Initializing %s %s with current market price = %.8f",
                      pair, self.__class__.__name__, current_market_price)

        self.initial_core_position = F(config.getfloat(
            'initialcorepositions', quote))
        self.trade_ids = list()
        self.trade_ids_filled = list()

        self.quote = quote
        self.pair = pair
        self.current_market_price = F(current_market_price)
        self.config = config
        self.make_grid()

    @property
    def majorLevel(self):
        return CF(self.config, self.config_section, 'majorLevel')

    @property
    def numberOfOrders(self):
        return self.config.getint(self.config_section, 'numberOfOrders')

    @property
    def increments(self):
        return percent2ratio(
            F(self.config.getfloat(self.config_section, 'increments')))

    @property
    def config_section(self):
        return self.__class__.__name__.lower()

    @property
    def size(self):

        return (
            percent2ratio(CF(self.config, self.config_section, 'size'))
            * self.initial_core_position
            / self.numberOfOrders
        )

    def build_order(self, rate):
        order = dict(market=self.pair, rate=rate, amount=self.size)
        return order

    def print_order(self, order):
        logging.debug("<order from=%s>%s</order>", type(self).__name__, pprint.pformat(order))
        return order

    def trade_activity(self, exchange):
        for i in xrange(len(self.trade_ids)-1, -1, -1):
            uuid = self.trade_ids[i]
            remaining = self.size - exchange.fillAmount(uuid)
            # logging.debug("Amount remaining = %f - %f = %f",
            #               self.size, exchange.fillAmount(uuid), remaining)
            if iszero(remaining):
                # logging.debug("** Trade activity will be returned.")
                # logging.debug("Length of trade_ids=%d", len(self.trade_ids))

                return i

        return None

    def _fill_activity(self, exchange):
        r = [(i, exchange.fills(trade_id)) for i, trade_id in enumerate(self.trade_ids)]
        return r

    def fill_activity(self, exchange):
        retval = self._fill_activity(exchange)
        logging.debug("Fill activity = {}".format(retval))
        return retval

    def purge_closed_trades(self, deepest_i):
        new_grid = list()
        new_trade_ids = list()
        for i in xrange(0, len(self.trade_ids)):
            if i > deepest_i:
                new_grid.append(self.grid[i])
                new_trade_ids.append(self.trade_ids[i])

        self.grid = new_grid
        self.trade_ids = new_trade_ids

    def __str__(self):

        config_s = str()
        for grid_section in 'sellgrid buygrid'.split():
            config_s += "<{0}>".format(grid_section)
            for option in self.config.options(grid_section):
                config_s += "{0}={1}".format(
                    option, self.config.get(grid_section, option))
            config_s += "</{0}>".format(grid_section)


        table = [
            ["Core Position", self.initial_core_position],
            ["Pair", self.pair],
            ["Current Market Price", self.current_market_price],
            ["Grid Config", config_s],
            ["Size", self.size],
            ["Starting Price", self.starting_price],
            ["Grid", self.grid],
            ["Grid Trade Ids", self.trade_ids],
            ["Grid Trade Ids Filled", self.trade_ids_filled],
        ]

        return "{0}\n{1}".format(type(self).__name__, tabulate(table, floatfmt=".8f"))

class SellGrid(Grid):

    def __init__(self, quote, pair, current_market_price, config):
        super(type(self), self).__init__(
            quote, pair, current_market_price, config)

    @property
    def starting_price(self):
        return delta_by_percent(self.current_market_price, self.majorLevel)


    def make_grid(self):
        retval = list()
        last_price = self.starting_price
        for i in range(0, self.numberOfOrders):
            retval.append(last_price)
            next_price = last_price + last_price * self.increments
            # print next_price
            last_price = next_price

        self.grid = retval

    def place_orders(self, exchange):
        logging.debug("<PLACE_ORDERS>")

        for rate in self.grid:
            order = self.build_order(rate)
            self.print_order(order)
            r = exchange.sell(**order)
            self.trade_ids.append(r.orderNumber)

        logging.debug("</PLACE_ORDERS>")

        return self

class BuyGrid(Grid):

    def __init__(self, quote, pair, current_market_price, config):
        super(type(self), self).__init__(
            quote, pair, current_market_price, config)

    @property
    def starting_price(self):
        # logging.debug("majorLevel={0}({1}. current mkt price={2}{3}".format(
        #     m, type(m), self.current_market_price, type(self.current_market_price)
        # ))
        return delta_by_percent(self.current_market_price, -1*self.majorLevel)

    def make_grid(self):
        retval = list()
        last_price = self.starting_price
        for i in range(0, self.numberOfOrders):
            retval.append(last_price)
            next_price = last_price - last_price * self.increments
            # print next_price
            last_price = next_price

        self.grid = retval

    def place_orders(self, exchange):
        print "<PLACE_ORDERS>"

        for rate in self.grid:
            order = self.build_order(rate)
            self.print_order(order)
            r = exchange.buy(**order)
            self.trade_ids.append(r.orderNumber)

        print "</PLACE_ORDERS>"

        return self


class ReciprocalTrade(object):

    direction_toggle = dict(buy='sell', sell='buy')

    def __init__(self, reciprocant_trade_id, config, market, exchange, rate_of_closed_trade, size_of_closed_trade, grids):
        """A reciprocal trade is created as a trade (partially) fills. It is
        created in the opposite direction of the trade that it reciprocates.
        E.g., if a buy (of any sort - grid buy, compliment buy, etc) order
        (partially) fills, then a ReciprocalSell trade that is the same size
        of the (partially) filled trade and with the major level of the
        sell grid.

        - reciprocant_trade_id: the trade_id that this reciprocal trade reciprocates.
        - market: something like BTC_STRAT
        - exchange: the exchange instance
        - rate_of_closed_trade
        - grids: the grids that initiated the chain of reciprocation.

        Initialization of the reciprocal takes place build_new_grids().
        """

        self.reciprocant_trade_id = reciprocant_trade_id
        self.config = config
        self.market = market
        self.exchange = exchange
        self.rate_of_closed_trade = rate_of_closed_trade
        self.size_of_closed_trade = size_of_closed_trade
        self.grid = grids
        self.trade_id = None
        logging.debug("{} of {} initialized with grids {}".format(
            type(self).__name__, reciprocant_trade_id, grids))

    @property
    def fills(self):
        return self.exchange.fills(self.trade_id)

    @property
    def majorLevel(self):
        return CF(self.config, type(self).__name__, 'majorLevel')

    def __str__(self):
        return """{} reciprocant={} trade_id={}
        market {}
        rate of closed trade {}
        size of closed trade {}
        """.format(
            self.__class__.__name__, self.reciprocant_trade_id, self.trade_id,
            self.market, self.rate_of_closed_trade, self.size_of_closed_trade
            )

    __repr__ = __str__

class ReciprocalSell(ReciprocalTrade):

    """A ReciprocalSell is made when a buy order fills."""

    @property
    def rate(self):
        """Take the rate of the buy trade and create a retrace sell trade
        mirror_delta percent greater than that rate."""

        delta = delta_by_percent(self.rate_of_closed_trade, self.majorLevel)
        return delta

    def place_order(self):
        r = self.exchange.sell(self.market,
                               rate=self.rate,
                               amount=self.size_of_closed_trade
                               )
        self.trade_id = r.orderNumber
        return self


class ReciprocalBuy(ReciprocalTrade):

    @property
    def rate(self):
        """Take the rate of the closed sell trade and create a buy trade
        delta percent less than that rate."""

        delta = delta_by_percent(self.rate_of_closed_trade, -1.0 * self.majorLevel)
        return delta

    def place_order(self):
        r = self.exchange.buy(self.market,
                              rate=self.rate,
                              amount=self.size_of_closed_trade
                              )
        self.trade_id = r.orderNumber
        return self

ReciprocalTrade.constructor_for = dict(buy=ReciprocalBuy, sell=ReciprocalSell)

class GridTrader(object):

    def __init__(self, exchange, config, account, base='btc'):
        self.exchange, self.config, self.base = exchange, config, base
        self.account = account
        self.market = dict()
        self.reciprocal = dict()
        self.reciprocal_dust = list() # trades too small to place

        # self.grids is set in .build_new_grids() below

    def __str__(self):
        s = str()

        for market in self.grids:
            s += '<{}:{} highestBid={} lowestAsk={}>\n'.format(
                self.account, market,
                self.market[market]['highestBid'],
                self.market[market]['lowestAsk']
            )

            s += "\nReciprocalDust:{}\n".format(self.reciprocal_dust)

            for buysell in self.grids[market]:
                s += "  <{0}>".format(buysell)
                s += "\nReciprocal:{}\n".format(self.reciprocal[market][buysell])
                s += str(self.grids[market][buysell])
                s += "  </{0}>".format(buysell)

            s += '</{0}>\n'.format(market)

        return "{0}\n{1}".format(type(self).__name__, s)

    def sanity_check(self, market):
        logging.debug("Sanity checking %s", market)
        new_bid = F(self.exchange.tickerFor(market).highestBid)
        old_bid = F(self.market[market]['highestBid'])

        d = percent_difference(old_bid, new_bid)

        if d >= 0:
            parameter = 'allowableDrop'
        else:
            parameter = 'allowableGain'

        allowable = self.config.getfloat('sanitycheck', parameter)

        logging.debug("Market delta from {:.8f} to {:.8f} between invocations...", old_bid, new_bid)

        logging.debug("tests %s Allowable percentage of %.8f", parameter, allowable)
        if abs(d) >= allowable:
            error_message = "{} Market delta from {:.8f} to {:.8f} between invocations violates {} of {} percent".format(
                market, old_bid, new_bid, parameter, allowable)
            raise exception.MarketCrash(error_message)

        logging.debug("PASSES")

    def notify_admin(self, error_msg):

        logging.debug("Cancelling all open orders before notifying admin about error %s", error_msg)

        self.exchange.cancelAllOpen()

        logging.debug("Cancellation done.")

        import mymailer
        mymailer.send_email(self, error_msg)


    @property
    def pairs(self):

        all_tickers = self.exchange.returnTicker()

        pairs = dict()

        for quote in self.config.get('pairs', 'pairs').split():
            pair = self.exchange.currency2pair(self.base, quote)
            pairs[pair] = {
                'quote':  quote,
                'ticker': all_tickers[pair]
            }

        return pairs

    def build_new_grids(self):

        pairs = self.pairs
        logging.debug("Querying pairs".format(pprint.pformat(pairs)))

        grid = dict()
        logging.debug("Creating buy and sell grids")
        for pair, pair_info in pairs.iteritems():

            self.reciprocal[pair] = dict()

            logging.debug("pair = {} info={} typeinfo={}".format(
                pair, pprint.pformat(pair_info), type(pair_info)))
            grid[pair] = dict()
            grid[pair]['sell'] = SellGrid(
                quote=pair_info['quote'],
                pair=pair,
                current_market_price=F(pair_info['ticker'].lowestAsk),
                config=self.config
            )
            grid[pair]['buy'] = BuyGrid(
                quote=pair_info['quote'],
                pair=pair,
                current_market_price=F(pair_info['ticker'].highestBid),
                config=self.config
            )
            for direction in 'sell buy'.split():
                self.reciprocal[pair][direction] = dict()
                logging.debug(
                   "{} reciprocal = {} grid = {}".format(
                       direction, self.reciprocal[pair][direction],
                       grid[pair][direction]))


        self.grids = grid

    def issue_trades(self):
        for market in self.grids:
            self.market[market] = {
                'lowestAsk'  : F(self.exchange.tickerFor(market).lowestAsk),
                'highestBid' : F(self.exchange.tickerFor(market).highestBid),
            }
            for buysell in self.grids[market]:
                g = self.grids[market][buysell]

                if buysell == 'buy':
                    g.place_orders(self.exchange)
                elif buysell == 'sell':
                    try:
                        g.place_orders(self.exchange)
                    except (exception.NotEnoughCoin, exception.DustTrade):
                        logging.debug("Sell grid not fully created because there was not enough coin")
                        # self.grids[market][buysell].trade_ids = list()
                else:
                    raise exception.InvalidDictionaryKey("Key other than buy or sell")

    def monitor_reciprocals(self, market, buy_reciprocal_market, sell_reciprocal_market):
        logging.debug("---------- monitor_reciprocals")
        for direction in 'buy sell'.split():
            logging.debug("... studying %s reciprocal market", direction)
            for reciprocant_trade_id, reciprocal_trade in self.reciprocal[market][direction].items():
                fill_tally = TallyGoal(reciprocal_trade.size_of_closed_trade)
                for fill in reciprocal_trade.fills:
                    ftid = fill['tradeID']
                    logging.debug("Looking for reciprocal trades of %d", ftid)
                    opposite_direction = ReciprocalTrade.direction_toggle[direction]
                    opposite_market = self.reciprocal[market][opposite_direction]
                    if ftid not in opposite_market:
                        r = ReciprocalTrade.constructor_for[opposite_direction](
                                ftid, self.config,
                                market, self.exchange,
                                rate_of_closed_trade=float(fill['rate']),
                                size_of_closed_trade=float(fill['amount']),
                                grids=self.grids[market]
                            )
                        self.place_reciprocal_order(r, opposite_market)
                    fill_tally.add(float(fill['amount']))
                if fill_tally.meets_target:
                    del self.reciprocal[market][direction][reciprocant_trade_id]

    def place_reciprocal_order(self, reciprocal_trade, reciprocal_market):
        """Place RECIPROCAL_TRADE, adding to RECIPROCAL_MARKET dictionary, indexed by TradeID of FILL
        that had not previously been filled.
        """
        try:
            reciprocal_trade.place_order()
            reciprocal_market[reciprocal_trade.reciprocant_trade_id] = reciprocal_trade
        except exception.DustTrade:
            self.reciprocal_dust.append(reciprocal_trade)

    @staticmethod
    def other_direction(buyorsell):
        if buyorsell == 'buy':
            return 'sell'
        if buyorsell == 'sell':
            return 'buy'
        raise Exception("%s was passed to a method only accept buy or sell", buyorsell)

    def _poll(self, grid, grids, market, reciprocal_market, reciprocal_constructor):
        for i, fills in grid.fill_activity(self.exchange):
            if i in grid.trade_ids_filled:
                logging.debug("Index %d has been completely filled", i)
                continue
            if fills:
                logging.debug("Index %d in grid has some fills towards its goal of %f", i, grid.size)
                fill_tally = TallyGoal(grid.size)
                for fill in fills:
                    if fill['tradeID'] not in reciprocal_market:
                        logging.debug("No reciprocal trade placed for %d", fill['tradeID'])
                        r = reciprocal_constructor(
                            fill['tradeID'],
                            self.config,
                            market, self.exchange,
                            rate_of_closed_trade=F(fill['rate']),
                            size_of_closed_trade=F(fill['amount']),
                            grids=grids
                        )
                        logging.debug("Placing this order %s", r)
                        self.place_reciprocal_order(r, reciprocal_market)
                    fill_tally.add(F(fill['amount']))
                if fill_tally.meets_target:
                    grid.trade_ids_filled.append(i)
            else:
                logging.debug("Index %d in grid has no fills towards its goal of %f", i, grid.size)

    def poll(self):

        logging.debug("------------------------------ poll method")

        for market in self.grids:
            logging.debug("Analyze %s", market)
            self.sanity_check(market)

            grids = self.grids[market]

            for direction in 'buy sell'.split():
                grid = grids[direction]
                logging.debug("Checking %s %s grid for fill activity", market, direction)
                other_direction = self.other_direction(direction)
                reciprocal_market = self.reciprocal[market][other_direction]
                self._poll(
                        grid, grids, market, reciprocal_market, ReciprocalTrade.constructor_for[other_direction])

            self.monitor_reciprocals(market, self.reciprocal[market]['buy'], self.reciprocal[market]['sell'])



def delta(percent, v):
    return v + percent2ratio(percent) * v


def pdict(d, skip_false=True):
    parms = list()
    for k in sorted(d.keys()):
        if not d[k] and skip_false:
            continue
        parms.append("{0}={1}".format(k, d[k]))

    return ",".join(parms)

# http://stackoverflow.com/questions/5595425/what-is-the-best-way-to-compare-floats-for-almost-equality-in-python
def isclose(a, b, rel_tol=epsilon, abs_tol=0.0):
    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)

def iszero(v):
    # logging.debug("isclose(0, %f)", v)
    # return isclose(0, v)
    return v < epsilon

def get_balances(e):

    b = e.returnCompleteBalances()
    for k, v in b.iteritems():
        #logging.debug("k=%s, v=%s", k, v)
        if iszero(float(b[k]['btcValue'])):
            b.pop(k)
        else:
            b[k]['TOTAL'] = F(b[k]['available']) + F(b[k]['onOrders'])
    return b


def initialize_logging(account_name, args):

    args = pdict(args)

    rootLogger = logging.getLogger()

    logPath = 'log/{0}'.format(account_name)
    fileName = "{0}--{1}".format(
        time.strftime("%Y%m%d-%H %M %S"),
        args
        )

    fileHandler = logging.FileHandler(
        "{0}/{1}.log".format(logPath, fileName))
    #fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler(stream=sys.stdout)
    #consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    return args, fileName


@arg('--cancel-all', help="Cancel all open orders, even if this program did not open them")
@arg('--init', help="Create new trade grids, issue trades and persist grids.")
@arg('--monitor', help="See if any trades in grid have closed and adjust accordingly")
@arg('--status-of', help="(Developer use only) Get the status of a trade by trade id")
@arg('account', help="The account whose API keys we are using (e.g. terrence, joseph, peter, etc.")
@arg('--exchange-name', help="on which exchange (polo, trex, gdax)")
@arg('--balances', help="list coin holdings")
def main(
        account,
        exchange_name='polo',
        cancel_all=False,
        init=False,
        monitor=False,
        balances=False,
        status_of='',
):

    command_line_args = locals()

    args, fileName = initialize_logging(account, command_line_args)

    config_file = config_file_name(account)
    config = ConfigParser.RawConfigParser()
    config.read(config_file)

    # logging.debug("Config contents:")
    # for section_name in config.sections():
    #     logging.debug('Section: %s', section_name)
    #     logging.debug('  Options: %s', config.options(section_name))
    #     for name, value in config.items(section_name):
    #         logging.debug('  %s = %s', name, value)

    persistence_file = persistence_file_name(account)

    exchange = _exchange.exchangeFactory(exchange_name, config)

    now = display_session_info(args, exchange)

    g = GridTrader(exchange, config, account)

    try:
        if cancel_all:
            logging.debug("Cancelling ALL open orders, even if this program did not make them")
            exchange.cancelAllOpen()

        if init:
            exchange = _exchange.exchangeFactory(exchange_name, config)

            logging.debug("Cancelling ALL open orders on exchange %s", exchange)
            exchange.cancelAllOpen()

            logging.debug("Building trade grids")
            g.build_new_grids()

            logging.debug("Issuing trades on created grids.")
            logging.debug("(also storing market rates for sanity checks.)")
            g.issue_trades()

            logging.debug("Storing GridTrader to disk.")
            Persist(persistence_file).store(g)

        if monitor:
            logging.debug("Evaluating trade activity since last invocation")
            persistence = Persist(persistence_file)
            g = persistence.retrieve()
            g.poll()
            persistence.store(g)

        if balances:
            logging.debug("Getting balances")


    except Exception as e:
        error_msg = traceback.format_exc()
        logging.debug('Aborting: %s', error_msg)
        g.notify_admin(error_msg)


    display_session_info(args, exchange, start_time=now)


if __name__ == '__main__':
    dispatch_command(main)
