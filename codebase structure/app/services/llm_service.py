import ollama
from app.core import config

client = ollama.Client(host=config.OLLAMA_HOST)


def describe_image(prompt: str, image_bytes: bytes) -> str:
    response = client.chat(
        model=config.OLLAMA_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [image_bytes],
            }
        ],
    )
    return response["message"]["content"]