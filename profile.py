#!/usr/bin/env python
import os
import geni.portal as portal
import geni.rspec.pg as rspec
import geni.rspec.igext as IG
import geni.rspec.emulab.pnext as PN


tourDescription = """
###  srsRAN on POWDER Paired Radio Workbench

This profile instantiates an experiment that can deploy an end to end 5G network
using srsRAN (gNB), Open5GS (CN5G), OAI (nrUE) using one of the Paired Radio
Workbenches available on POWDER. These workbenched all include two USRP X310s,
each with at least one UBX160 daughterboard, and a common 10 MHz clock and PPS
reference provided by an OctoClock. The X310s on `bench_b` include two UBX160
daughterboards, making them suitable for 5G NSA or MIMO configurations. The
transceivers are connected via SMA cables through 30 dB attenuators, providing
for an interference free RF environment.

The following will be deployed on server-class compute nodes:

- Open5GS 5G/LTE core network
- srsRAN gNodeB (fiber connection to CN5G and X310)
- (someday..) OAI 5G UE (fiber connection to other X310)

"""

tourInstructions = """

Startup scripts will still be running after your experiment becomes ready. Watch
the "Startup" column on the "List View" tab for your experiment and wait until
all of the compute nodes show "Finished" before proceeding.

After all startup scripts have finished...

#### srsRAN + Open5GS SA Mode

On `cn-host`:

```
# watch the Open5GS AMF log
sudo tail -f /var/log/open5gs/amf.log
```

On `nodeb-comp`:

```
# start gNB (we use numactl to bind the process to a single CPU to improve performance)
sudo numactl --membind=0 --cpunodebind=0 /var/tmp/srsRAN_Project/build/apps/gnb/gnb -c /local/repository/etc/srsran/gnb_rf_x310.yml
```

On `ue-comp`:

```
# build and start OAI UE

```

"""

BIN_PATH = "/local/repository/bin"
ETC_PATH = "/local/repository/etc"
IP_NAT_SCRIPT = os.path.join(BIN_PATH, "add-nat-and-ip-forwarding.sh")
DEFAULT_SRSRAN_HASH = "a15950301c5f3a1a166b79bb6c9ee901a4e8c2dd"
SRSRAN_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-srsran.sh")
OPEN5GS_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-open5gs.sh")
COMP_MANAGER_ID = "urn:publicid:IDN+emulab.net+authority+cm"
BENCH_SDR_IDS = {
    "bench_a": ["oai-wb-a1", "oai-wb-a2"],
    "bench_b": ["oai-wb-b1", "oai-wb-b2"],
}
UBUNTU_IMG = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"

pc = portal.Context()

node_types = [
    ("d430", "Emulab, d430"),
    ("d740", "Emulab, d740"),
]
pc.defineParameter(
    name="sdr_nodetype",
    description="Type of compute node paired with the SDRs",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[0],
    legalValues=node_types
)

pc.defineParameter(
    name="cn_nodetype",
    description="Type of compute node to use for CN node",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[0],
    legalValues=node_types
)

bench_ids = [
    ("bench_a", "Paired Radio Workbench A"),
    ("bench_b", "Paired Radio Workbench B"),
]
pc.defineParameter(
    name="bench_id",
    description="Which workbench bench to use",
    typ=portal.ParameterType.STRING,
    defaultValue=bench_ids[0],
    legalValues=bench_ids
)

pc.defineParameter(
    name="srsran_commit_hash",
    description="Commit hash for srsRAN",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True
)

pc.defineParameter(
    name="sdr_compute_image",
    description="Image to use for compute nodes connected to SDRs",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True
)

pc.defineParameter(
    name="nodeb_node_id",
    description="use a specific compute node for the nodeB",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True
)

pc.defineParameter(
    name="ue_node_id",
    description="use a specific compute node for the UE",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True
)

params = pc.bindParameters()
request = pc.makeRequestRSpec()

