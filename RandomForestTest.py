import pandas as pd
import joblib
from nfstream import NFStreamer


def predict_threats(pcap_file, model_path):
    # 1. Load the trained model
    model = joblib.load(r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\ids_random_forest_v4.pkl')
    print(f"[*] Model Loaded: {r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\ids_random_forest_v4.pkl'}")

    # 2. Extract flows from the new PCAP
    # We use the same idle_timeout=10 to match how the model was trained
    print(f"[*] Extracting features from {r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps\RandomForestTest.pcap'}...")
    streamer = NFStreamer(source=r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps\RandomForestTest.pcap', statistical_analysis=True, idle_timeout=10)
    df = streamer.to_pandas()

    if df.empty:
        print("[!] No flows found in PCAP.")
        return

    # 3. Preprocess to match training features
    # These are the columns the model expects (must match exactly)
    features = model.feature_names_in_

    # Fill missing columns and ensure numeric type
    X = df.reindex(columns=features, fill_value=0)
    X = X.apply(pd.to_numeric, errors='coerce').fillna(0)

    # 4. Predict
    predictions = model.predict(X)
    df['prediction'] = predictions

    # 5. Generate Report
    threats = df[df['prediction'] == 1]

    print("\n" + "=" * 30)
    print("      IDS THREAT REPORT      ")
    print("=" * 30)
    print(f"Total Flows Scanned: {len(df)}")
    print(f"Malicious Flows Detected: {len(threats)}")
    print("-" * 30)

    if not threats.empty:
        # Show the most dangerous threats (Source IP and Protocol)
        print("Top Detected Threats:")
        report = threats[['src_ip', 'dst_ip', 'protocol', 'bidirectional_packets']].head(10)
        print(report.to_string(index=False))
    else:
        print("[+] No threats detected. Network is clean.")


if __name__ == "__main__":
    # Point this to a NEW pcap you just captured in GNS3
    predict_threats('pcaps/new_test_capture.pcap', 'ids_random_forest_v4.pkl')