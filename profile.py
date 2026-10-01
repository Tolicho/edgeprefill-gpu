#!/usr/bin/env python
import geni.portal as portal
import geni.rspec.pg as rspec
import geni.rspec.igext as IG
import geni.rspec.emulab.pnext as PN
import geni.rspec.emulab.ansible

from geni.rspec.emulab.ansible import Role, RoleBinding, Override, Playbook


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

The original repository's Ansible deployment installs the 5G software.

A dedicated experimental network connects the core to the GPU server:

- `cn5g`: 192.168.2.1/24
- `edgegpu`: 192.168.2.2/24

GPU drivers, the LLM runtime, and routing between the UE's 5G data
interface and the GPU server require additional setup after deployment.
"""

# Indented Markdown commands avoid nested code fences when copying this file.
tourInstructions = """
Startup scripts may still be running after the experiment becomes ready.
Open List View and wait until startup services on `cn5g`, `cudu`, and
`ue` show Finished before proceeding.

On `cn5g`, watch the Open5GS AMF log:

    sudo tail -f /var/log/open5gs/amf.log

On `cudu`, start the gNodeB:

    sudo /opt/ocudu/build/apps/gnb/gnb -c /etc/ocudu/gnb.yml

On `ue`, start the nrUE:

    sudo /opt/srsRAN_4G/build/srsue/src/srsue /etc/srsran/ue.conf

Watch the AMF and gNodeB output for UE registration and establishment
of a PDU session.

On `edgegpu`, inspect the GPU hardware:

    lspci | grep -Ei 'nvidia|3d controller|vga'

If NVIDIA drivers are already installed, inspect them with:

    nvidia-smi

