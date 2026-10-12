import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from groq import Groq
from .interfaces import ITestGenerationModel
from .config import resolve_llm_config, resolve_context_budget

logger = logging.getLogger(__name__)

class GroqTestGenerationModel(ITestGenerationModel):
    def __init__(self, model_name: str = None):
        llm_config = resolve_llm_config()
        self.budget_config = resolve_context_budget()
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set.")
        self.client = Groq(api_key=self.api_key)
        self.model_name = model_name or llm_config.model_name
        self.temperature = llm_config.temperature

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """
        Generate with token estimation and retry with smaller context if needed.
        """
        # Estimate tokens before calling
        estimated_tokens = self._estimate_tokens(prompt, system_prompt)
        
        logger.info(
            f"[AgentQE Generation] model={self.model_name} "
            f"estimated_prompt_tokens={estimated_tokens} "
            f"budget={self.budget_config.max_prompt_tokens}"
        )
        
        if estimated_tokens > self.budget_config.max_prompt_tokens:
            logger.warning(
                f"Prompt exceeds budget ({estimated_tokens} > {self.budget_config.max_prompt_tokens}). "
                f"This should have been reduced by the context builder."
            )
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            # We want JSON structured output
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            
            # Check for context length error
            if "413" in error_str or "context" in error_str.lower() or "tokens" in error_str.lower():
                logger.error(f"Context length error: {e}")
                raise GenerationError(
                    "PROMPT_TOO_LARGE",
                    "Generation context exceeded the configured token budget after reduction."
                )
            
            logger.error(f"LLM Generation failed (model={self.model_name}): {e}")
            raise e
    
    def _estimate_tokens(self, prompt: str, system_prompt: str = "") -> int:
        """
        Estimate token count using conservative heuristic.
        
        Approximation: 1 token ≈ 3.5 characters for English text.
        This is conservative and may overestimate slightly.
        """
        text = system_prompt + prompt
        # Remove whitespace for more accurate count
        text = re.sub(r'\s+', ' ', text)
        # Conservative estimate: 1 token per 3.5 characters
        return int(len(text) / 3.5)


class GenerationError(Exception):
    """Structured error for generation failures."""
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(message)
