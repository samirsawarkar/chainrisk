"""
LLM : Google  OpenAI  Gemini.
: https://ai.google.dev/gemini-api/docs/openai
"""

import json
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..config import Config


class LLMClient:
    """Gemini(OpenAI SDK +  Base URL)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        chat_model: Optional[str] = None,
        json_model: Optional[str] = None,
    ):
        #  model=  chat/json 
        if model is not None:
            chat_model = chat_model or model
            json_model = json_model or model
        self.api_key = (api_key or Config.GEMINI_API_KEY or "").strip()
        self.base_url = (base_url or Config.GEMINI_API_BASE_URL or "").strip()
        self._default_chat_model = chat_model or Config.GEMINI_MODEL_DEFAULT
        self._default_json_model = json_model or Config.GEMINI_MODEL_JSON

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY ")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        model: Optional[str] = None,
    ) -> str:
        use_model = model or self._default_chat_model
        kwargs: Dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception:
            if response_format:
                kwargs.pop("response_format", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise

        content = response.choices[0].message.content or ""
        content = re.sub(
            r"<think>[\s\S]*?</think>", "", content
        ).strip()
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        use_model = model or self._default_json_model
        try:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                model=use_model,
            )
        except Exception:
            extra = (
                "\n\nRespond with a single valid JSON object only, no markdown fences."
            )
            patched = list(messages)
            if patched and patched[-1].get("role") == "user":
                patched[-1] = {
                    **patched[-1],
                    "content": patched[-1]["content"] + extra,
                }
            response = self.chat(
                messages=patched,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=None,
                model=use_model,
            )

        cleaned_response = response.strip()
        cleaned_response = re.sub(
            r"^```(?:json)?\s*\n?", "", cleaned_response, flags=re.IGNORECASE
        )
        cleaned_response = re.sub(r"\n?```\s*$", "", cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLMJSON: {cleaned_response}") from e
