#!/usr/bin/env python3
import os

os.system("rm -f /tmp/R*.log /tmp/R*.pid logs/*")
os.system("mn -c >/dev/null 2>&1")
os.system("pkill -9 bgpd > /dev/null 2>&1")
os.system("pkill -9 zebra > /dev/null 2>&1")
os.system("pkill -9 -f webserver.py > /dev/null 2>&1")
