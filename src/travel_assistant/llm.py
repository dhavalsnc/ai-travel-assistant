from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from travel_assistant.config import settings


class MissingAPIKeyError(RuntimeError):
    pass


def explain_llm_error(exc: Exception) -> str | None:
    text = str(exc)

    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        if "PerDay" in text or "free_tier" in text:
            return (
                "Gemini free-tier daily quota is exhausted (20 requests per day, per "
                "model — and one turn uses several). Options: wait for the daily reset, "
                "set TRAVEL_MODEL to a different Gemini model (each has its own quota), "
                "or enable billing on the Google Cloud project behind this key."
            )
        return "Gemini rate limit reached. Wait a few seconds and send the message again."

    if "NOT_FOUND" in text and "model" in text.lower():
        return (
            f"The configured model ({settings.model}) is not available to this key. "
            "Set TRAVEL_MODEL in .env to a model your key can access."
        )

    return None


def build_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    if not settings.google_api_key:
        raise MissingAPIKeyError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key "
            "from https://aistudio.google.com/apikey (it starts with 'AIza')."
        )

    return ChatGoogleGenerativeAI(
        model=settings.model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        max_output_tokens=settings.max_tokens,
        max_retries=3,
    )
