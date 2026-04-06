import joblib
import pandas as pd
import numpy as np
from nfstream import NFPlugin, NFStreamer
import datetime
import sys



# 1. The Detection Plugin
class IDSDetector(NFPlugin):
    def __init__(self, model_path):
        super().__init__()
        # Load the model you just trained
        try:
            self.model = joblib.load(r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\ids_random_forest_v4.pkl')
            # This ensures we use the exact features used during training
            self.features = self.model.feature_names_in_
            print(f"[*] SUCCESS: Model '{r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\ids_random_forest_v4.pkl'}' loaded.")
            print(f"[*] Monitoring for OSPF/EIGRP/ICMP anomalies...")
        except Exception as e:
            print(f"[!] Critical Error loading model: {e}")
            sys.exit(1)

    def on_expire(self, flow):
        """Processes each flow once it finishes or times out."""

        if flow.bidirectional_packets < 3:
            # Silently skip single/dual packets to avoid R6 false positives
            return


        # Pull the features the model expects from the live flow
        flow_data = {feat: getattr(flow, feat, 0) for feat in self.features}
        X_live = pd.DataFrame([flow_data])

        # Ensure numeric format (crucial for RF models)
        X_live = X_live.apply(pd.to_numeric, errors='coerce').fillna(0)

        # Predict: 0 = Normal, 1 = Attack
        prediction = self.model.predict(X_live)[0]

        if prediction == 1:
            self.trigger_alert(flow)
        else:
            # Heartbeat: A dot represents a 'Normal' flow cleared by the IDS
            print(".", end="", flush=True)

            # Debug: See the metrics for the flow being analyzed
        print(f"Checking {flow.src_ip} | Pkts: {flow.bidirectional_packets} | PIAT: {flow.bidirectional_mean_piat_ms:.4f}")

        flow_data = {feat: getattr(flow, feat, 0) for feat in self.features}


    def trigger_alert(self, flow):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        proto = "OSPF" if flow.protocol == 89 else "EIGRP" if flow.protocol == 88 else "ICMP/Other"

        print(f"\n" + "!" * 60)
        print(f"  [!!!] ALERT: MALICIOUS {proto} ACTIVITY [!!!]")
        print(f"  Time:       {timestamp}")
        print(f"  Source:     {flow.src_ip} --> {flow.dst_ip}")
        print(f"  Avg PIAT:   {flow.bidirectional_mean_piat_ms:.2f} ms")
        print(f"  Pkt Count:  {flow.bidirectional_packets}")
        print("!" * 60 + "\n")


# 2. Main Execution (Windows Host)
if __name__ == "__main__":
    # Update this to your 'Ethernet 4' Loopback Adapter GUID
    target_interface = r"\Device\NPF_{B22E4023-9B1E-421F-9C41-2F392B025C6F}"

    # Initialize the detector
    detector = IDSDetector(model_path=r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\ids_random_forest_v4.pkl')

    print(f"[*] Initializing Sniffer on {target_interface}...")

    try:
        streamer = NFStreamer(
            source=target_interface,
            statistical_analysis=True,
            # CRITICAL FIXES BELOW:
            active_timeout=1,  # Forces the Kali flood to 'expire' every 1 second
            idle_timeout=1,  # Don't wait 5 seconds to analyze
            bpf_filter="proto 89",  # Ignore SNMP/CDP noise entirely
            udps=[detector]
        )

        for flow in streamer:
            pass

    except PermissionError:
        print("\n[!] ACCESS DENIED: You MUST run this terminal as ADMINISTRATOR.")
    except KeyboardInterrupt:
        print("\n[*] IDS stopping...")