"""Language-model providers behind the agent chat. All free tiers, all optional.

Pick with DD_LLM in .env: auto (default: first provider with a key), groq, gemini, openrouter, ollama, none.
  groq        GROQ_API_KEY        https://console.groq.com        free tier, fast; model GROQ_MODEL (llama-3.3-70b-versatile)
  gemini      GEMINI_API_KEY      https://aistudio.google.com     free tier; model GEMINI_MODEL (gemini-2.0-flash)
  openrouter  OPENROUTER_API_KEY  https://openrouter.ai           free models carry the ":free" suffix; OPENROUTER_MODEL
  ollama      none                http://localhost:11434          runs locally; OLLAMA_MODEL (llama3.2)
With no provider the chat still works: the agent composes a grounded answer from the desk's numbers by rules.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, provider: str | None = None, timeout: float = 40.0) -> None:
        self.timeout = timeout
        want = (provider or os.environ.get("DD_LLM") or "auto").lower()
        self.provider, self.model = self._pick(want)

    @staticmethod
    def _pick(want: str) -> tuple[str, str]:
        env = os.environ.get
        table = [("groq", env("GROQ_API_KEY"), env("GROQ_MODEL", "llama-3.3-70b-versatile")),
                 ("gemini", env("GEMINI_API_KEY"), env("GEMINI_MODEL", "gemini-2.0-flash")),
                 ("openrouter", env("OPENROUTER_API_KEY"), env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")),
                 ("ollama", "local" if want == "ollama" else None, env("OLLAMA_MODEL", "llama3.2"))]
        if want == "none":
            return "none", ""
        for name, key, model in table:
            if (want == "auto" or want == name) and key:
                return name, model
        return "none", ""

    @property
    def available(self) -> bool:
        return self.provider != "none"

    def label(self) -> str:
        return f"{self.provider} · {self.model}" if self.available else "rules v0 (no language model key set)"

    def chat(self, system: str, messages: list[dict], max_tokens: int = 600, temperature: float = 0.3) -> str:
        """messages: [{role: user|assistant, content}]. Returns the assistant text."""
        if not self.available:
            raise LLMError("no provider")
        if self.provider == "gemini":
            return self._gemini(system, messages, max_tokens, temperature)
        if self.provider == "ollama":
            return self._post("http://localhost:11434/api/chat", {"model": self.model, "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens},  # noqa: E501
                                                                 "messages": [{"role": "system", "content": system}] + messages}, {})["message"]["content"]  # noqa: E501
        url, key = {"groq": ("https://api.groq.com/openai/v1/chat/completions", os.environ.get("GROQ_API_KEY", "")),
                    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", os.environ.get("OPENROUTER_API_KEY", ""))}[self.provider]  # noqa: E501
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}] + messages}  # noqa: E501
        out = self._post(url, body, {"Authorization": f"Bearer {key}", "HTTP-Referer": "https://github.com/Shiripatel/delta-desk", "X-Title": "Delta Desk"})  # noqa: E501
        return out["choices"][0]["message"]["content"]

    def _gemini(self, system: str, messages: list[dict], max_tokens: int, temperature: float) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={os.environ.get('GEMINI_API_KEY', '')}"  # noqa: E501
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages],  # noqa: E501
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        out = self._post(url, body, {})
        try:
            return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise LLMError(f"gemini: unexpected reply {str(out)[:200]}") from exc

    def _post(self, url: str, body: dict, headers: dict) -> dict:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"{self.provider} {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMError(f"{self.provider} unreachable: {exc.reason}") from exc
