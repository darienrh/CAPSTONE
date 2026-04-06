import pandas as pd
import joblib
from nfstream import NFStreamer


def live_test_naive_bayes(pcap_file, model_path, scaler_path):
    # 1. Load the Model and the Scaler
    # Naive Bayes is very sensitive to scaling, so we must use the same scaler from training
    nb_model = joblib.load(r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\naive_bayes_model.pkl')
    scaler = joblib.load(r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\scaler.pkl')
    print(f"[*] Naive Bayes Model & Scaler Loaded.")

    # 2. Extract features from the NEW PCAP
    print(f"[*] Analyzing: {r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps\RandomForestTest.pcap'}...")
    streamer = NFStreamer(source=r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps\RandomForestTest.pcap', statistical_analysis=True, idle_timeout=10)
    df = streamer.to_pandas()

    if df.empty:
        print("[!] No traffic found in PCAP.")
        return

    # 3. Match the features used during training
    features = [
        'protocol', 'bidirectional_packets', 'bidirectional_bytes',
        'src2dst_mean_piat_ms', 'dst2src_mean_piat_ms',
        'bidirectional_mean_ps', 'src2dst_min_ps', 'bidirectional_max_piat_ms'
    ]

    X = df[features].fillna(0)

    # 4. Scale the data
    X_scaled = scaler.transform(X)

    # 5. Predict
    predictions = nb_model.predict(X_scaled)
    df['prediction'] = predictions

    # 6. Results
    threats = df[df['prediction'] == 1]
    print("\n" + "=" * 30)
    print("   NAIVE BAYES TEST REPORT   ")
    print("=" * 30)
    print(f"Total Flows: {len(df)}")
    print(f"Attacks Found: {len(threats)}")

    if not threats.empty:
        print("\nDetected Attack Sources:")
        print(threats[['src_ip', 'dst_ip', 'protocol']].drop_duplicates())
    else:
        print("\n[+] No attacks detected by Naive Bayes.")


if __name__ == "__main__":
    # Path to your fresh capture
    test_pcap = r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps\R6-S4.pcap'
    live_test_naive_bayes(test_pcap, 'naive_bayes_model.pkl', 'scaler.pkl')