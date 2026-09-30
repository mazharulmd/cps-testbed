#!/bin/bash
# CPS Testbed scenario controller
# Usage: ./run_scenario.sh --latency=50 --name=myrun

LATENCY=10
LOSS=0.2
NAME="run"

for arg in "$@"; do
  case $arg in
    --latency=*) LATENCY="${arg#*=}" ;;
    --loss=*)    LOSS="${arg#*=}" ;;
    --name=*)    NAME="${arg#*=}" ;;
  esac
done

# paths
HELICS=$HOME/software/helics-cpp-install
NS3=$HOME/software/ns-3
VENV=$HOME/cps-env-ubuntu
RESULTS=$HOME/cps-testbed/results
mkdir -p "$RESULTS"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG="$RESULTS/${NAME}_${STAMP}.log"

export LD_LIBRARY_PATH=$HELICS/lib:$LD_LIBRARY_PATH

echo "=========================================="
echo " CPS Testbed Scenario: $NAME"
echo " Network latency: ${LATENCY} ms"
echo " Log: $LOG"
echo "=========================================="

# clean any stale processes
pkill -f helics_broker 2>/dev/null
pkill -f gridpack_fed 2>/dev/null
sleep 2

# 1. broker
$HELICS/bin/helics_broker -f 2 --loglevel=warning > /dev/null 2>&1 &
BROKER_PID=$!

# 2. GridPACK federate
cd $HOME
source $VENV/bin/activate
python3 gridpack_fed.py 2>&1 | tee "$LOG.gridpack" &

# 3. NS-3 network federate
cd $NS3
./ns3 run "helicstest --latency=$LATENCY --loss=$LOSS --name=$NAME" 2>&1 | tee "$LOG"

wait $BROKER_PID 2>/dev/null

echo ""
echo "=========================================="
echo " Scenario complete. Results saved:"
echo "   NS-3 / PDC log : $LOG"
echo "   GridPACK log   : $LOG.gridpack"
echo "=========================================="
