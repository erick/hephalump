#!/usr/bin/env python
# Copyright 2021-2024
# Georgia Tech
# All rights reserved
# Do not post or publish in any public or forbidden forums or websites

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.log import lg, info, setLogLevel
from mininet.util import dumpNodeConnections, quietRun, moveIntf
from mininet.cli import CLI
from mininet.node import Switch, OVSKernelSwitch

from subprocess import Popen, PIPE, check_output
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser

import sys
import os
import termcolor as T
import time

setLogLevel('info')

parser = ArgumentParser("Configure simple BGP network in Mininet.")
parser.add_argument('--rogue', action="store_true", default=False)
parser.add_argument('--scriptfile', default=None)
parser.add_argument('--sleep', default=3, type=int)
args = parser.parse_args()

FLAGS_rogue_as = args.rogue
ROGUE_AS_NAME = 'R6'

def log(s, col="green"):
    print(T.colored(s, col))


class Router(Switch):
    """The Router object provides a container (namespace) for individual routing entries"""

    ID = 0
    def __init__(self, name, **kwargs):
        kwargs['inNamespace'] = True
        Switch.__init__(self, name, **kwargs)
        Router.ID += 1
        self.switch_id = Router.ID

    @staticmethod
    def setup():
        return

    def start(self, controllers):
        pass

    def stop(self):
        self.deleteIntfs()

    def log(self, s, col="magenta"):
        print(T.colored(s, col))

class SimpleTopo(Topo):
    """The default topology is a simple straight-line topology between AS1 -- AS2 -- AS3.  The rogue AS (AS4) connects to AS1 directly."""

    def __init__(self):
        super(SimpleTopo, self ).__init__()

        hosts = []

        def create_router_and_hosts(as_num: int):
            router = f'R{as_num}'
            self.addSwitch(router)
            for host_num in [1, 2]:
                host = self.addNode(f'h{as_num}-{host_num}')
                hosts.append(host)
                self.addLink(router, host)


        create_router_and_hosts(1)
        create_router_and_hosts(2)
        create_router_and_hosts(3)
        create_router_and_hosts(4)
        create_router_and_hosts(5)
        create_router_and_hosts(6)

        self.addLink('R1', 'R2')   
        self.addLink('R1', 'R3')   
        self.addLink('R2', 'R3')  
        self.addLink('R2', 'R4')
        self.addLink('R2', 'R5')
        self.addLink('R3', 'R4')
        self.addLink('R3', 'R5')
        self.addLink('R4', 'R5')
        self.addLink('R5', 'R6')  


def parse_hostname(hostname):
    as_num, host_num = hostname.replace('h', '').split('-')
    return int(as_num), int(host_num)

def get_ip(hostname):
    as_num, host_num = parse_hostname(hostname)
    # AS4 is posing as AS3
    if as_num == 6:
        as_num = 1
    host_ip = f'{10+as_num}.0.{host_num}.1/24'
    return host_ip


def get_gateway(hostname):
    as_num, host_num = parse_hostname(hostname)
    # AS4 is posing as AS3
    if as_num == 6:
        as_num = 1
    gateway_ip = f'{10+as_num}.0.{host_num}.254'
    return gateway_ip


def start_webserver(net, hostname, text="Default web server 2.1.1"):
    host = net.getNodeByName(hostname)
    return host.popen(f"python webserver.py --text '{text}'", shell=True)


def main():
    os.system("rm -f /tmp/R*.log /tmp/R*.pid logs/*")
    os.system("mn -c >/dev/null 2>&1")
    os.system("pkill -9 bgpd > /dev/null 2>&1")
    os.system("pkill -9 zebra > /dev/null 2>&1")
    os.system('pkill -9 -f webserver.py')

    net = Mininet(topo=SimpleTopo(), switch=Router)
    net.start()
    for router in net.switches:
        router.cmd("sysctl -w net.ipv4.ip_forward=1")
        router.waitOutput()

    log(f"Waiting {args.sleep} seconds for sysctl changes to take effect...")
    sleep(args.sleep)

    for router in net.switches:
        if router.name == ROGUE_AS_NAME and not FLAGS_rogue_as:
            continue
        router.cmd("ip link set dev lo up ")
        router.waitOutput()
        router.cmd("/usr/lib/frr/zebra -f conf/zebra-%s.conf -d -i /tmp/zebra-%s.pid > logs/%s-zebra-stdout 2>&1" % (router.name, router.name, router.name))
        router.waitOutput()
        router.cmd("/usr/lib/frr/bgpd -f conf/bgpd-%s.conf -d -i /tmp/bgp-%s.pid > logs/%s-bgpd-stdout 2>&1" % (router.name, router.name, router.name), shell=True)
        router.waitOutput()
        log("Starting zebra and bgpd on %s" % router.name)

    for host in net.hosts:
        host.cmd("ifconfig %s-eth0 %s" % (host.name, get_ip(host.name)))
        host.cmd("route add default gw %s" % (get_gateway(host.name)))

    log("Starting web servers", 'yellow')
    start_webserver(net, 'h1-1', "Default web server 2.1.1")
    start_webserver(net, 'h6-1', "*** Attacker web server 2.1.1***")

    CLI(net, script=args.scriptfile)
    net.stop()
    os.system("pkill -9 bgpd")
    os.system("pkill -9 zebra")
    os.system('pkill -9 -f webserver.py')


if __name__ == "__main__":
    main()

