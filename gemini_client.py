"""Small Gemini REST adapter; source checks remain in the caller."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL = "gemini-3.5-flash-lite"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


class GeminiAPIError(ValueError):
    """A safe, actionable explanation; never contains credentials or CV text."""


def explain_http_error(status: int, google_status: str, details: str = "") -> str:
    if status in (401, 403):
        return f"Gemini HTTP {status}: API key rejected or Gemini API access is disabled for this project. Check your AI Studio key and project."
    if status == 429:
        return "Gemini HTTP 429: rate or free-tier quota reached. Check your project's Gemini API rate limits."
    if status == 404:
        return "Gemini HTTP 404: this model is unavailable to this project. Check its available models in Google AI Studio."
    if status == 400:
        return f"Gemini HTTP 400 ({google_status or 'INVALID_ARGUMENT'}): {details[:350] or 'request rejected; check model access and app code.'}"
    return f"Gemini HTTP {status}: Google could not complete this request ({google_status or 'API error'})."


def generate(api_key: str, payload: dict) -> dict:
    if not api_key.strip():
        raise ValueError("Missing Gemini API key")
    request = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"x-goog-api-key": api_key.strip(), "Content-Type": "application/json"},
                      method="POST")
    try:
        with urlopen(request, timeout=55) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            body = json.load(exc)
            status = str(body.get("error", {}).get("status", ""))[:40]
            details = str(body.get("error", {}).get("message", "")).replace(api_key.strip(), "[redacted]")
        except (ValueError, AttributeError):
            status, details = "", ""
        raise GeminiAPIError(explain_http_error(exc.code, status, details)) from None
    except URLError:
        raise GeminiAPIError("Could not reach the Gemini API. Check the hosting network and try again.") from None


def generate_json(api_key: str, schema: dict, instructions: str, facts: dict, max_tokens: int) -> dict:
    payload = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": [{"parts": [{"text": json.dumps(facts, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                             "maxOutputTokens": max_tokens},
    }
    body = generate(api_key, payload)
    candidates = body.get("candidates") or []
    if not candidates or candidates[0].get("finishReason") not in ("STOP", None):
        reason = candidates[0].get("finishReason", "no candidate") if candidates else "no candidate"
        raise GeminiAPIError(f"Gemini did not complete the response ({reason}). Try the action again.")
    parts = candidates[0].get("content", {}).get("parts", [])
    content = "".join(part.get("text", "") for part in parts)
    if not content:
        raise GeminiAPIError("Gemini returned no text. Check the model and try again.")
    answer = json.loads(content)
    if not isinstance(answer, dict):
        raise GeminiAPIError("Gemini returned an unexpected response format.")
    return answer


def search_sources(api_key: str, query: str) -> list[dict]:
    """Return only search-backed URLs, never model-generated URLs."""
    body = generate(api_key, {"contents": [{"parts": [{"text": query}]}],
                              "tools": [{"google_search": {}}],
                              "generationConfig": {"maxOutputTokens": 900}})
    candidates = body.get("candidates") or []
    if not candidates or candidates[0].get("finishReason") not in ("STOP", None):
        raise ValueError("Gemini search did not complete")
    return [chunk["web"] for chunk in candidates[0].get("groundingMetadata", {}).get("groundingChunks", [])
            if isinstance(chunk, dict) and isinstance(chunk.get("web"), dict)]
