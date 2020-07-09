# Core
import ConfigParser
import logging
import subprocess, time

# 3rd Party
from argh import dispatch_command, arg

# Local



logging.basicConfig(level=logging.DEBUG)


def minutes(m):
    return 60 * m


def gridtrader(command, account):
    shell_cmd = 'python gridtrader.py --{0} {1}'.format(command, account)
    return shell_cmd


class Batch(object):

    def __init__(self, config, accountgroup):
        self.config = config
        self.accountgroup = accountgroup

    @property
    def accounts(self):
        try:
            return self.config.get('accountgroups', self.accountgroup).split()
        except ConfigParser.NoOptionError:
            return [self.accountgroup]

    def _init(self):
        for account in self.accounts:
            logging.debug("*** %s", account)
            shell_cmd = gridtrader('init', account)
            subprocess.call(shell_cmd.split())

    def verbose_delay(self, _type):
        delay = self.config.getfloat('delay', _type)
        print "Next loop begins after {} delay of {} minutes".format(
            _type, delay)
        time.sleep(minutes(delay))


    def _monitor(self):

        for account in self.accounts:
            shell_cmd = gridtrader('monitor', account)
            subprocess.call(shell_cmd.split())
            self.verbose_delay('account')

    def _cancel_all(self):
        for account in self.accounts:
            shell_cmd = gridtrader('cancel-all', account)
            subprocess.call(shell_cmd.split())

    def _monitor_forever(self):

        while True:
            self._monitor()
            self.verbose_delay('group')

@arg('--cancel-all', help="Cancel all open orders, even if this program did not open them")
@arg('--init', help="Create new trade grids, issue trades and persist grids.")
@arg('--monitor', help="See if any trades in grid have closed and adjust accordingly")
@arg('--monitor-loop', help="Run monitor in a loop")
@arg('accountgroup', help="Searches [accountgroups] in config.ini for this value. Otherwise considers it a single .ini in src/config")
def main(
        accountgroup,
        init=False, monitor=False, monitor_loop=False, delay=1,
        cancel_all=False
):

    config = ConfigParser.RawConfigParser()
    config.read('batch/config.ini')

    batch = Batch(config, accountgroup)

    if init:
        batch._init()

    if monitor:
        batch._monitor()

    if monitor_loop:
        batch._monitor_forever()

    if cancel_all:
        batch._cancel_all()


if __name__ == '__main__':
    dispatch_command(main)
