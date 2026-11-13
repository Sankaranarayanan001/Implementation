import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("api-server")


@mcp.tool()
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


if __name__ == "__main__":
    mcp.run(transport="stdio")