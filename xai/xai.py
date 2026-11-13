import pandas as pd
from lime_shap import predict, get_lime_explanation, get_shap_global_insights, class_names
from llm import get_llm_explanation, get_llm_global_explanation


def predict_with_explanation(input_df: pd.DataFrame):
    prediction, probabilities = predict(input_df)
    prediction_label = class_names[prediction]

    lime_result = get_lime_explanation(input_df)
    explanation_text, llm_status = get_llm_explanation(prediction_label, lime_result[:5])

    return {
        "prediction": prediction_label,
        "confidence": round(float(max(probabilities)), 4),
        "lime_explanation": lime_result,
        "explanation": explanation_text,
        "llm_status": llm_status
    }


def get_global_insights():
    insights = get_shap_global_insights()
    explanation_text, llm_status = get_llm_global_explanation(insights[:5])

    return {
        "feature_importance": insights,
        "explanation": explanation_text,
        "llm_status": llm_status
    }