import joblib
import pandas as pd
import numpy as np
from nfstream import NFPlugin, NFStreamer
import datetime
import sys
import requests

# Flask API endpoint
FLASK_URL = "http://192.168.231.10:5000/api/ids/alert"

def post_alert(alert_type, protocol, src_ip, dst_ip, details):
    try:
        requests.post(FLASK_URL, json={
            'attack_type': alert_type,
            'protocol': protocol,
            'source_ip': src_ip,
            'target_device': dst_ip,
            'severity': 'high',
            'details': details
        }, timeout=2)
    except Exception:
        pass

# --- PLUGIN 1: Random Forest (OSPF/EIGRP/ICMP) ---
class RF_Detector(NFPlugin):
    def __init__(self, model_path):
        super().__init__()
        try:
            self.model = joblib.load(r'D:\school_code\Capstone_RuleBasedAI\IDS\ids_random_forest_v4.pkl')
            self.features = self.model.feature_names_in_
            print(f"[*] RF Model loaded. Monitoring OSPF/EIGRP/ICMP...")
        except Exception as e:
            print(f"[!] Error loading RF Model: {e}")
            sys.exit(1)

    def on_expire(self, flow):
        if flow.bidirectional_packets < 3:
            return

        # Extract features and force to numeric (Same as your working OSPF script)
        flow_data = {feat: getattr(flow, feat, 0) for feat in self.features}
        X_live = pd.DataFrame([flow_data])
        X_live = X_live.apply(pd.to_numeric, errors='coerce').fillna(0)

        try:
            prediction = self.model.predict(X_live)[0]
            if prediction == 1:
                self.trigger_alert(flow)
        except Exception:
            pass

    def trigger_alert(self, flow):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        proto = "OSPF" if flow.protocol == 89 else "EIGRP" if flow.protocol == 88 else "ICMP/Other"
        print(f"\n" + "!" * 60)
        print(f"  [RF-ALERT] MALICIOUS {proto} ACTIVITY DETECTED")
        print(f"  Source:     {flow.src_ip} --> {flow.dst_ip}")
        print(f"  Pkt Count:  {flow.bidirectional_packets}")
        print("!" * 60 + "\n")
        
        # Send alert to Flask
        post_alert('ml_detection', proto, flow.src_ip, flow.dst_ip,
                   f"RF model detected malicious {proto} from {flow.src_ip}")


# --- PLUGIN 2: Naive Bayes (TCP SYN Flood) ---
class NB_Detector(NFPlugin):
    def __init__(self, model_path, scaler_path):
        super().__init__()
        try:
            self.model = joblib.load(r'D:\school_code\Capstone_RuleBasedAI\IDS\naive_bayes_model.pkl')
            self.scaler = joblib.load(r'D:\school_code\Capstone_RuleBasedAI\IDS\scaler.pkl')
            self.features = ['Protocol', 'Packet_Count', 'Total_Bytes', 'Avg_PIAT']
            print(f"[*] NB Model & Scaler loaded. Monitoring TCP Floods...")
        except Exception as e:
            print(f"[!] Error loading NB Model: {e}")
            sys.exit(1)

    def on_expire(self, flow):
        if flow.bidirectional_packets < 5:
            return

        # NB only cares about TCP and OSPF based on your dataset
        if flow.protocol not in [6, 89]:
            return

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
        except:
            pass

    def trigger_alert(self, flow):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        proto_name = "TCP" if flow.protocol == 6 else "OSPF" if flow.protocol == 89 else f"PROTO_{flow.protocol}"
        print(f"\n" + "*" * 60)
        print(f"  [NB-ALERT] {proto_name} ANOMALY DETECTED")
        print(f"  Source:     {flow.src_ip} --> {flow.dst_ip}")
        print(f"  Avg PIAT:   {flow.bidirectional_mean_piat_ms:.4f} ms")
        print("*" * 60 + "\n")
        
        # Send alert to Flask
        post_alert('ml_detection', proto_name, flow.src_ip, flow.dst_ip,
                   f"NB model detected {proto_name} anomaly from {flow.src_ip}")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    target_interface = r"\Device\NPF_{958B06FE-EB01-42BE-BF43-D2043464D5D1}"

    # Initialize both detectors
    rf_inst = RF_Detector(r'D:\school_code\Capstone_RuleBasedAI\IDS\ids_random_forest_v4.pkl')
    nb_inst = NB_Detector(
        model_path=r'D:\school_code\Capstone_RuleBasedAI\IDS\naive_bayes_model.pkl',
        scaler_path=r'D:\school_code\Capstone_RuleBasedAI\IDS\scaler.pkl'
    )

    print(f"[*] Hybrid IDS Active on {target_interface}...")

    try:
        streamer = NFStreamer(
            source=target_interface,
            statistical_analysis=True,
            active_timeout=1,
            idle_timeout=1,
            # Broaden filter to catch everything both models need
            bpf_filter="tcp or proto 89 or proto 88 or icmp",
            udps=[rf_inst, nb_inst]
        )

        for flow in streamer:
            # Simple heartbeat
            if flow.protocol == 89:
                print("o", end="", flush=True) # 'o' for OSPF heartbeat
            elif flow.protocol == 6:
                print("t", end="", flush=True) # 't' for TCP heartbeat

    except KeyboardInterrupt:
        print("\n[*] Stopping Hybrid IDS...")