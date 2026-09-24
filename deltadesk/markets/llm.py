"""Language-model providers behind the agent chat. Free tiers first, paid ones when you add a key.

Pick with DD_LLM in .env: auto (default: first provider with a usable key, in the order below), or a name.
  groq        GROQ_API_KEY (gsk_…)      https://console.groq.com     free tier, fast · GROQ_MODEL (llama-3.3-70b-versatile)
  gemini      GEMINI_API_KEY (AIza…)    https://aistudio.google.com  free tier · GEMINI_MODEL (gemini-2.0-flash)
  openrouter  OPENROUTER_API_KEY (sk-or-…) https://openrouter.ai     free models carry ":free" · OPENROUTER_MODEL
  deepseek    DEEPSEEK_API_KEY (sk-…)   https://platform.deepseek.com  cheap, paid · DEEPSEEK_MODEL (deepseek-chat)
  openai      OPENAI_API_KEY (sk-…)     https://platform.openai.com  paid · OPENAI_MODEL (gpt-4o-mini)
  ollama      no key, DD_LLM=ollama     http://localhost:11434       local · OLLAMA_MODEL (llama3.2)
Values that do not carry the vendor's prefix (for example a host's generated placeholder) are ignored.
Requests carry a browser-style User-Agent: Cloudflare in front of some providers rejects Python's default one
(error 1010). With no provider the chat still works: the agent composes the same structured answer by rules.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeltaDesk/0.1 (+https://github.com/Shiripatel/delta-desk)"}
OPENAI_STYLE = {"groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
                "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
                "deepseek": ("https://api.deepseek.com/v1/chat/completions", "DEEPSEEK_API_KEY"),
                "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY")}


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, provider: str | None = None, timeout: float = 45.0) -> None:
        self.timeout = timeout
        want = (provider or os.environ.get("DD_LLM") or "auto").lower()
        self.provider, self.model = self._pick(want)

    @staticmethod
    def _pick(want: str) -> tuple[str, str]:
        env = os.environ.get

        def key(name: str, prefix: str) -> str | None:   # placeholder values are ignored
            v = env(name) or ""
            return v if v.startswith(prefix) else None
        table = [("groq", key("GROQ_API_KEY", "gsk_"), env("GROQ_MODEL", "llama-3.3-70b-versatile")),
                 ("gemini", key("GEMINI_API_KEY", "AIza"), env("GEMINI_MODEL", "gemini-2.0-flash")),
                 ("openrouter", key("OPENROUTER_API_KEY", "sk-or-"), env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")),
                 ("deepseek", key("DEEPSEEK_API_KEY", "sk-"), env("DEEPSEEK_MODEL", "deepseek-chat")),
                 ("openai", key("OPENAI_API_KEY", "sk-"), env("OPENAI_MODEL", "gpt-4o-mini")),
                 ("ollama", "local" if want == "ollama" else None, env("OLLAMA_MODEL", "llama3.2"))]
        if want == "none":
            return "none", ""
        for name, k, model in table:
            if (want == "auto" or want == name) and k:
                return name, model
        return "none", ""

    @property
    def available(self) -> bool:
        return self.provider != "none"

    def label(self) -> str:
        return f"{self.provider} · {self.model}" if self.available else "rules v0 (no language model key set)"

    def chat(self, system: str, messages: list[dict], max_tokens: int = 700, temperature: float = 0.2) -> str:
        """messages: [{role: user|assistant, content}]. Returns the assistant text."""
        if not self.available:
            raise LLMError("no provider")
        if self.provider == "gemini":
            return self._gemini(system, messages, max_tokens, temperature)
        if self.provider == "ollama":
            out = self._post("http://localhost:11434/api/chat", {"model": self.model, "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens},  # noqa: E501
                                                                "messages": [{"role": "system", "content": system}] + messages}, {})
            return out["message"]["content"]
        url, env_key = OPENAI_STYLE[self.provider]
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}] + messages}  # noqa: E501
        extra = {"Authorization": f"Bearer {os.environ.get(env_key, '')}"}
        if self.provider == "openrouter":
            extra.update({"HTTP-Referer": "https://github.com/Shiripatel/delta-desk", "X-Title": "Delta Desk"})
        out = self._post(url, body, extra)
        try:
            return out["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"{self.provider}: unexpected reply {str(out)[:200]}") from exc

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
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers={**HEADERS, **headers}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300].replace("\n", " ")
            raise LLMError(f"{self.provider} {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMError(f"{self.provider} unreachable: {exc.reason}") from exc
