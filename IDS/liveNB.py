import joblib
import pandas as pd
import numpy as np
from nfstream import NFPlugin, NFStreamer
import datetime
import sys


class NB_TCP_Detector(NFPlugin):
    def __init__(self, model_path, scaler_path):
        super().__init__()
        try:
            # Load model and scaler from your project directory
            self.model = joblib.load(r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\naive_bayes_model.pkl')
            self.scaler = joblib.load(r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\scaler.pkl')

            # CRITICAL: These must match the 4 headers in your NBDataset.csv exactly
            self.features = ['Protocol', 'Packet_Count', 'Total_Bytes', 'Avg_PIAT']

            print(f"[*] NB Model & Scaler Loaded.")
            print(f"[*] Monitoring for TCP/OSPF anomalies using features: {self.features}")
        except Exception as e:
            print(f"[!] Error loading files: {e}")
            sys.exit(1)

    def on_expire(self, flow):
        # 1. Threshold: Ignore small flows (like OSPF Hellos)
        if flow.bidirectional_packets < 5:
            return

        # 2. Match the 4 features in NBDataset_Balanced.csv
        X_live = pd.DataFrame([{
            'Protocol': float(flow.protocol),
            'Packet_Count': float(flow.bidirectional_packets),
            'Total_Bytes': float(flow.bidirectional_bytes),
            'Avg_PIAT': float(flow.bidirectional_mean_piat_ms)
        }])

        try:
            X_scaled = self.scaler.transform(X_live)
            prediction = self.model.predict(X_scaled)[0]

            if prediction == 1:
                self.trigger_alert(flow)
            else:
                print(".", end="", flush=True)
        except Exception as e:
            print(f"Error: {e}")

    def trigger_alert(self, flow):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        # Identify protocol for the alert message
        proto_name = "TCP" if flow.protocol == 6 else "OSPF" if flow.protocol == 89 else f"PROTO_{flow.protocol}"

        print(f"\n" + "!" * 60)
        print(f"  [NB-ALERT] MALICIOUS {proto_name} ACTIVITY DETECTED")
        print(f"  Time:       {timestamp}")
        print(f"  Source:     {flow.src_ip} --> {flow.dst_ip}")
        print(f"  Avg PIAT:   {flow.bidirectional_mean_piat_ms:.4f} ms")
        print(f"  Pkt Count:  {flow.bidirectional_packets}")
        print("!" * 60 + "\n")


if __name__ == "__main__":
    # Your Loopback Adapter GUID
    target_interface = r"\Device\NPF_{B22E4023-9B1E-421F-9C41-2F392B025C6F}"

    # Path to your saved files
    model_file = r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\naive_bayes_model.pkl'
    scaler_file = r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\scaler.pkl'

    detector = NB_TCP_Detector(model_path=model_file, scaler_path=scaler_file)

    print(f"[*] Initializing Sniffer on {target_interface}...")

    try:
        streamer = NFStreamer(
            source=target_interface,
            statistical_analysis=True,
            active_timeout=1,  # This "breaks up" the continuous flood for the model
            idle_timeout=1,
            bpf_filter="tcp or proto 89",
            udps=[detector]
        )

        # This loop keeps the script running and processing flows
        for flow in streamer:
            pass

    except PermissionError:
        print("\n[!] ACCESS DENIED: You MUST run PyCharm/Terminal as ADMINISTRATOR.")
    except KeyboardInterrupt:
        print("\n[*] IDS stopping...")
    except Exception as e:
        print(f"\n[!] Unexpected Error: {e}")