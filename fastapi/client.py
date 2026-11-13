import httpx

API_URL = "http://127.0.0.1:8000/analyze-image"


def main():
    print("=== Image Q&A Client ===\n")

    image_path = input("Enter image path (e.g. dog.jpg): ").strip()
    question = input("Enter your question: ").strip()

    print("\n[Client] Sending request to FastAPI server...")

    with open(image_path, "rb") as f:
        files = {"image": (image_path, f, "image/jpeg")}
        data = {"question": question}

        response = httpx.post(API_URL, files=files, data=data, timeout=120)

    print(f"[Client] Response status: {response.status_code}\n")

    if response.status_code == 200:
        result = response.json()
        print("=== Result ===")
        print(f"Question : {result['question']}")
        print(f"Filename : {result['filename']}")
        print(f"Answer   : {result['answer']}")
    else:
        print("=== Error ===")
        print(response.json())


if __name__ == "__main__":
    main()