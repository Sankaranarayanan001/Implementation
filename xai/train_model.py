import os
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from lightgbm import LGBMClassifier
from sklearn.metrics import classification_report

os.makedirs('model', exist_ok=True)   # creates the folder if it doesn't exist

data = pd.read_csv('train.csv')

selected_features = ['ram', 'battery_power', 'px_width', 'px_height', 'int_memory',
                      'sc_w', 'pc', 'three_g', 'sc_h', 'fc']

X = data[selected_features]
y = data['price_range']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

model = LGBMClassifier(n_estimators=200, random_state=42,verbose=-1)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
print(classification_report(y_test, y_pred))

joblib.dump(model, 'model/lgbm_model.pkl')
X_train.to_csv('model/X_train.csv', index=False)
X_test.to_csv('model/X_test.csv', index=False)
y_test.to_csv('model/y_test.csv', index=False)
y_train.to_csv('model/y_train.csv', index=False)
print("Model and data saved.")
