import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.preprocessing import LabelEncoder

# 1. Load the new v3 dataset
df = pd.read_csv('combined_network_data_v4.csv')

# 2. LABEL CHECK
# DO NOT overwrite the labels. We use the 'label' column already created
# by your preprocessing script.
print(f"Total rows in dataset: {len(df)}")
print(f"Label distribution (from CSV):\n{df['label'].value_counts()}")

# 3. PREPROCESSING
# Encode names we want to keep
le = LabelEncoder()
df['application_name'] = le.fit_transform(df['application_name'].astype(str))
df['application_category_name'] = le.fit_transform(df['application_category_name'].astype(str))

# Define identifying columns to drop (IPs, MACs, etc.)
# We also drop 'source_file' so the model doesn't just "memorize" filenames
cols_to_always_drop = [
    'id', 'expiration_id', 'src_ip', 'dst_ip', 'src_mac', 'dst_mac',
    'src_oui', 'dst_oui', 'source_file', 'dst_port', 'src_port'
]
df_temp = df.drop(columns=[c for c in cols_to_always_drop if c in df.columns])

# THE "BULLETPROOF" FIX:
# Select only numeric columns. This automatically removes 'requested_server_name'
# and other text strings that cause ValueErrors.
X = df_temp.select_dtypes(include=[np.number]).drop(columns=['label'], errors='ignore')
y = df['label']

# Handle any remaining NaN values
X = X.fillna(0)

# 4. SPLIT DATA
# Check if we have at least one attack flow before splitting
if len(y.unique()) < 2:
    print("\n[!] ERROR: No attack samples (label 1) found. Check your labeling logic in the processing script.")
else:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

    # 5. TRAIN
    print(f"\nTraining Random Forest on {len(X_train)} flows...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # 6. RESULTS
    y_pred = model.predict(X_test)
    print("\n" + "="*20 + " IDS REPORT " + "="*20)
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    # 7. FEATURE IMPORTANCE
    importances = pd.Series(model.feature_importances_, index=X.columns)
    print("\nTop 5 Behavioral Indicators:")
    print(importances.sort_values(ascending=False).head(5))


import joblib

# Save the model to a file
joblib.dump(model, 'ids_random_forest_v4.pkl')
# Save the label encoder (you'll need this for new data)
joblib.dump(le, 'label_encoder.pkl')

print("\n[SUCCESS] Model saved as 'ids_random_forest_v4.pkl'")

train_acc = model.score(X_train, y_train)
test_acc = model.score(X_test, y_test)

print(f"Training Accuracy: {train_acc:.4f}")
print(f"Testing Accuracy: {test_acc:.4f}")
print(f"Difference: {train_acc - test_acc:.4f}")
