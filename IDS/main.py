import os
import pandas as pd
from nfstream import NFStreamer


def process_all_pcaps():
    pcap_folder = r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps'
    output_file = "combined_network_data_v4.csv"
    all_flows = []

    if not os.path.exists(pcap_folder):
        print(f"Error: {pcap_folder} not found.")
        return

    files = [f for f in os.listdir(pcap_folder) if f.endswith(('.pcap', '.pcapng'))]
    print(f"Found {len(files)} files. Starting processing...")

    for filename in files:
        file_path = os.path.join(pcap_folder, filename)
        print(f"Processing: {filename}...")

        try:
            # FIX 1: Add idle_timeout=10 to break long attacks into multiple flows
            # This turns 1 giant attack flow into many 10-second segments
            streamer = NFStreamer(source=file_path, statistical_analysis=True, idle_timeout=10)
            df = streamer.to_pandas()

            df['source_file'] = filename
            df['label'] = 0
            fname_upper = filename.upper()


            #check every file for the attack behavior
            ospf_attack = (df['protocol'] == 89) & (df['bidirectional_mean_piat_ms'] < 1000)
            icmp_attack = (df['protocol'] == 1) & (df['bidirectional_mean_piat_ms'] < 100)

            df.loc[ospf_attack | icmp_attack, 'label'] = 1

            print(f"   -> Flows: {len(df)} | Attacks (Label 1): {df['label'].sum()}")

            # FIX 2: Only append ONCE per file
            all_flows.append(df)

        except Exception as e:
            print(f"Could not process {filename}: {e}")

    if all_flows:
        master_df = pd.concat(all_flows, ignore_index=True)
        master_df.to_csv(output_file, index=False)
        print("-" * 30)
        print(f"Final Label Distribution:\n{master_df['label'].value_counts()}")
    else:
        print("No data collected.")


if __name__ == '__main__':
    process_all_pcaps()