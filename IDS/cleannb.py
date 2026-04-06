import pandas as pd

# 1. Load the dataset
df = pd.read_csv('NBDataset.csv')

# 2. Filter out "Fake Attacks"
# Keep only Label 1 rows that actually LOOK like a flood (High packet count, Low PIAT)
clean_attacks = df[(df['Label'] == 1) & (df['Packet_Count'] > 50) & (df['Avg_PIAT'] < 100)]

# 3. Keep all normal traffic
normal_traffic = df[df['Label'] == 0]

# 4. Oversample the TCP attacks
# Since there are fewer TCP attack rows, we repeat them to give them a "louder" voice
tcp_attacks = clean_attacks[clean_attacks['Protocol'] == 6]
oversampled_tcp = pd.concat([tcp_attacks] * 15)

# 5. Create the new Balanced Dataset
balanced_df = pd.concat([normal_traffic, clean_attacks, oversampled_tcp])

# Save it as the new training source
balanced_df.to_csv('NBDataset_Balanced.csv', index=False)
print(f"Created Balanced Dataset with {len(balanced_df)} rows.")