import re
import requests
from langchain_core.tools import tool
from ddgs import DDGS

# ---------- Calculator tool ----------
MAX_EXPRESSION_LENGTH = 64
MAX_LITERAL_DIGITS = 15

def validation_error(sanitized: str):
    if len(sanitized) > MAX_EXPRESSION_LENGTH:
        return f"Expression too long (max {MAX_EXPRESSION_LENGTH} characters)."
    if "**" in sanitized:
        return "Exponentiation (**) is not allowed."
    if not re.fullmatch(r"[\d+\-*/().]+", sanitized):
        return "Only numbers and +, -, *, /, (, ) are allowed."
    for match in re.finditer(r"\d+", sanitized):
        if len(match.group()) > MAX_LITERAL_DIGITS:
            return f"Number literals may contain at most {MAX_LITERAL_DIGITS} digits."
    return None


@tool
def calculate(expression: str) -> dict:
    """Evaluate a mathematical expression. Supports +, -, *, /, and parentheses."""
    sanitized = expression.replace(" ", "")
    error = validation_error(sanitized)
    if error:
        return {"expression": expression, "error": f'Invalid expression: "{expression}". {error}'}
    try:
        result = eval(sanitized)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


# ---------- Weather tool ----------
@tool
def get_weather(city: str) -> dict:
    """Get the current weather for a given city."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1}
        ).json()
        if "results" not in geo:
            return {"city": city, "error": "City not found."}
        lat = geo["results"][0]["latitude"]
        lon = geo["results"][0]["longitude"]
        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": True}
        ).json()
        cw = weather["current_weather"]
        return {"city": city, "temperature": cw["temperature"], "windspeed": cw["windspeed"], "unit": "celsius"}
    except Exception as e:
        return {"city": city, "error": str(e)}


# ---------- Search web tool ----------
@tool
def search_web(query: str) -> dict:
    """Search the web for information about a topic."""
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=3))
        results = [
            {"title": r["title"], "url": r["href"], "snippet": r["body"][:200]}
            for r in raw_results
        ]
        return {"query": query, "results": results}
    except Exception as e:
        return {"query": query, "error": str(e)}


# Exported list + lookup dict, used by langgraph_setup.py
tools = [calculate, get_weather, search_web]
tools_by_name = {t.name: t for t in tools}