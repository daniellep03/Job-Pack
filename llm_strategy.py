"""
LLM Strategy Pattern — GoF Strategy
Each concrete strategy implements the same interface.
Switching backends requires only a config change (LLM_BACKEND in .env).
"""

from abc import ABC, abstractmethod
import os
import json
import requests


class LLMStrategy(ABC):
    """Abstract base — defines the interface all LLM backends must satisfy."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return generated text given a system and user prompt."""
        ...


# ── Concrete Strategy 1: Claude API ─────────────────────────────────────────

class ClaudeStrategy(LLMStrategy):
    """Uses Anthropic's Claude API."""

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022")
        self.api_url = "https://api.anthropic.com/v1/messages"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        resp = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


# ── Concrete Strategy 2: Ollama (hosted class endpoint or local) ─────────────

class OllamaStrategy(LLMStrategy):
    """
    Works for both the hosted class Ollama endpoint and a raw local Ollama.
    Set OLLAMA_BASE_URL to switch between them — zero code change.
    """

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "llama3")
        self.api_key = os.getenv("OLLAMA_API_KEY", "")  # required for class endpoint

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # ollama.com cloud uses OpenAI-compatible /v1/chat/completions.
        # NOTE: the host is "ollama.com", not "api.ollama.com" — the latter
        # 301-redirects to this host, and requests drops the Authorization
        # header across that cross-host redirect, breaking auth.
        # Self-hosted local Ollama uses /api/chat instead.
        if "ollama.com" in self.base_url:
            url = f"{self.base_url}/v1/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 4096,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        else:
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


# ── Concrete Strategy 3: Groq ────────────────────────────────────────────────

class GroqStrategy(LLMStrategy):
    """Uses Groq's free OpenAI-compatible API (fast Llama3 inference)."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not set in .env")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
        }
        resp = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# ── Factory ──────────────────────────────────────────────────────────────────

def get_llm_strategy() -> LLMStrategy:
    """
    Read LLM_BACKEND from environment and return the correct strategy.
    Valid values: 'claude', 'ollama', 'groq'  (default: 'ollama')
    """
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    if backend == "claude":
        return ClaudeStrategy()
    elif backend == "ollama":
        return OllamaStrategy()
    elif backend == "groq":
        return GroqStrategy()
    else:
        raise ValueError(f"Unknown LLM_BACKEND '{backend}'. Use 'claude', 'ollama', or 'groq'.")
