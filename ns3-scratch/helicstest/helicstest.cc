#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "helics/application_api/ValueFederate.hpp"
#include <vector>
#include <map>
#include <fstream>

using namespace ns3;
NS_LOG_COMPONENT_DEFINE("CpsTestbed");

static Ptr<Socket> g_pmuSocket;
static std::map<uint32_t,double> g_sendTime;
static std::map<uint32_t,double> g_recvV;
static std::map<uint32_t,double> g_trueV;     // actual value before any tampering
static std::map<uint32_t,double> g_delayMs;
static std::map<uint32_t,bool>   g_attacked;  // was this bus tampered?
static uint32_t g_rxCount = 0;
static double g_vLimit = 1.08;
static std::string g_pendingCommand;

// attack config
static bool     g_attackOn = false;
static uint32_t g_attackBus = 8;       // which bus to target
static double   g_fakeV = 1.05;
static uint32_t g_dropBus = 0;

void SendVoltage(uint32_t bus, double trueV) {
  if (g_dropBus != 0 && bus == g_dropBus) {
    std::cout << "[LOSS] bus " << bus << " packet dropped (targeted)" << std::endl;
    return;
  }
  double txV = trueV;
  bool tampered = false;
  // ---- FALSE DATA INJECTION: rewrite the targeted bus's value ----
  if (g_attackOn && bus == g_attackBus) {
    txV = g_fakeV;
    tampered = true;
  }
  g_trueV[bus] = trueV;
  g_attacked[bus] = tampered;

  std::ostringstream msg;
  msg << "bus=" << bus << ";V=" << txV;
  std::string s = msg.str();
  Ptr<Packet> pkt = Create<Packet>((uint8_t*)s.c_str(), s.size());
  g_sendTime[bus] = Simulator::Now().GetSeconds();
  g_pmuSocket->Send(pkt);
  std::cout << "[PMU-node0] sent bus=" << bus << " V=" << txV << " into network" << std::endl;
  if (tampered)
    std::cout << "[ATTACK] bus " << bus << " true V=" << trueV
              << " -> INJECTED FAKE V=" << txV << " (hiding violation)" << std::endl;
}

void PdcReceive(Ptr<Socket> socket) {
  Ptr<Packet> pkt;
  while ((pkt = socket->Recv())) {
    uint32_t sz = pkt->GetSize();
    std::vector<uint8_t> buf(sz);
    pkt->CopyData(buf.data(), sz);
    std::string s((char*)buf.data(), sz);
    uint32_t bus = 0; float v = 0;
    sscanf(s.c_str(), "bus=%u;V=%f", &bus, &v);
    double now = Simulator::Now().GetSeconds();
    g_rxCount++;
    g_recvV[bus] = v;
    g_delayMs[bus] = (now - g_sendTime[bus]) * 1000.0;
    std::cout << "[PDC-node1] received bus=" << bus << " V=" << v << " (delay " << g_delayMs[bus] << " ms)" << std::endl;
    // PDC decides based on what it RECEIVED (possibly tampered)
    if (v > g_vLimit) {
      std::ostringstream c; c << "REDUCE_VOLTAGE@bus" << bus;
      g_pendingCommand = c.str();
      std::cout << "[PDC] bus " << bus << " V=" << v
                << " -> VIOLATION detected, command raised" << std::endl;
    }
  }
}

