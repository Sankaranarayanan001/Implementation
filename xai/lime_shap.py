import joblib
import pandas as pd
import numpy as np
import shap
import lime.lime_tabular

model = joblib.load('model/lgbm_model.pkl')
X_train = pd.read_csv('model/X_train.csv')
X_test = pd.read_csv('model/X_test.csv')

feature_names = X_train.columns.tolist()
class_names = ['Low', 'Medium', 'High', 'Very High']

shap_explainer = shap.TreeExplainer(model)
lime_explainer = lime.lime_tabular.LimeTabularExplainer(
    training_data=X_train.values,
    feature_names=feature_names,
    class_names=class_names,
    mode='classification'
)


def get_lime_explanation(input_df: pd.DataFrame):
    exp = lime_explainer.explain_instance(
        data_row=input_df.values[0],
        predict_fn=model.predict_proba,
        num_features=10
    )
    return [{"feature": f, "weight": round(w, 4)} for f, w in exp.as_list()]


def get_shap_global_insights():
    shap_values = shap_explainer.shap_values(X_test)

    if isinstance(shap_values, list):
        mean_abs_shap = np.mean([np.abs(sv) for sv in shap_values], axis=0).mean(axis=0)
    else:
        mean_abs_shap = np.abs(shap_values).mean(axis=(0, 2))

    importance = pd.DataFrame({
        "feature": feature_names,
        "mean_abs_shap": mean_abs_shap
    }).sort_values("mean_abs_shap", ascending=False)

    return importance.to_dict(orient="records")


def predict(input_df: pd.DataFrame):
    input_df = input_df[feature_names]
    prediction = int(model.predict(input_df)[0])
    probabilities = model.predict_proba(input_df)[0]
    return prediction, probabilities