The GPU data address is 192.168.2.2. Before measuring prompt delivery,
configure and verify UE-to-GPU routing through the 5G user plane.
"""

HEAD_CMD = (
    "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c "
    "'EMULAB_ANSIBLE_NOAUTO=1 "
    "/local/repository/emulab-ansible-bootstrap/head.sh "
    ">/local/logs/setup.log 2>&1'"
)

TAIL_CMD = (
    "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c "
    "'/local/setup/ansible/run-automation.sh "
    ">> /local/logs/setup.log 2>&1'"
)

CLIENT_CMD = (
    "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c "
    "'/local/repository/emulab-ansible-bootstrap/client.sh "
    ">/local/logs/setup.log 2>&1'"
)

ANSIBLE_VENV = "/local/setup/venv/default/bin"
ANSIBLE_COLLECTIONS_DIR = "~/.ansible/collections/ansible_collections"
NEXTG_UTILS_COLLECTION_NS = "dustinmaas/nextg_utils"
NEXTG_UTILS_COLLECTION_REPO = (
    "git+https://gitlab.flux.utah.edu/dmaas/ansible-nextg"
)

GALAXY_INSTALL_CMD = (
    "{}/ansible-galaxy collection install {} "
    ">> /local/logs/setup.log 2>&1"
).format(ANSIBLE_VENV, NEXTG_UTILS_COLLECTION_REPO)

GALAXY_INSTALL_REQS_CMD = (
    "{}/ansible-galaxy install -r {}/{}/requirements.yml "
    ">> /local/logs/setup.log 2>&1"
).format(
    ANSIBLE_VENV,
    ANSIBLE_COLLECTIONS_DIR,
    NEXTG_UTILS_COLLECTION_NS,
)

COMP_MANAGER_ID = "urn:publicid:IDN+emulab.net+authority+cm"

BENCH_SDR_IDS = {
    "bench_a": ["oai-wb-a1", "oai-wb-a2"],
    "bench_b": ["oai-wb-b1", "oai-wb-b2"],
}

UBUNTU_IMG = (
    "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"
)

GPU_NODE_TYPE = "d760-hgpu"

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
    defaultValue="d740",
    legalValues=node_types,
)

pc.defineParameter(
    name="cn_nodetype",
    description="Type of compute node to use for CN node",
    typ=portal.ParameterType.STRING,
    defaultValue="d740",
    legalValues=node_types,
)

bench_ids = [
    ("bench_a", "Paired Radio Workbench A"),
    ("bench_b", "Paired Radio Workbench B"),
]

pc.defineParameter(
    name="bench_id",
    description="Which paired radio workbench to use",
    typ=portal.ParameterType.STRING,
    defaultValue="bench_b",
    legalValues=bench_ids,
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
    advanced=True,
)

pc.defineParameter(
    name="nodeb_node_id",
    description="Use a specific compute node for the nodeB",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True,
)

pc.defineParameter(
    name="ue_node_id",
    description="Use a specific compute node for the UE",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True,
)

params = pc.bindParameters()
pc.verifyParameters()
request = pc.makeRequestRSpec()

# Preserve the original Ansible roles and playbooks.
request.addRole(
    Role(
        "open5gs",
        path="ansible",
        playbooks=[
            Playbook(
                "open5gs",
                path="open5gs.yml",
                pre_hook="./fix-inventory-collisions.py",
            )
        ],
    )
)

request.addRole(
    Role(
        "ocudu",
        path="ansible",
        playbooks=[Playbook("ocudu", path="ocudu.yml")],
    )
)

request.addRole(
    Role(
        "srsran_4g",
        path="ansible",
        playbooks=[Playbook("srsran_4g", path="srsran_4g.yml")],
    )
)

# Open5GS runs on its own core node.
request.addOverride(Override("ocudu_build_5gc", value="false"))

# Enable UHD support for the real X310 radios.
request.addOverride(Override("ocudu_enable_uhd", value="true"))
request.addOverride(Override("srsran_4g_enable_uhd", value="true"))

request.addOverride(
    Override(
        "open5gs_config_src",
        value="/local/repository/etc/open5gs/",
    )
)

if params.deployric:
    request.addOverride(
        Override("ocudu_enable_du_e2", value="true")
    )
    request.addOverride(
        Override("ocudu_e2sm_kpm_enabled", value="true")
    )

# Open5GS core node.
cn_node = request.RawPC("cn5g")
cn_node.component_manager_id = COMP_MANAGER_ID
cn_node.hardware_type = params.cn_nodetype
cn_node.disk_image = UBUNTU_IMG

cn_if = cn_node.addInterface("cn-if")
cn_if.addAddress(
    rspec.IPv4Address("192.168.1.1", "255.255.255.0")
)

cn_link = request.Link("cn-link")
cn_link.addInterface(cn_if)

if params.do_deploy:
    cn_node.bindRole(RoleBinding("open5gs"))
    cn_node.addService(
        rspec.Execute(shell="sh", command=CLIENT_CMD)
    )

# gNodeB compute node.
nodeb = request.RawPC("cudu")
nodeb.component_manager_id = COMP_MANAGER_ID

if params.nodeb_node_id:
    nodeb.component_id = params.nodeb_node_id
else:
    nodeb.hardware_type = params.sdr_nodetype

nodeb.disk_image = params.sdr_compute_image or UBUNTU_IMG

nodeb_cn_if = nodeb.addInterface("nodeb-cn-if")
nodeb_cn_if.addAddress(
    rspec.IPv4Address("192.168.1.2", "255.255.255.0")
)
cn_link.addInterface(nodeb_cn_if)

nodeb_usrp_if = nodeb.addInterface("nodeb-usrp-if")
nodeb_usrp_if.addAddress(
    rspec.IPv4Address("192.168.40.1", "255.255.255.0")
)

if params.do_deploy:
    nodeb.bindRole(RoleBinding("ocudu"))
    nodeb.addService(
        rspec.Execute(shell="sh", command=HEAD_CMD)
    )
    nodeb.addService(
        rspec.Execute(shell="sh", command=GALAXY_INSTALL_CMD)
    )
    nodeb.addService(
        rspec.Execute(shell="sh", command=GALAXY_INSTALL_REQS_CMD)
    )
    nodeb.addService(
        rspec.Execute(shell="sh", command=TAIL_CMD)
    )

# gNodeB radio.
nodeb_sdr = request.RawPC("ru-sdr")
nodeb_sdr.component_manager_id = COMP_MANAGER_ID
nodeb_sdr.component_id = BENCH_SDR_IDS[params.bench_id][0]

nodeb_sdr_if = nodeb_sdr.addInterface("nodeb-sdr-if")

nodeb_sdr_link = request.Link("nodeb-sdr-link")
nodeb_sdr_link.addInterface(nodeb_usrp_if)
nodeb_sdr_link.addInterface(nodeb_sdr_if)

# UE compute node.
ue = request.RawPC("ue")
ue.component_manager_id = COMP_MANAGER_ID

if params.ue_node_id:
    ue.component_id = params.ue_node_id
else:
    ue.hardware_type = params.sdr_nodetype

ue.disk_image = params.sdr_compute_image or UBUNTU_IMG

ue_usrp_if = ue.addInterface("ue-usrp-if")

# The two radio Ethernet links are separate networks,
# so the original profile uses the same address on each.
ue_usrp_if.addAddress(
    rspec.IPv4Address("192.168.40.1", "255.255.255.0")
)

if params.do_deploy:
    ue.bindRole(RoleBinding("srsran_4g"))
    ue.addService(
        rspec.Execute(shell="sh", command=CLIENT_CMD)
    )

# UE radio.
ue_sdr = request.RawPC("ue-sdr")
ue_sdr.component_manager_id = COMP_MANAGER_ID
ue_sdr.component_id = BENCH_SDR_IDS[params.bench_id][1]

ue_sdr_if = ue_sdr.addInterface("ue-sdr-if")

ue_sdr_link = request.Link("ue-sdr-link")
ue_sdr_link.addInterface(ue_usrp_if)
ue_sdr_link.addInterface(ue_sdr_if)

# GPU server for edge LLM inference.
# Configure GPU drivers and the inference runtime after boot.
edgegpu = request.RawPC("edgegpu")
edgegpu.component_manager_id = COMP_MANAGER_ID
edgegpu.hardware_type = GPU_NODE_TYPE
edgegpu.disk_image = UBUNTU_IMG

# Dedicated experimental data network from the core to the GPU.
cn_edge_if = cn_node.addInterface("cn-edge-if")
cn_edge_if.addAddress(
    rspec.IPv4Address("192.168.2.1", "255.255.255.0")
)

gpu_if = edgegpu.addInterface("gpu-data-if")
gpu_if.addAddress(
    rspec.IPv4Address("192.168.2.2", "255.255.255.0")
)

edge_link = request.Link("edge-link")
edge_link.addInterface(cn_edge_if)
edge_link.addInterface(gpu_if)

tour = IG.Tour()
tour.Description(IG.Tour.MARKDOWN, tourDescription)
tour.Instructions(IG.Tour.MARKDOWN, tourInstructions)
request.addTour(tour)

pc.printRequestRSpec(request)