int main (int argc, char *argv[])
{
  double latencyMs = 10.0;
  double lossRate = 0.0;
  bool attack = false;
  std::string scenario = "run";
  CommandLine cmd;
  cmd.AddValue("latency", "link latency in ms", latencyMs);
  cmd.AddValue("loss", "packet loss rate 0..1", lossRate);
  cmd.AddValue("attack", "enable false data injection", attack);
  cmd.AddValue("name", "scenario name", scenario);
  uint32_t dropBus = 0;
  cmd.AddValue("droppmu", "drop a specific bus packet", dropBus);
  cmd.Parse (argc, argv);
  g_attackOn = attack;
  g_dropBus = dropBus;

  helics::FederateInfo fi;
  fi.coreType = helics::CoreType::ZMQ;
  fi.coreInitString = "--federates=1";
  fi.setProperty(HELICS_PROPERTY_TIME_DELTA, 1.0);
  auto fed = std::make_shared<helics::ValueFederate>("ns3_network", fi);
  auto sub = fed->registerSubscription("gridpack/bus1_voltage");
  auto cmdPub = fed->registerGlobalPublication<std::string>("ns3/control_command");

  NodeContainer nodes; nodes.Create(2);
  PointToPointHelper p2p;
  p2p.SetDeviceAttribute("DataRate", StringValue("10Mbps"));
  p2p.SetChannelAttribute("Delay", TimeValue(MilliSeconds(latencyMs)));
  NetDeviceContainer devs = p2p.Install(nodes);

  if (lossRate > 0.0) {
    Ptr<RateErrorModel> em = CreateObject<RateErrorModel>();
    em->SetAttribute("ErrorRate", DoubleValue(lossRate));
    em->SetAttribute("ErrorUnit", StringValue("ERROR_UNIT_PACKET"));
    devs.Get(1)->SetAttribute("ReceiveErrorModel", PointerValue(em));
  }

  InternetStackHelper stack; stack.Install(nodes);
  Ipv4AddressHelper addr; addr.SetBase("10.1.1.0", "255.255.255.0");
  Ipv4InterfaceContainer ifaces = addr.Assign(devs);

  uint16_t port = 5000;
  Ptr<Socket> pdcSocket = Socket::CreateSocket(nodes.Get(1),
      TypeId::LookupByName("ns3::UdpSocketFactory"));
  pdcSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), port));
  pdcSocket->SetRecvCallback(MakeCallback(&PdcReceive));

  g_pmuSocket = Socket::CreateSocket(nodes.Get(0),
      TypeId::LookupByName("ns3::UdpSocketFactory"));
  g_pmuSocket->Bind();
  g_pmuSocket->Connect(InetSocketAddress(ifaces.GetAddress(1), port));

  fed->enterExecutingMode();
  std::cout << "[CPS] scenario=" << scenario << " latency=" << latencyMs
            << "ms loss=" << (lossRate*100) << "% attack="
            << (attack ? "ON (FDI on bus 8)" : "OFF") << std::endl;

  uint32_t busNum = 0;
  std::map<uint32_t,double> sentTrueV;
  helics::Time t = 0.0;
  while (t < 15.0) {
    t = fed->requestTime(15.0);
    if (sub.isUpdated()) {
      busNum++;
      double v = sub.getDouble();
      sentTrueV[busNum] = v;
      Simulator::Schedule(Seconds(0.0), &SendVoltage, busNum, v);
      Simulator::Stop(MilliSeconds(latencyMs * 2 + 50));
      Simulator::Run();
      if (!g_pendingCommand.empty()) {
        cmdPub.publish(g_pendingCommand);
        std::cout << "[CONTROL] command -> GridPACK: " << g_pendingCommand << std::endl;
        g_pendingCommand.clear();
      } else cmdPub.publish("");
    }
  }
  fed->finalize();

  // ---- results CSV: true vs received (delivered), with attack flag ----
  std::string base = "/home/ubuntu/cps-testbed/results/";
  std::ofstream out(base + "last_compare.csv");
  out << "bus,sent_v,recv_v,delay_ms,delivered,attacked\n";
  uint32_t lost = 0, violations = 0, missed = 0;
  double delaySum = 0, delayMax = 0;
  for (uint32_t b = 1; b <= busNum; ++b) {
    double trueV = sentTrueV[b];
    out << b << "," << trueV << ",";
    bool atk = g_attacked.count(b) ? g_attacked[b] : false;
    if (g_recvV.count(b)) {
      double d = g_delayMs[b];
      out << g_recvV[b] << "," << d << ",1," << (atk?1:0) << "\n";
      delaySum += d; if (d > delayMax) delayMax = d;
      if (g_recvV[b] > g_vLimit) violations++;
      // a MISSED violation: true value is a violation but received value hid it
      if (trueV > g_vLimit && g_recvV[b] <= g_vLimit) missed++;
    } else { out << ",," << "0," << (atk?1:0) << "\n"; lost++; }
  }
  out.close();

  double avgDelay = (g_rxCount>0) ? delaySum/g_rxCount : 0;
  double lossPct = (busNum>0) ? 100.0*lost/busNum : 0;

  std::ofstream js(base + "last_summary.json");
  js << "{\n"
     << "  \"scenario\": \"" << scenario << "\",\n"
     << "  \"latency_ms\": " << latencyMs << ",\n"
     << "  \"attack\": \"" << (attack ? "FALSE DATA INJECTION (bus 8)" : "none") << "\",\n"
     << "  \"total_buses\": " << busNum << ",\n"
     << "  \"delivered\": " << g_rxCount << ",\n"
     << "  \"lost\": " << lost << ",\n"
     << "  \"loss_actual_pct\": " << lossPct << ",\n"
     << "  \"violations_seen_by_pdc\": " << violations << ",\n"
     << "  \"missed_violations\": " << missed << ",\n"
     << "  \"avg_delay_ms\": " << avgDelay << ",\n"
     << "  \"max_delay_ms\": " << delayMax << ",\n"
     << "  \"helics_status\": \"connected (2 federates synced)\",\n"
     << "  \"gridpack\": \"IEEE 14-bus power flow\",\n"
     << "  \"ns3\": \"PMU->PDC UDP over point-to-point\"\n"
     << "}\n";
  js.close();

  std::cout << "[CPS] SUMMARY: delivered " << g_rxCount << "/" << busNum
            << ", violations seen " << violations
            << ", MISSED violations (hidden by attack) " << missed << std::endl;
  Simulator::Destroy();
  return 0;
}
