import os
from abc import ABC, abstractmethod

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="LLM Provider Service", version="0.1.0")

class GenerateRequest(BaseModel):
    provider: str
    model: str
    api_key: str = ""
    messages: list[dict[str, str]]

class Provider(ABC):
    @abstractmethod
    async def generate(self, model, api_key, messages):
        raise NotImplementedError

class GroqProvider(Provider):
    async def generate(self, model, api_key, messages):
        import asyncio
        key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
        if not key:
            raise HTTPException(400, "Groq API key is not configured")
        
        models_to_try = [model]
        if "120b" in model and "openai/gpt-oss-20b" not in models_to_try:
            models_to_try.append("openai/gpt-oss-20b")

        async with httpx.AsyncClient(timeout=90) as client:
            last_err = None
            for m in models_to_try:
                for attempt in range(3):
                    r = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={"model": m, "messages": messages, "temperature": 0.2, "max_tokens": 8192},
                    )
                    if r.status_code == 200:
                        return r.json()["choices"][0]["message"]["content"]
                    if r.status_code == 429:
                        last_err = r.text
                        if attempt < 2:
                            await asyncio.sleep(2.0 * (attempt + 1))
                            continue
                        break # try fallback model
                    if r.status_code >= 400:
                        raise HTTPException(r.status_code, r.text)
            raise HTTPException(429, last_err or "Groq rate limit exceeded after retries")

class GeminiProvider(Provider):
    async def generate(self, model, api_key, messages):
        key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not key:
            raise HTTPException(400, "Gemini API key is not configured")
        
        system_instruction = None
        contents = []
        for m in messages:
            role = m.get("role", "")
            content_text = m.get("content", "")
            if role == "system":
                system_instruction = {"parts": [{"text": content_text}]}
            else:
                gemini_role = "model" if role == "assistant" else "user"
                # Prevent consecutive identical roles in Gemini multi-turn format
                if contents and contents[-1]["role"] == gemini_role:
                    contents[-1]["parts"][0]["text"] += f"\n\n{content_text}"
                else:
                    contents.append({"role": gemini_role, "parts": [{"text": content_text}]})

        body = {"contents": contents}
        if system_instruction:
            body["system_instruction"] = system_instruction

        import asyncio
        async with httpx.AsyncClient(timeout=90) as client:
            for attempt in range(3):
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": key},
                    json=body,
                )
                if r.status_code == 200:
                    try:
                        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError, TypeError) as exc:
                        raise HTTPException(502, "Unexpected Gemini response") from exc
                if r.status_code == 429 and attempt < 2:
                    await asyncio.sleep(2.5 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    raise HTTPException(r.status_code, r.text)
            raise HTTPException(429, "Gemini rate limit exceeded after retries")

PROVIDERS = {"groq": GroqProvider(), "gemini": GeminiProvider()}

@app.get("/health")
def health():
    return {"status": "ok", "service": "llm"}

@app.get("/providers")
def providers():
    return {
        "providers": {
            "groq": {"models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]},
            "gemini": {"models": ["gemini-2.5-flash"]},
        }
    }

@app.post("/generate")
async def generate(request: GenerateRequest):
    provider = PROVIDERS.get(request.provider.lower())
    if not provider:
        raise HTTPException(400, f"Unsupported provider: {request.provider}")
    content = await provider.generate(request.model, request.api_key, request.messages)
    return {"content": content, "provider": request.provider, "model": request.model}
