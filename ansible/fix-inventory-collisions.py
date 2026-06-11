#!/usr/bin/env python3
"""
Pre-playbook fixup for emulab-ansible-bootstrap inventories.

The bootstrap generates /local/setup/ansible/inventory.ini by emitting each
node's short name and relying on /etc/hosts for resolution. POWDER's
nameservice maps the short name to the node's first addressed interface in
the rspec. When that interface is on a private point-to-point link (e.g. an
SDR link) whose subnet is reused on the head node, the short name resolves
to one of the head's own interface IPs, so SSH from the head to the
"remote" node loops back to localhost. The remote play then runs on the
wrong host.

This script walks the inventory, resolves each host's short name, and for
any entry whose resolved IP is also on a local interface of the head, it
appends `ansible_host=<short>.<domain>` so ansible connects to the
management FQDN instead. Idempotent and a no-op if no collision is found.
"""
import socket
import subprocess
import sys

INV_PATH = "/local/setup/ansible/inventory.ini"


def emulab_experiment_domain() -> str:
    """Return the Emulab/POWDER experiment domain, e.g.
    "ocudu-x310.powdersandbox.emulab.net". Falls back to the socket-derived
    domain if geni-get is unavailable or its output cannot be parsed.

    geni-get returns a slice URN of the form
        urn:publicid:IDN+<tld>:<project>+slice+<experiment>
    from which the experiment FQDN suffix is <experiment>.<project>.<tld>.
    """
    try:
        urn = subprocess.check_output(["geni-get", "slice_urn"], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        urn = ""
    if urn.startswith("urn:publicid:IDN+") and "+slice+" in urn:
        head, exp = urn.rsplit("+slice+", 1)
        body = head[len("urn:publicid:IDN+"):]
        if ":" in body:
            tld, project = body.split(":", 1)
            return "{}.{}.{}".format(exp, project, tld)
    fqdn = socket.getfqdn()
    if "." in fqdn:
        return fqdn.split(".", 1)[1]
    return ""


def main() -> int:
    domain = emulab_experiment_domain()
    if not domain:
        return 0

    local_ips = set()
    out = subprocess.check_output(["ip", "-4", "-o", "addr", "show"], text=True)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and "/" in parts[3]:
            local_ips.add(parts[3].split("/", 1)[0])

    try:
        with open(INV_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return 0

    # First pass: identify hosts already declared with a local connection
    # anywhere in the file. They never need rewriting (and would be no-ops
    # at best, since the local connection plugin ignores ansible_host).
    local_conn_hosts = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        if "ansible_connection=local" in stripped:
            local_conn_hosts.add(stripped.split()[0])

    changed = False
    new_lines = []
    for line in lines:
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            new_lines.append(line)
            continue
        if "ansible_host=" in stripped:
            new_lines.append(line)
            continue
        name = stripped.split()[0]
        if name in local_conn_hosts:
            new_lines.append(line)
            continue
        try:
            ip = socket.gethostbyname(name)
        except (socket.gaierror, OSError):
            new_lines.append(line)
            continue
        if ip in local_ips:
            new_lines.append("{} ansible_host={}.{}\n".format(raw, name, domain))
            changed = True
        else:
            new_lines.append(line)

    if changed:
        with open(INV_PATH, "w") as f:
            f.writelines(new_lines)
        print("fix-inventory-collisions: rewrote {}".format(INV_PATH))
    else:
        print("fix-inventory-collisions: no collisions detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
