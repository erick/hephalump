#!/bin/bash
# Copyright 2021-2023
# Georgia Tech
# All rights reserved
# Do not post or publish in any public or forbidden forums or websites

echo "Killing any existing rogue AS"
sudo python run.py --node R6 --cmd "pkill -f --signal 9 [z]ebra-R6"
sudo python run.py --node R6 --cmd "pkill -f --signal 9 [b]gpd-R6"

echo "Starting rogue AS (hard)"
sudo python run.py --node R6 --cmd "/usr/lib/frr/zebra -f conf/zebra-R6-hard.conf -d -i /tmp/zebra-R6.pid > logs/R6-zebra-hard-stdout"
sudo python run.py --node R6 --cmd "/usr/lib/frr/bgpd -f conf/bgpd-R6-hard.conf -d -i /tmp/bgpd-R6.pid > logs/R6-bgpd-hard-stdout"
