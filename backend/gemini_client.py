import os
import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"

class GeminiClient:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key = api_key

    def generate(self, prompt: str, context: str = ""):
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"Context:\n{context}\n\nPrompt:\n{prompt}"}
                    ]
                }
            ]
        }

        response = requests.post(
            f"{GEMINI_ENDPOINT}?key={self.api_key}",
            json=payload,
            headers=headers
        )

        return response.json()