#!/bin/bash
sudo sysctl -w net.core.wmem_max=24912805
sudo sysctl -w net.core.rmem_max=24912805

SDR_IFACE=$(ifconfig | grep -B1 192.168..0.1 | grep -o "^\w*")
sudo ifconfig $SDR_IFACE mtu 9000
