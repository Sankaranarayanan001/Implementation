import base64
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llava"


async def ask_about_image(client: httpx.AsyncClient, image_bytes: bytes, question: str) -> str:
    """
    Sends an image + question to the Ollama vision model and returns the answer text.
    This is the ONLY function that knows Ollama exists — FastAPI code never talks
    to Ollama directly, it just calls this function.
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = await client.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": question,
            "images": [image_b64],
            "stream": False,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["response"]