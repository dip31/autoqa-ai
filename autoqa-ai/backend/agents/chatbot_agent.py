import os
import time
import requests
from dotenv import load_dotenv

SYSTEM_PROMPT = """You are AutoQA Assistant, an expert AI chatbot for the AutoQA AI platform.
You help users with:
- Writing and reviewing test cases
- Code quality and best practices
- QA automation strategies
- Bug risk analysis and prevention
- Understanding test coverage
- Website testing approaches
- Interpreting reports and scores

Be concise, helpful, and practical. Format responses clearly.
If asked about something unrelated to QA/software testing, politely redirect to QA topics."""

MODELS = [
    "gemini-flash-lite-latest",  # confirmed working
    "gemini-flash-latest",
]

def _try_model(api_key: str, model: str, payload: dict) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    res = requests.post(url, json=payload, timeout=45)
    res.raise_for_status()
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]

def chat(messages: list) -> str:
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")

    contents = [
        {"role": "user" if m["role"] == "user" else "model",
         "parts": [{"text": m["content"]}]}
        for m in messages
    ]

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}
    }

    errors = []
    for model in MODELS:
        try:
            return _try_model(api_key, model, payload)
        except Exception as e:
            errors.append(f"{model}: {e}")
            time.sleep(1)   # brief pause before next model
            continue

    raise Exception(f"All Gemini models failed. Errors: {' | '.join(errors)}")
