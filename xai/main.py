from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd

from xai import predict_with_explanation, get_global_insights

app = FastAPI(
    title="Explainable Mobile Price Classifier",
    description="LightGBM prediction + LIME (local) + SHAP (global) feature explanations."
)


class PhoneInput(BaseModel):
    ram: float
    battery_power: float
    px_width: float
    px_height: float
    int_memory: float
    sc_w: float
    pc: float
    three_g: float
    sc_h: float
    fc: float


@app.post("/predict")
def predict_endpoint(input_data: PhoneInput):
    df = pd.DataFrame([input_data.dict()])
    return predict_with_explanation(df)


@app.get("/model-insights")
def model_insights():
    return get_global_insights()