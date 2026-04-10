import requests, os, base64
from dotenv import load_dotenv
load_dotenv(override=True)

key = os.getenv("GEMINI_API_KEY")

# Test image generation model
models = ["gemini-2.0-flash-preview-image-generation", "imagen-3.0-generate-002"]

payload = {
    "contents": [{"role": "user", "parts": [{"text": "Generate a simple QA report chart image"}]}],
    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
}

for m in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
    r = requests.post(url, json=payload, timeout=30)
    print(f"{m}: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for p in parts:
            if "inlineData" in p:
                print(f"  -> Got image! mime: {p['inlineData']['mimeType']}, size: {len(p['inlineData']['data'])} chars")
            elif "text" in p:
                print(f"  -> Got text: {p['text'][:100]}")
    else:
        print(f"  -> {r.text[:200]}")
