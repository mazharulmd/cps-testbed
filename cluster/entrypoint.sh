#!/bin/bash
# Start-up of a CPS testbed cluster node. The role comes from CPS_ROLE:
#
#   head  web portal: Node-RED dashboard (1880) and experiment API (8080); HELICS brokers;
#         writes /shared/cluster.json and the MPI hostfile from the variables below
#   node  compute node: sshd only; runs GridPACK MPI ranks and federates on request
#
# Head variables (defaults in brackets):
#   CPS_NODES        MPI hosts and slots, "node1:2,node2:2"           [none: everything on the head]
#   CPS_PLACE_GRID   node running the grid federate (and mpirun)      [head]
#   CPS_PLACE_NS3    node running the NS-3 network federate           [head]
#   CPS_PLACE_CC     node running the control-center federate         [head]
#   CPS_MPI_NP       default GridPACK MPI ranks per experiment        [1]
#   CPS_MAX_JOBS     experiments that may run at the same time        [1]
#   CPS_WEB_PASSWORD / NODERED_ADMIN_HASH  logins for the API / Node-RED
#
# All nodes mount the same /shared volume; the head puts the cluster's SSH key there.
set -e
ROLE=${CPS_ROLE:-head}
HEAD=${CPS_HEAD:-$(hostname)}
mkdir -p /shared/runs /shared/grids /shared/legacy /root/.ssh
chmod 700 /root/.ssh

# variables for processes started over ssh (MPI ranks, remote federates)
env | grep -E '^(PATH|LD_LIBRARY_PATH|OMPI_|PRTE_|CPS_[A-Z_]*)=' | grep -v '^CPS_WEB_PASSWORD=' > /etc/environment

if [ "$ROLE" = head ]; then
  # one key pair for the cluster, created on first start and shared through /shared
  if [ ! -f /shared/.ssh/id_ed25519 ]; then
    mkdir -p /shared/.ssh && chmod 700 /shared/.ssh
    ssh-keygen -q -t ed25519 -N "" -C cps-cluster -f /shared/.ssh/id_ed25519
  fi
else
  echo "[node] waiting for the cluster key from the head ..."
  until [ -f /shared/.ssh/id_ed25519.pub ]; do sleep 1; done
fi
cp /shared/.ssh/id_ed25519 /shared/.ssh/id_ed25519.pub /root/.ssh/
cp /shared/.ssh/id_ed25519.pub /root/.ssh/authorized_keys
chmod 600 /root/.ssh/id_ed25519 /root/.ssh/authorized_keys
/usr/sbin/sshd

if [ "$ROLE" != head ]; then
  echo "[node] $(hostname) ready: $(nproc) cores"
  exec sleep infinity
fi

# ------------------------------------------------------------------ head
python3 - <<'EOF'
import json, os
head = os.environ.get("CPS_HEAD") or os.uname().nodename
nodes = []
for item in filter(None, os.environ.get("CPS_NODES", "").split(",")):
    host, _, slots = item.strip().partition(":")
    nodes.append({"host": host, "slots": int(slots or 1)})
cfg = {
    "head": head,
    "nodes": nodes,
    "placement": {"broker": head,
                  "grid": os.environ.get("CPS_PLACE_GRID", head),
                  "ns3": os.environ.get("CPS_PLACE_NS3", head),
                  "cc": os.environ.get("CPS_PLACE_CC", head)},
    "mpi": {"hostfile": "/shared/hostfile" if nodes else None,
            "default_np": int(os.environ.get("CPS_MPI_NP", "1"))},
    "helics_port_base": 23500,
    "max_parallel_jobs": int(os.environ.get("CPS_MAX_JOBS", "1")),
}
with open("/shared/hostfile", "w") as fh:
    fh.writelines(f"{n['host']} slots={n['slots']}\n" for n in nodes)
with open("/shared/cluster.json", "w") as fh:
    json.dump(cfg, fh, indent=1)
print("[head] cluster:", json.dumps(cfg))
EOF

# wait until every node answers over ssh (MPI and remote federates need it)
for host in $(python3 -c "import json;c=json.load(open('/shared/cluster.json'));print(' '.join(sorted({n['host'] for n in c['nodes']}|set(c['placement'].values()))))"); do
  [ "$host" = "$HEAD" ] && continue
  for i in $(seq 1 60); do ssh -o BatchMode=yes -o ConnectTimeout=2 "$host" true 2>/dev/null && break; sleep 1; done
  ssh -o BatchMode=yes "$host" true 2>/dev/null && echo "[head] $host reachable" || echo "[head] WARNING: $host not reachable"
done

cd /opt/cps-testbed/webapp
uvicorn app:app --host 0.0.0.0 --port 8080 &
node-red -u /opt/node-red-data &
wait -n
exit $?
