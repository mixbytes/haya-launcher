#!/usr/bin/env python3

import argparse
import json
import numpy
import os
import random
import re
import subprocess
import sys
import time

CUR_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

UNLOCK_TIMEOUT = 999999999
FAST_UNSTAKE_SYSTEM = CUR_SCRIPT_DIR + '/fast.refund/eosio.system/eosio.system.wasm'

SYSTEM_ACCOUNTS = [
    'eosio.bpay',
    'eosio.msig',
    'eosio.names',
    'eosio.ram',
    'eosio.ramfee',
    'eosio.saving',
    'eosio.stake',
    'eosio.token',
    'eosio.vpay',
    'eosio.rex',
]

PROJECT = 'daobet' # or 'haya'

DEFAULT_PUBLIC_KEY    = 'EOS6MRyAjQq8ud7hVNYcfnVPJqcVpscN5So8BhtHuGYqET5GDW5CV'
DEFAULT_PRIVATE_KEY   = '5KQwrPbwdL6PhXujxW37FSSQZ1JiwsST4cqQzDeyXtP79zkvFD3'
DEFAULT_CLI_BIN       = '/usr/bin/' + PROJECT + '-cli'
DEFAULT_NODE_BIN      = '/usr/bin/' + PROJECT + '-node'
DEFAULT_WALLET_BIN    = '/usr/bin/' + PROJECT + '-wallet'
DEFAULT_CONTRACTS_DIR = CUR_SCRIPT_DIR + '/contracts'
DEFAULT_NODES_DIR     = CUR_SCRIPT_DIR + '/nodes'
DEFAULT_WALLET_DIR    = CUR_SCRIPT_DIR + '/wallet'
DEFAULT_GENESIS_JSON  = CUR_SCRIPT_DIR + '/genesis.json'
DEFAULT_LOGGING_JSON  = CUR_SCRIPT_DIR + '/logging.json'


def json_arg(a):
    return " '" + json.dumps(a) + "' "

def run(cmd):
    print('bios-boot-tutorial.py:', cmd)
    if args.dry_run:
        return
    if subprocess.call(cmd, shell=True):
        print('bios-boot-tutorial.py: exiting because of error')
        sys.exit(1)

def retry(cmd):
    while True:
        print('bios-boot-tutorial.py:', cmd)
        if args.dry_run:
            return
        if subprocess.call(cmd, shell=True):
            sleep(2)
            print('*** Retry')
        else:
            break

def background(cmd):
    print('bios-boot-tutorial.py:', cmd)
    if args.dry_run:
        return
    return subprocess.Popen(cmd, shell=True)

def get_output(cmd):
    print('bios-boot-tutorial.py:', cmd)
    if args.dry_run:
        return
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    return proc.communicate()[0].decode('utf-8')

def get_json_output(cmd):
    return json.loads(get_output(cmd))

def sleep(t):
    print('sleep', t, '...')
    time.sleep(t)
    print('resume')

def start_wallet():
    run('rm -rf ' + os.path.abspath(args.wallet_dir))
    run('mkdir -p ' + os.path.abspath(args.wallet_dir))
    background(args.wallet_bin + ' --unlock-timeout %d --http-server-address 127.0.0.1:6666 --wallet-dir %s' %
        (UNLOCK_TIMEOUT, os.path.abspath(args.wallet_dir)))
    sleep(.4)
    run(args.cli_bin + 'wallet create --to-console')

def import_keys():
    run(args.cli_bin + 'wallet import --private-key ' + args.private_key)
    keys = {}
    for a in ACCOUNTS:
        key = a['pvt']
        if not key in keys:
            if len(keys) >= args.max_user_keys:
                break
            keys[key] = True
            run(args.cli_bin + 'wallet import --private-key ' + key)
    for i in range(FIRST_PRODUCER, FIRST_PRODUCER + NUM_PRODUCERS):
        a = ACCOUNTS[i]
        key = a['pvt']
        if not key in keys:
            keys[key] = True
            run(args.cli_bin + 'wallet import --private-key ' + key)

