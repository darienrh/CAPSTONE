import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.preprocessing import StandardScaler
import joblib

# 1. Load the dataset
df = pd.read_csv('NBDataset_Balanced.csv')
print(f"[*] Total rows loaded: {len(df)}")

# 2. Data Balancing (CRITICAL for Naive Bayes)
# Naive Bayes struggles if one class (Normal) is 10x larger than the other (Attack)
normal_df = df[df['Label'] == 0]
attack_df = df[df['Label'] == 1]

# If you have very few TCP attacks, we oversample them to give them more weight
tcp_attacks = attack_df[attack_df['Protocol'] == 6]
if len(tcp_attacks) > 0:
    attack_df = pd.concat([attack_df, pd.concat([tcp_attacks] * 5)])

df_balanced = pd.concat([normal_df, attack_df])
print(f"[*] Balanced dataset size: {len(df_balanced)} (Attacks: {len(attack_df)})")

# 3. Feature Selection
# Must match your extractor: ['Protocol', 'Packet_Count', 'Total_Bytes', 'Avg_PIAT']
features = ['Protocol', 'Packet_Count', 'Total_Bytes', 'Avg_PIAT']
X = df_balanced[features].fillna(0)
y = df_balanced['Label']

# 4. Scaling
# GaussianNB assumes features follow a normal distribution.
# Scaling Total_Bytes (large) and Avg_PIAT (small) to the same range is essential.
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 5. Split
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.3, random_state=42, stratify=y
)

# 6. Train the Gaussian Naive Bayes Model
print(f"[*] Training GaussianNB on {len(X_train)} samples...")
nb_model = GaussianNB()
nb_model.fit(X_train, y_train)

# 7. Evaluate
y_pred = nb_model.predict(X_test)
print("\n" + "="*20 + " NAIVE BAYES REPORT " + "="*20)
print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
print("\nConfusion Matrix:")
print(confusion_matrix(y_test, y_pred))
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

# 8. Save Files for Live Detection
joblib.dump(nb_model, 'naive_bayes_model.pkl')
joblib.dump(scaler, 'scaler.pkl')

print("\n[SUCCESS] Model and Scaler saved. You can now run liveNB.py.")