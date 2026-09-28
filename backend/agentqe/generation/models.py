import os
import json
import logging
from typing import List, Dict, Any, Optional
from groq import Groq
from .interfaces import ITestGenerationModel

logger = logging.getLogger(__name__)

class GroqTestGenerationModel(ITestGenerationModel):
    def __init__(self, model_name: str = "llama-3.1-70b-versatile"):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set.")
        self.client = Groq(api_key=self.api_key)
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            # We want JSON structured output
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM Generation failed: {e}")
            raise e
