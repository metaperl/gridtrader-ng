# Grid Trader
Grid trading algorithm.

## Installation

1. Install python-poloniex from
https://github.com/metaperl/python-poloniex

Then type `python setup.py install` to install it.

2. Install the 3rd party Python libraries needed:
`pip install -r requirements.txt`


### Poloniex API Key

Login to Poloniex and [create an API key](https://poloniex.com/apiKeys)
with trading privileges enabled.

## Configuration

### Make a logfile directory

    mkdir -p src/log/$accountName


### Setup a config file for each account

Edit `src/config/$accountName.ini` per the docs in the .ini file.

### (optional) Edit batch/config.ini per the inline docs


## Usage

    shell> cd src
    shell> python gridtrader.py --help
    shell> python gridtrader.py --balances $accountName # List balances of account
    shell> python gridtrader.py --init $accountName    # Run once to set things up.
    shell> python gridtrader.py --monitor $accountName # Run every X minutes (via cron?) over and over.
    shell> python gridtrader.py --cancel-all $accountName # Cancels all open orders

### Batch execution (optional)

See src/batch/run.py

    shell> cd src
    shell> python batch/run.py --init $accountName
    shell> python batch/run.py --monitor-loop $accountName  # looping calls to python gridtrader.py --monitor $accountName 

# WARNINGS

If you change the program code you *MUST* run --init again. You cannot
run `--monitor` right after a change to the source code. You must --init
after that in ALL cases, because of how the serialization of program objects
to disk between runs works.