def start_node(node_index, account):
    dir = args.nodes_dir + ('%02d-' % node_index) + account['name'] + '/'
    run('rm -rf ' + dir)
    run('mkdir -p ' + dir)
    other_opts = ''.join(list(map(lambda i: '    --p2p-peer-address localhost:' + str(9000 + i), range(node_index))))
    if not node_index: other_opts += (
        '    --plugin eosio::history_plugin'
        '    --plugin eosio::history_api_plugin'
    )
    cmd = (
        args.node_bin +
        '    --max-transaction-time=1000'
        '    --delete-all-blocks'
        '    --keosd-provider-timeout=100000000'
        '    --max-irreversible-block-age -1'
        '    --contracts-console'
        '    --genesis-json ' + os.path.abspath(args.genesis) +
        '    --blocks-dir ' + os.path.abspath(dir) + '/blocks'
        '    --config-dir ' + os.path.abspath(dir) +
        '    --data-dir ' + os.path.abspath(dir) +
        '    --chain-state-db-size-mb 1024'
        '    --http-server-address 127.0.0.1:' + str(8000 + node_index) +
        '    --p2p-listen-endpoint 127.0.0.1:' + str(9000 + node_index) +
        '    --max-clients ' + str(MAX_CLIENTS) +
        '    --p2p-max-nodes-per-host ' + str(MAX_CLIENTS) +
        '    --enable-stale-production'
        '    --producer-name ' + account['name'] +
        '    --signature-provider ' + account['pub'] + '=KEOSD:http://127.0.0.1:6666/v1/wallet/sign_digest'
        '    -l '+os.path.abspath(args.logging_json) +
        '    --plugin eosio::http_plugin'
        '    --plugin eosio::chain_api_plugin'
        '    --plugin eosio::producer_api_plugin'
        '    --plugin eosio::net_api_plugin'
        '    --plugin eosio::randpa_plugin ' +
        other_opts)
    err_file = dir + 'stderr'
    if not args.dry_run:
        with open(err_file, mode='w') as f:
            f.write(cmd + '\n\n')
    background(cmd + '    2>>' + dir + 'stderr')


def start_producers(b, e):
    for i in range(b, e):
        start_node(i - b + 1, ACCOUNTS[i])

def create_system_accounts():
    for a in SYSTEM_ACCOUNTS:
        run(args.cli_bin + 'create account eosio ' + a + ' ' + args.public_key)

