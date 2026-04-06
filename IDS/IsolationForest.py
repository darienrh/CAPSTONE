import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix

#1 load in the combined dataset
df = pd.read_csv('combined_network_data.csv')

#2 drop certain columns so the IDS looks at behaviour and not just specific addresses
cols_drop = ['id', 'expiration_id', 'src_ip', 'dst_ip', 'src_mac', 'dst_mac', 'src_oui', 'dst_oui', 'source_file',
             'requested_server_name', 'client_fingerprint', 'server_fingerprint', 'user_agent', 'content_type']
X = df.drop(columns=cols_drop).fillna(0)


#encode text into numbers for progrgam to understand
le = LabelEncoder()
X['application_name'] = le.fit_transform(X['application_name'].astype(str))
X['application_category_name'] = le.fit_transform(X['application_category_name'].astype(str))

#3 Train model
iso_forest = IsolationForest(contamination=0.44, random_state=42)

#Predict: 1 is Benign, -1 is Anomaly
df['anomaly_score'] = iso_forest.fit_predict(X)

df['iso_pred'] = df['anomaly_score'].map({1: 0, -1: 1})

#4 attacks evaluated
df['actual_label'] = df['source_file'].apply(lambda x: 1 if 'KALI' in x.upper() else 0)

print("--- Isolation Forest Results ---")
print(classification_report(df['actual_label'], df['iso_pred']))


#5 graph results
plt.figure(figsize=(10, 5))
sns.histplot(iso_forest.decision_function(X), bins=50, kde=True)
plt.title('Histogram of Isolation Forest (Lower = More suspicious')
plt.axvline(x=0, color='r', linestyle='--')
plt.show()


