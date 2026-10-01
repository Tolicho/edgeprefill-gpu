#!/usr/bin/env python
import geni.portal as portal
import geni.rspec.pg as rspec
import geni.rspec.igext as IG
import geni.rspec.emulab.pnext as PN
import geni.rspec.emulab.ansible

from geni.rspec.emulab.ansible import (
    Role,
    RoleBinding,
    Override,
    Playbook,
)


tourDescription = """
### OCUDU + srsRAN_4G + Edge GPU on POWDER

This profile deploys an end-to-end 5G network using OCUDU (gNB),
Open5GS (CN5G), and srsRAN_4G (nrUE) on a POWDER Paired Radio
Workbench. It also allocates a GPU server for edge LLM experiments.

The workbenches each include two USRP X310s with a common 10 MHz
clock and PPS reference provided by an OctoClock. The transceivers
are connected through SMA cables and 30 dB attenuators.

Compute nodes:

- `cn5g`: Open5GS core network.
- `cudu`: OCUDU gNodeB, connected to the core and one X310.
- `ue`: srsRAN_4G nrUE, connected to the other X310.
- `edgegpu`: GPU server using hardware type `d760-hgpu`.

The 5G software is installed through the original repository's
Ansible deployment.

A dedicated experimental network connects `cn5g` to `edgegpu`:

- `cn5g`: 192.168.2.1/24
- `edgegpu`: 192.168.2.2/24

GPU drivers, the LLM runtime, and routing between the UE's
5G data interface and the GPU server require additional setup.
"""


tourInstructions = """
Startup scripts may still be running after the experiment becomes
ready. Open List View and wait until startup services on `cn5g`,
`cudu`, and `ue` show Finished before proceeding.

On `cn5g`, watch the Open5GS AMF log:
