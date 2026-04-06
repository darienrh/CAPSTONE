import csv
import os
from scapy.all import PcapReader, IP, TCP, UDP


def extract_pcap_features_to_match_project():
    pcap_folder = r'C:\Users\srsm3\PycharmProjects\CapstoneIDSML\pcaps'
    output_csv = "combined_network_data_Naive.csv"
    headers = ['Packet_Length', 'Protocol', 'Src_Port', 'Dst_Port', 'TCP_Flags', 'label']

    with open(output_csv, mode='w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)

        files = [f for f in os.listdir(pcap_folder) if f.endswith(('.pcap', '.pcapng'))]

        for filename in files:
            file_path = os.path.join(pcap_folder, filename)
            print(f"Scapy processing: {filename}")

            with PcapReader(file_path) as pcap_reader:
                for pkt in pcap_reader:
                    if IP in pkt:
                        pkt_length = len(pkt[IP])
                        protocol = pkt[IP].proto
                        src_port = 0
                        dst_port = 0
                        tcp_flags = 0

                        if TCP in pkt:
                            src_port = pkt[TCP].sport
                            dst_port = pkt[TCP].dport
                            tcp_flags = int(pkt[TCP].flags)
                        elif UDP in pkt:
                            src_port = pkt[UDP].sport
                            dst_port = pkt[UDP].dport

                        # --- Apply our Behavioral Labeling ---
                        label = 0
                        # OSPF Attack (Protocol 89)
                        if protocol == 89:
                            label = 1
                        # ICMP Attack (Protocol 1)
                        elif protocol == 1:
                            label = 1

                        writer.writerow([pkt_length, protocol, src_port, dst_port, tcp_flags, label])

    print(f"Basic feature extraction complete: {output_csv}")


if __name__ == "__main__":
    extract_pcap_features_to_match_project()