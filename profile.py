#!/usr/bin/env python
import geni.portal as portal
import geni.rspec.pg as rspec
import geni.rspec.igext as IG
import geni.rspec.emulab.pnext as PN
import geni.rspec.emulab.ansible

from geni.rspec.emulab.ansible import Role, RoleBinding, Override, Playbook


tourDescription = """
###  OCUDU + srsRAN_4G on POWDER Paired Radio Workbench

This profile instantiates an experiment that deploys an end to end 5G network
using OCUDU (gNB), Open5GS (CN5G), and srsRAN_4G (nrUE) on one of the Paired
Radio Workbenches available on POWDER. These workbenches each include two USRP
X310s with at least one UBX160 daughterboard, and a common 10 MHz clock and PPS
reference provided by an OctoClock. The X310s on `bench_b` include two UBX160
daughterboards, making them suitable for 5G NSA or MIMO configurations. The
transceivers are connected via SMA cables through 30 dB attenuators, providing
for an interference free RF environment.

The following will be deployed on server-class compute nodes:

- Open5GS 5G/LTE core network (`cn5g`)
- OCUDU gNodeB (`cudu`, fiber connection to CN5G and X310)
- srsRAN_4G nrUE (`ue`, fiber connection to other X310)

All are installed via the `https://gitlab.flux.utah.edu/dmaas/ansible-nextg` Ansible collection.

"""

tourInstructions = """

Startup scripts will still be running after your experiment becomes ready. Watch
the "Startup" column on the "List View" tab for your experiment and wait until
all of the compute nodes show "Finished" before proceeding.

After all startup scripts have finished...

On `cn5g`:

```
# watch the Open5GS AMF log
sudo tail -f /var/log/open5gs/amf.log
```

On `cudu`:

```
# start gNB (numactl pins the process to a single CPU to improve performance)
sudo numactl --membind=0 --cpunodebind=0 /opt/ocudu/build/apps/gnb/gnb \\
    -c /etc/ocudu/gnb.yml
```

On `ue`:

```
# start srsRAN_4G nrUE
sudo /opt/srsRAN_4G/build/srsue/src/srsue /etc/srsran/ue.conf
```

As the UE attaches to the network, the AMF log and gNodeB process will show
progress as a PDU session for the UE is established.

"""

# N-heads: every node bootstraps itself, runs only its own role's playbook via
# ansible's local connection (the bootstrap auto-annotates the local node), and
# constrains the run-automation entrypoints to itself with --limit <hostname>.
HEAD_CMD = "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c 'EMULAB_ANSIBLE_NOAUTO=1 /local/repository/emulab-ansible-bootstrap/head.sh >/local/logs/setup.log 2>&1'"
TAIL_CMD = "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c 'EXTRA_OVERRIDES=\"--limit $(hostname -s)\" /local/setup/ansible/run-automation.sh >> /local/logs/setup.log 2>&1'"

ANSIBLE_VENV = "/local/setup/venv/default/bin"
ANSIBLE_COLLECTIONS_DIR = "~/.ansible/collections/ansible_collections"
NEXTG_UTILS_COLLECTION_NS = "dustinmaas/nextg_utils"
NEXTG_UTILS_COLLECTION_REPO = "git+https://gitlab.flux.utah.edu/dmaas/ansible-nextg"
GALAXY_INSTALL_CMD = "{}/ansible-galaxy collection install {} >> /local/logs/setup.log 2>&1".format(ANSIBLE_VENV, NEXTG_UTILS_COLLECTION_REPO)
GALAXY_INSTALL_REQS_CMD = "{}/ansible-galaxy install -r {}/{}/requirements.yml >> /local/logs/setup.log 2>&1".format(ANSIBLE_VENV, ANSIBLE_COLLECTIONS_DIR, NEXTG_UTILS_COLLECTION_NS)

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
    ("d760p", "Emulab, d760"),
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
    name="deployric",
    description="Deploy ORAN SC RIC and xApp on the gNB node.",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=False,
)

