import csv
from scapy.all import PcapReader, IP
import sys
import os

def extract_flows_from_pcap(pcap_filepath, output_csv_filepath, label):
    print(f"Reading {pcap_filepath} and extracting 2-second flows...")

    headers = ['Protocol', 'Packet_Count', 'Total_Bytes', 'Avg_PIAT', 'Label']
    flows = {}
    WINDOW_SIZE = 2.0
    flow_count = 0

    with open(output_csv_filepath, mode='a', newline='') as csv_file:
        writer = csv.writer(csv_file)

        # Write headers if the file is empty
        if csv_file.tell() == 0:
            writer.writerow(headers)

        with PcapReader(pcap_filepath) as pcap_reader:
            for pkt in pcap_reader:
                if IP in pkt:
                    src_ip = pkt[IP].src
                    dst_ip = pkt[IP].dst
                    proto = pkt[IP].proto
                    length = len(pkt[IP])

                    # Use the packet's actual recorded timestamp
                    current_time = float(pkt.time)
                    flow_key = (src_ip, dst_ip, proto)

                    if flow_key not in flows:
                        flows[flow_key] = {
                            'start_time': current_time,
                            'last_time': current_time,
                            'packet_count': 1,
                            'total_bytes': length,
                            'piat_sum': 0.0
                        }
                        continue

                    # Update flow stats
                    piat = (current_time - flows[flow_key]['last_time']) * 1000  # Convert to ms
                    flows[flow_key]['piat_sum'] += piat
                    flows[flow_key]['last_time'] = current_time
                    flows[flow_key]['packet_count'] += 1
                    flows[flow_key]['total_bytes'] += length

                    # Check if 2-second window expired
                    if current_time - flows[flow_key]['start_time'] >= WINDOW_SIZE:
                        avg_piat = flows[flow_key]['piat_sum'] / (flows[flow_key]['packet_count'] - 1)

                        # Write the extracted flow to the CSV
                        writer.writerow(
                            [proto, flows[flow_key]['packet_count'], flows[flow_key]['total_bytes'], avg_piat, label])
                        flow_count += 1

                        # Reset the flow
                        del flows[flow_key]

        # Flush any remaining flows that didn't hit the full 2 seconds before the PCAP ended
        for flow_key, data in flows.items():
            if data['packet_count'] > 1:  # Only save flows with more than 1 packet (needed for PIAT)
                avg_piat = data['piat_sum'] / (data['packet_count'] - 1)
                writer.writerow([flow_key[2], data['packet_count'], data['total_bytes'], avg_piat, label])
                flow_count += 1

    print(f"Extraction complete! Saved {flow_count} flows to {output_csv_filepath}.")


# --- Execution Workflow ---
if __name__ == "__main__":
    pcap_folder = r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps'
    output_file = "NBDataset.csv"

    # Ensure the directory exists
    if not os.path.isdir(pcap_folder):
        print(f"[!] Error: {pcap_folder} is not a valid directory.")
        sys.exit(1)

    # Loop through all files in the folder
    for filename in os.listdir(pcap_folder):
        if filename.endswith(".pcap") or filename.endswith(".pcapng"):
            full_path = os.path.join(pcap_folder, filename)

            # Use label=1 if 'flood' or 'attack' is in the filename, else label=0
            current_label = 1 if "flood" in filename.lower() or "attack" in filename.lower() else 0

            print(f"[*] Processing {filename} with Label: {current_label}")
            extract_flows_from_pcap(full_path, output_file, label=current_label)

    print(f"\n[SUCCESS] All files processed. Dataset saved to {output_file}")