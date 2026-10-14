"""Small Gemini REST adapter; source checks remain in the caller."""

import json
from urllib.request import Request, urlopen


MODEL = "gemini-2.5-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def generate(api_key: str, payload: dict) -> dict:
    if not api_key.strip():
        raise ValueError("Missing Gemini API key")
    request = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"x-goog-api-key": api_key.strip(), "Content-Type": "application/json"},
                      method="POST")
    with urlopen(request, timeout=55) as response:
        return json.load(response)


def generate_json(api_key: str, schema: dict, instructions: str, facts: dict, max_tokens: int) -> dict:
    payload = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": [{"parts": [{"text": json.dumps(facts, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                             "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}},
    }
    body = generate(api_key, payload)
    candidates = body.get("candidates") or []
    if not candidates or candidates[0].get("finishReason") not in ("STOP", None):
        raise ValueError("Gemini response did not complete; retry the action")
    parts = candidates[0].get("content", {}).get("parts", [])
    content = "".join(part.get("text", "") for part in parts)
    if not content:
        raise ValueError("Gemini returned no text")
    answer = json.loads(content)
    if not isinstance(answer, dict):
        raise ValueError("Gemini returned an unexpected response")
    return answer


def search_sources(api_key: str, query: str) -> list[dict]:
    """Return only search-backed URLs, never model-generated URLs."""
    body = generate(api_key, {"contents": [{"parts": [{"text": query}]}],
                              "tools": [{"google_search": {}}],
                              "generationConfig": {"maxOutputTokens": 650,
                                                   "thinkingConfig": {"thinkingBudget": 0}}})
    candidates = body.get("candidates") or []
    if not candidates or candidates[0].get("finishReason") not in ("STOP", None):
        raise ValueError("Gemini search did not complete")
    return [chunk["web"] for chunk in candidates[0].get("groundingMetadata", {}).get("groundingChunks", [])
            if isinstance(chunk, dict) and isinstance(chunk.get("web"), dict)]