pc.defineParameter(
    name="do_deploy",
    description="Run Ansible deploy for OCUDU and srsRAN_4G",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True,
    advanced=True,
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
pc.verifyParameters()
request = pc.makeRequestRSpec()

# Declare Ansible roles. Each role becomes an inventory group of the same name,
# and its playbook runs against that group.
request.addRole(
    Role(
        "open5gs",
        path="ansible",
        playbooks=[Playbook("open5gs", path="open5gs.yml")]
    )
)
request.addRole(
    Role(
        "ocudu",
        path="ansible",
        playbooks=[Playbook("ocudu", path="ocudu.yml")]
    )
)
request.addRole(
    Role(
        "srsran_4g",
        path="ansible",
        playbooks=[Playbook("srsran_4g", path="srsran_4g.yml")]
    )
)

# The OCUDU role builds the 5GC in-tree by default; we deploy Open5GS on
# cn-host directly, so skip the 5GC build on the gNB node.
request.addOverride(Override("ocudu_build_5gc", value="false"))

# Build OCUDU and srsRAN_4G with UHD support; the workbench uses real X310s.
request.addOverride(Override("ocudu_enable_uhd", value="true"))
request.addOverride(Override("srsran_4g_enable_uhd", value="true"))

# Override the bundled Open5GS samples with this profile's configs.
request.addOverride(Override("open5gs_config_src", value="/local/repository/etc/open5gs/"))

if params.deployric:
    request.addOverride(Override("ocudu_enable_du_e2", value="true"))
    request.addOverride(Override("ocudu_e2sm_kpm_enabled", value="true"))

# CN host: Open5GS built from source via the open5gs Ansible role.
cn_node = request.RawPC("cn5g")
cn_node.component_manager_id = COMP_MANAGER_ID
cn_node.hardware_type = params.cn_nodetype
cn_node.disk_image = UBUNTU_IMG
cn_if = cn_node.addInterface("cn-if")
cn_if.addAddress(rspec.IPv4Address("192.168.1.1", "255.255.255.0"))
cn_link = request.Link("cn-link")
cn_link.addInterface(cn_if)

if params.do_deploy:
    cn_node.bindRole(RoleBinding("open5gs"))
    cn_node.addService(rspec.Execute(shell="sh", command=HEAD_CMD))
    cn_node.addService(rspec.Execute(shell="sh", command=GALAXY_INSTALL_CMD))
    cn_node.addService(rspec.Execute(shell="sh", command=GALAXY_INSTALL_REQS_CMD))
    cn_node.addService(rspec.Execute(shell="sh", command=TAIL_CMD))

# gNB compute node: OCUDU via Ansible.
nodeb = request.RawPC("cudu")
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

if params.do_deploy:
    nodeb.bindRole(RoleBinding("ocudu"))
    nodeb.addService(rspec.Execute(shell="sh", command=HEAD_CMD))
    nodeb.addService(rspec.Execute(shell="sh", command=GALAXY_INSTALL_CMD))
    nodeb.addService(rspec.Execute(shell="sh", command=GALAXY_INSTALL_REQS_CMD))
    nodeb.addService(rspec.Execute(shell="sh", command=TAIL_CMD))

nodeb_sdr = request.RawPC("ru-sdr")
nodeb_sdr.component_manager_id = COMP_MANAGER_ID
nodeb_sdr.component_id = BENCH_SDR_IDS[params.bench_id][0]
nodeb_sdr_if = nodeb_sdr.addInterface("nodeb-sdr-if")

nodeb_sdr_link = request.Link("nodeb-sdr-link")
nodeb_sdr_link.addInterface(nodeb_usrp_if)
nodeb_sdr_link.addInterface(nodeb_sdr_if)

# UE compute node: srsRAN_4G via Ansible.
ue = request.RawPC("ue")
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

if params.do_deploy:
    ue.bindRole(RoleBinding("srsran_4g"))
    ue.addService(rspec.Execute(shell="sh", command=HEAD_CMD))
    ue.addService(rspec.Execute(shell="sh", command=GALAXY_INSTALL_CMD))
    ue.addService(rspec.Execute(shell="sh", command=GALAXY_INSTALL_REQS_CMD))
    ue.addService(rspec.Execute(shell="sh", command=TAIL_CMD))

ue_sdr = request.RawPC("ue-sdr")
ue_sdr.component_manager_id = COMP_MANAGER_ID
ue_sdr.component_id = BENCH_SDR_IDS[params.bench_id][1]
ue_sdr_if = ue_sdr.addInterface("ue-sdr-if")

ue_sdr_link = request.Link("ue-sdr-link")
ue_sdr_link.addInterface(ue_usrp_if)
ue_sdr_link.addInterface(ue_sdr_if)

tour = IG.Tour()
tour.Description(IG.Tour.MARKDOWN, tourDescription)
tour.Instructions(IG.Tour.MARKDOWN, tourInstructions)
request.addTour(tour)

pc.printRequestRSpec(request)