cn_node = request.RawPC("cn-host")
cn_node.component_manager_id = COMP_MANAGER_ID
cn_node.hardware_type = params.cn_nodetype
cn_node.disk_image = UBUNTU_IMG
cn_if = cn_node.addInterface("cn-if")
cn_if.addAddress(rspec.IPv4Address("192.168.1.1", "255.255.255.0"))
cn_link = request.Link("cn-link")
cn_link.bandwidth = 10*1000*1000
cn_link.addInterface(cn_if)
cn_node.addService(rspec.Execute(shell="bash", command=IP_NAT_SCRIPT))
cn_node.addService(rspec.Execute(shell="bash", command=OPEN5GS_DEPLOY_SCRIPT))

if params.srsran_commit_hash:
    srsran_hash = params.srsran_commit_hash
else:
    srsran_hash = DEFAULT_SRSRAN_HASH

nodeb = request.RawPC("nodeb-comp")
nodeb.component_manager_id = COMP_MANAGER_ID

if params.nodeb_node_id:
    nodeb.component_id = params.nodeb_node_id
else:
    nodeb.hardware_type = params.sdr_nodetype

if params.sdr_compute_image:
    nodeb.disk_image = params.sdr_compute_image
else:
    nodeb.disk_image = UBUNTU_IMG

nodeb_cn_if = nodeb.addInterface("nodeb-cn-if")
nodeb_cn_if.addAddress(rspec.IPv4Address("192.168.1.2", "255.255.255.0"))
cn_link.addInterface(nodeb_cn_if)

nodeb_usrp_if = nodeb.addInterface("nodeb-usrp-if")
nodeb_usrp_if.addAddress(rspec.IPv4Address("192.168.40.1", "255.255.255.0"))

cmd = "{} '{}'".format(SRSRAN_DEPLOY_SCRIPT, srsran_hash)
nodeb.addService(rspec.Execute(shell="bash", command=cmd))
nodeb.addService(rspec.Execute(shell="bash", command="/local/repository/bin/tune-cpu.sh"))
nodeb.addService(rspec.Execute(shell="bash", command="/local/repository/bin/tune-sdr-iface.sh"))

nodeb_sdr = request.RawPC("nodeb-sdr")
nodeb_sdr.component_manager_id = COMP_MANAGER_ID
nodeb_sdr.component_id = BENCH_SDR_IDS[params.bench_id][0]
nodeb_sdr_if = nodeb_sdr.addInterface("nodeb-sdr-if")

nodeb_sdr_link = request.Link("nodeb-sdr-link")
nodeb_sdr_link.bandwidth = 10*1000*1000
nodeb_sdr_link.addInterface(nodeb_usrp_if)
nodeb_sdr_link.addInterface(nodeb_sdr_if)

ue = request.RawPC("ue-comp")
ue.component_manager_id = COMP_MANAGER_ID

if params.ue_node_id:
    ue.component_id = params.ue_node_id
else:
    ue.hardware_type = params.sdr_nodetype

if params.sdr_compute_image:
    ue.disk_image = params.sdr_compute_image
else:
    ue.disk_image = UBUNTU_IMG

ue_usrp_if = ue.addInterface("ue-usrp-if")
ue_usrp_if.addAddress(rspec.IPv4Address("192.168.40.1", "255.255.255.0"))
ue.addService(rspec.Execute(shell="bash", command="/local/repository/bin/tune-sdr-iface.sh"))

ue_sdr = request.RawPC("ue-sdr")
ue_sdr.component_manager_id = COMP_MANAGER_ID
ue_sdr.component_id = BENCH_SDR_IDS[params.bench_id][1]
ue_sdr_if = ue_sdr.addInterface("ue-sdr-if")

ue_sdr_link = request.Link("ue-sdr-link")
ue_sdr_link.bandwidth = 10*1000*1000
ue_sdr_link.addInterface(ue_usrp_if)
ue_sdr_link.addInterface(ue_sdr_if)

tour = IG.Tour()
tour.Description(IG.Tour.MARKDOWN, tourDescription)
tour.Instructions(IG.Tour.MARKDOWN, tourInstructions)
request.addTour(tour)

pc.printRequestRSpec(request)