def int_to_currency(i):
    return '%d.%04d %s' % (i // 10000, i % 10000, args.symbol)

def allocate_funds(b, e):
    dist = numpy.random.pareto(1.161, e - b).tolist() # 1.161 = 80/20 rule
    dist.sort()
    dist.reverse()
    factor = 1_000_000_000 / sum(dist)
    total = 0
    for i in range(b, e):
        funds = round(factor * dist[i - b] * 10000)
        if i >= FIRST_PRODUCER and i < FIRST_PRODUCER + NUM_PRODUCERS:
            funds = max(funds, round(args.min_producer_funds * 10000))
        funds = 15_000_000 * 10000
        total += funds
        ACCOUNTS[i]['funds'] = funds
    return total

def create_staked_accounts(b, e):
    ram_funds = round(args.ram_funds * 10000)
    #configured_min_stake = round(args.min_stake * 10000)
    #max_unstaked = round(args.max_unstaked * 10000)
    for i in range(b, e):
        a = ACCOUNTS[i]
        funds = a['funds']
        print('#' * 80)
        print('# %d/%d %s %s' % (i, e, a['name'], int_to_currency(funds)))
        print('#' * 80)
        if funds < ram_funds:
            print('skipping %s: not enough funds to cover ram' % a['name'])
            continue
        liquid = 10 * 10000
        stake = funds - ram_funds - liquid
        stake_net = 10 * 10000
        stake_cpu = 10 * 10000
        stake_vote = stake - stake_net - stake_cpu
        print('%s: total funds=%s, ram=%s, net=%s, cpu=%s, vote=%s' %
            (a['name'], int_to_currency(a['funds']), int_to_currency(ram_funds), int_to_currency(stake_net),
            int_to_currency(stake_cpu), int_to_currency(stake_vote)))
        assert(funds == ram_funds + stake_net + stake_cpu + stake_vote + liquid)
        retry(args.cli_bin + 'system newaccount --transfer eosio %s %s --stake-net "%s" --stake-cpu "%s" --stake-vote "%s" --buy-ram "%s"   ' %
            (a['name'], a['pub'], int_to_currency(stake_net), int_to_currency(stake_cpu), int_to_currency(stake_vote), int_to_currency(ram_funds)))
        if liquid:
            retry(args.cli_bin + 'transfer eosio %s "%s"' % (a['name'], int_to_currency(liquid)))

def reg_producers(b, e):
    for i in range(b, e):
        a = ACCOUNTS[i]
        retry(args.cli_bin + 'system regproducer ' + a['name'] + ' ' + a['pub'] + ' https://' + a['name'] + '.com' + '/' + a['pub'])

def list_producers():
    run(args.cli_bin + 'system listproducers')

def vote(b, e):
    print('VOTING STEP')
    if e > len(ACCOUNTS):
        e = len(ACCOUNTS)
    for i in range(NUM_PRODUCERS):
        voter = ACCOUNTS[i]['name']
        prod = ACCOUNTS[FIRST_PRODUCER + i]['name']
        print('VOTING FOR ', prod)
        retry(args.cli_bin + 'system voteproducer prods ' + voter + ' ' + prod)

def claim_rewards():
    table = get_json_output(args.cli_bin + 'get table eosio eosio producers -l 100')
    times = []
    for row in table['rows']:
        if row['unpaid_blocks'] and not row['last_claim_time']:
            times.append(get_json_output(args.cli_bin + 'system claimrewards -j ' + row['owner'])['processed']['elapsed'])
    print('Elapsed time for claimrewards:', times)

def proxy_votes(b, e):
    vote(FIRST_PRODUCER, FIRST_PRODUCER + 1)
    proxy = ACCOUNTS[FIRST_PRODUCER]['name']
    retry(args.cli_bin + 'system regproxy ' + proxy)
    sleep(1.0)
    for i in range(b, e):
        voter = ACCOUNTS[i]['name']
        retry(args.cli_bin + 'system voteproducer proxy ' + voter + ' ' + proxy)

def update_auth(account, permission, parent, controller):
    run(args.cli_bin + 'push action eosio updateauth' + json_arg({
        'account': account,
        'permission': permission,
        'parent': parent,
        'auth': {
            'threshold': 1, 'keys': [], 'waits': [],
            'accounts': [{
                'weight': 1,
                'permission': {'actor': controller, 'permission': 'active'}
            }]
        }
    }) + '-p ' + account + '@' + permission)

def resign(account, controller):
    update_auth(account, 'owner', '', controller)
    update_auth(account, 'active', 'owner', controller)
    sleep(1)
    run(args.cli_bin + 'get account ' + account)

def random_transfer(b, e):
    for j in range(20):
        src = ACCOUNTS[random.randint(b, e - 1)]['name']
        dest = src
        while dest == src:
            dest = ACCOUNTS[random.randint(b, e - 1)]['name']
        run(args.cli_bin + 'transfer -f ' + src + ' ' + dest + ' "0.0001 ' + args.symbol + '"' + ' || true')

def msig_propose_replace_system(proposer, proposal_name):
    requested_permissions = []
    for i in range(FIRST_PRODUCER, FIRST_PRODUCER + NUM_PRODUCERS):
        requested_permissions.append({'actor': ACCOUNTS[i]['name'], 'permission': 'active'})
    trx_permissions = [{'actor': 'eosio', 'permission': 'active'}]
    with open(FAST_UNSTAKE_SYSTEM, mode='rb') as f:
        setcode = {'account': 'eosio', 'vmtype': 0, 'vmversion': 0, 'code': f.read().hex()}
    run(args.cli_bin + 'multisig propose ' + proposal_name + json_arg(requested_permissions) +
        json_arg(trx_permissions) + 'eosio setcode' + json_arg(setcode) + ' -p ' + proposer)

def msig_approve_replace_system(proposer, proposal_name):
    for i in range(FIRST_PRODUCER, FIRST_PRODUCER + NUM_PRODUCERS):
        run(args.cli_bin + 'multisig approve ' + proposer + ' ' + proposal_name +
            json_arg({'actor': ACCOUNTS[i]['name'], 'permission': 'active'}) +
            '-p ' + ACCOUNTS[i]['name'])

def msig_exec_replace_system(proposer, proposal_name):
    retry(args.cli_bin + 'multisig exec ' + proposer + ' ' + proposal_name + ' -p ' + proposer)

def msig_replace_system():
    run(args.cli_bin + 'push action eosio buyrambytes' + json_arg(['eosio', ACCOUNTS[0]['name'], 200000]) + '-p eosio')
    sleep(1)
    msig_propose_replace_system(ACCOUNTS[0]['name'], 'fast.unstake')
    sleep(1)
    msig_approve_replace_system(ACCOUNTS[0]['name'], 'fast.unstake')
    msig_exec_replace_system(ACCOUNTS[0]['name'], 'fast.unstake')

#def produce_new_accounts():
#    with open('newusers', 'w') as f:
#        for i in range(120_000, 200_000):
#            x = get_output(args.cli_bin + 'create key --to-console')
#            r = re.match('Private key: *([^ \n]*)\nPublic key: *([^ \n]*)', x, re.DOTALL | re.MULTILINE)
#            name = 'user'
#            for j in range(7, -1, -1):
#                name += chr(ord('a') + ((i >> (j * 4)) & 15))
#            print(i, name)
#            if not args.dry_run:
#                f.write('        {"name":"%s", "pvt":"%s", "pub":"%s"},\n' % (name, r[1], r[2]))


def step_kill_all():
    run('killall daobet-wallet daobet-node || true')
    sleep(1.5)

def step_start_wallet():
    start_wallet()
    import_keys()

def step_start_boot():
    start_node(0, {'name': 'eosio', 'pvt': args.private_key, 'pub': args.public_key})
    sleep(4)

def step_install_system_contracts():
    run(args.cli_bin + 'set contract eosio.token ' + args.contracts_dir + '/eosio.token/')
    run(args.cli_bin + 'set contract eosio.msig ' + args.contracts_dir + '/eosio.msig/')

def step_create_tokens():
    sleep(1)
    run(args.cli_bin + 'push action eosio.token create \'["eosio", "10000000000.0000 %s"]\' -p eosio.token' % (args.symbol))
    total_allocation = allocate_funds(0, len(ACCOUNTS)) + 1_000 * 10_000
    run(args.cli_bin + 'push action eosio.token issue \'["eosio", "%s", "memo"]\' -p eosio' % int_to_currency(total_allocation))
    sleep(1)

def step_set_system_contract():
    sleep(1)
    retry(args.cli_bin + 'set contract eosio ' + args.contracts_dir + '/eosio.system/')
    sleep(1)
    run(args.cli_bin + 'push action eosio setpriv' + json_arg(['eosio.msig', 1]) + '-p eosio@active')

def step_init_system_contract():
    run(args.cli_bin + 'push action eosio init' + json_arg(['0', '4,SYS']) + '-p eosio@active')
    sleep(1)

def step_create_staked_accounts():
    create_staked_accounts(0, len(ACCOUNTS))

def step_reg_producers():
    reg_producers(FIRST_PRODUCER, FIRST_PRODUCER + NUM_PRODUCERS)
    sleep(1)
    list_producers()

def step_start_producers():
    start_producers(FIRST_PRODUCER, FIRST_PRODUCER + NUM_PRODUCERS)
    sleep(args.producer_sync_delay)

def step_vote():
    vote(0, 0 + args.num_voters)
    sleep(1)
    list_producers()
    sleep(1)

def step_proxy_votes():
    proxy_votes(0, 0 + args.num_voters)

def step_resign():
    resign('eosio', 'eosio.prods')
    for a in SYSTEM_ACCOUNTS:
        resign(a, 'eosio')

def step_transfer():
    while True:
        random_transfer(0, args.num_senders)

def step_log():
    run('tail -n 60 ' + args.nodes_dir + '00-eosio/stderr')

###

if __name__ == '__main__':
    # parse options
    parser = argparse.ArgumentParser()

    commands = [
        ('k', 'kill',               step_kill_all,                 True,    "Kill all node and wallet processes"),
        ('w', 'wallet',             step_start_wallet,             True,    "Start wallet, create wallet, fill with keys"),
        ('b', 'boot',               step_start_boot,               True,    "Start boot node"),
        ('s', 'sys',                create_system_accounts,        True,    "Create system accounts (eosio.*)"),
        ('c', 'contracts',          step_install_system_contracts, True,    "Install system contracts (token, msig)"),
        ('t', 'tokens',             step_create_tokens,            True,    "Create tokens"),
        ('S', 'sys-contract',       step_set_system_contract,      True,    "Set system contract"),
        ('I', 'init-sys-contract',  step_init_system_contract,     True,    "Initialiaze system contract"),
        ('T', 'stake',              step_create_staked_accounts,   True,    "Create staked accounts"),
        ('p', 'reg-prod',           step_reg_producers,            True,    "Register producers"),
        ('P', 'start-prod',         step_start_producers,          True,    "Start producers"),
        ('v', 'vote',               step_vote,                     True,    "Vote for producers"),
        # ('R', 'claim',              claim_rewards,                 True,    "Claim rewards"),
        # ('x', 'proxy',              step_proxy_votes,              True,    "Proxy votes"),
        # ('q', 'resign',             step_resign,                   True,    "Resign eosio"),
        # ('m', 'msg-replace',        msig_replace_system,           False,   "Replace system contract using msig"),
        # ('X', 'xfer',               step_transfer,                 False,   "Random transfer tokens (infinite loop)"),
        ('l', 'log',                step_log,                       True,    "Show tail of node's log"),
    ]

    parser.add_argument('--public_key',     metavar='KEY',  help='EOSIO Public Key',                     default=DEFAULT_PUBLIC_KEY)
    parser.add_argument('--private-key',    metavar='KEY',  help='EOSIO Private Key',                    default=DEFAULT_PRIVATE_KEY)
    parser.add_argument('--cli-bin',        metavar='PATH', help='Path to CLI binary',                   default=DEFAULT_CLI_BIN)
    parser.add_argument('--node-bin',       metavar='PATH', help='Path to node binary',                  default=DEFAULT_NODE_BIN)
    parser.add_argument('--wallet-bin',     metavar='PATH', help='Path to wallet binary',                default=DEFAULT_WALLET_BIN)
    parser.add_argument('--contracts-dir',  metavar='DIR',  help='Path to contracts directory',          default=DEFAULT_CONTRACTS_DIR)
    parser.add_argument('--nodes-dir',      metavar='DIR',  help='Path to nodes directory',              default=DEFAULT_NODES_DIR)
    parser.add_argument('--genesis',        metavar='FILE', help='Path to genesis.json',                 default=DEFAULT_GENESIS_JSON)
    parser.add_argument('--wallet-dir',     metavar='DIR',  help='Path to wallet directory',             default=DEFAULT_WALLET_DIR)
    parser.add_argument('--logging-json',   metavar='FILE', help='Path to logging.json file (for node)', default=DEFAULT_LOGGING_JSON)
    parser.add_argument('--http-port',      metavar='PORT', help='HTTP port for CLI',                    type=int, default=8000)

    parser.add_argument('--symbol',              metavar='STR', help='The eosio.system symbol',                        default='SYS')
    parser.add_argument('--user-limit',          metavar='N',   help='Max number of users (0 = no limit)',             type=int,   default=0)
    parser.add_argument('--max-user-keys',       metavar='N',   help='Maximum user keys to import into wallet',        type=int,   default=10)
    parser.add_argument('--ram-funds',           metavar='N',   help='How much funds for each user to spend on ram',   type=float, default=0.1)
    parser.add_argument('--min-stake',           metavar='N',   help='Minimum stake before allocating unstaked funds', type=float, default=0.9)
    parser.add_argument('--max-unstaked',        metavar='N',   help='Maximum unstaked funds',                         type=float, default=10.0)
    parser.add_argument('--producer-limit',      metavar='N',   help='Maximum number of producers (0 = no limit)',     type=int,   default=21)
    parser.add_argument('--min-producer-funds',  metavar='N',   help='Minimum producer funds',                         type=float, default=1000.0)
    parser.add_argument('--num-producers-vote',  metavar='N',   help='Number of producers for which each user votes',  type=int,   default=20)
    parser.add_argument('--num-voters',          metavar='N',   help='Number of voters',                               type=int,   default=99)
    parser.add_argument('--num-senders',         metavar='N',   help='Number of users to transfer funds randomly',     type=int,   default=10)
    parser.add_argument('--producer-sync-delay', metavar='N',   help='Time (s) to sleep to allow producers to sync',   type=int,   default=5)

    parser.add_argument('-a', '--all',     action='store_true', help='Do everything marked with (*)')
    parser.add_argument('-n', '--dry-run', action='store_true', help='Only print commands, do not execute them')

    for (flag, command, function, in_all, help) in commands:
        prefix = ''
        if in_all: prefix += '*'
        if prefix: help = '(' + prefix + ') ' + help
        if flag:
            parser.add_argument('-' + flag, '--' + command, action='store_true', help=help, dest=command)
        else:
            parser.add_argument('--' + command, action='store_true', help=help, dest=command)

    args = parser.parse_args()

    if args.dry_run:
        print('DRY RUN mode')

    args.cli_bin += ' --wallet-url http://127.0.0.1:6666 --url http://127.0.0.1:%d ' % args.http_port

    with open('accounts.json') as f:
        a = json.load(f)
        if args.user_limit:
            del a['users'][args.user_limit:]
        else:
            a['users'] = []

        if args.producer_limit:
            del a['producers'][args.producer_limit:]
        FIRST_PRODUCER = len(a['users'])
        NUM_PRODUCERS = len(a['producers'])
        ACCOUNTS = a['users'] + a['producers']

    MAX_CLIENTS = NUM_PRODUCERS + 10

    noop = True
    for (flag, command, function, in_all, help) in commands:
        if getattr(args, command) or in_all and args.all:
            if function:
                noop = False
                function()
    if noop:
        print('bios-boot-tutorial.py: Tell me what to do. -a does almost everything. -h shows options.')
