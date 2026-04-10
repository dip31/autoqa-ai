import requests, time, os
from dotenv import load_dotenv
load_dotenv(override=True)

key = os.getenv("GEMINI_API_KEY")
models = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
payload = {
    "contents": [{"role": "user", "parts": [{"text": "Say OK"}]}],
    "generationConfig": {"maxOutputTokens": 10}
}

for m in models:
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}",
            json=payload, timeout=15
        )
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"OK  {m}: {text}")
        else:
            print(f"FAIL {r.status_code}  {m}: {r.text[:80]}")
    except Exception as e:
        print(f"ERR {m}: {e}")
    time.sleep(2)
