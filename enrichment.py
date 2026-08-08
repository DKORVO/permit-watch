import os

import requests


def enrich_item(item):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    payload = {
        "model": os.environ.get("OPENROUTER_MODEL", "openrouter/free"),
        "messages": [{"role": "user", "content": "Summarize this public planning/permit notice in 2 factual sentences. State any date, location, application number, and action requested only if present. Do not infer facts.\n\nTitle: " + item["title"] + "\nText: " + item["excerpt"]}],
        "temperature": 0.1,
        "max_tokens": 180,
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "http://localhost", "X-Title": "Permit Watch"}, timeout=(10, 60))
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        return "Enrichment returned no summary; review the original source."
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return "Enrichment unavailable; review the original source."
