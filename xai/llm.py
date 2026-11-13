import requests

def get_llm_explanation(prediction_label, lime_result):
    """Local explanation: turns LIME result into plain English."""
    prompt = f"""
    A machine learning model classified a mobile phone's price range as "{prediction_label}".

    LIME explanation (local, per-feature contribution): {lime_result}

    In one short paragraph, explain in plain English why the phone was classified this way,
    based on these contributing features.
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:3b", "prompt": prompt, "stream": False},
            timeout=30
        )
        return response.json()["response"], "ok"
    except Exception as e:
        return f"LLM explanation unavailable: {str(e)}", "error"


def get_llm_global_explanation(insights_result):
    """Global explanation: turns SHAP global feature importance into plain English."""
    prompt = f"""
    This is the global feature importance (mean absolute SHAP value) of a machine learning model
    that predicts mobile phone price range (Low, Medium, High, Very High):

    {insights_result}

    In one short paragraph, explain in plain English which features matter most overall
    for this model's predictions, and which features barely matter.
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:3b", "prompt": prompt, "stream": False},
            timeout=30
        )
        return response.json()["response"], "ok"
    except Exception as e:
        return f"LLM explanation unavailable: {str(e)}", "error"