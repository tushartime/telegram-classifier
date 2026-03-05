import os
from typing import List, Optional
import requests
import json


def _build_prompt_with_candidates(text: str, candidates: List[str]) -> str:
    return (
        "You are a classifier. Your task is to choose EXACTLY ONE category from the list below "
        "that best matches the caption.\n"
        "Rules:\n"
        "- You MUST answer with one category from the list.\n"
        "- If you are unsure, pick the closest category.\n"
        "- Do NOT answer with anything that is not in the list.\n"
        "- Do NOT answer 'Misc', 'Other', or explanations.\n"
        "Return only the category name, nothing else.\n\n"
        "Categories:\n"
        f"{', '.join(candidates)}\n\n"
        "Caption:\n"
        f'\"\"\"{text}\"\"\"'
    )


def _build_prompt_freeform(text: str) -> str:
    return (
        "You are a topic labeller for course content.\n"
        "Given the caption below, invent ONE short category name (1-3 words) that best describes the topic.\n"
        "Rules:\n"
        "- Answer with ONLY the category name.\n"
        "- Keep it short and generic (e.g. 'Sales', 'Video Editing', 'Manychat Automation').\n"
        "- Do NOT add explanations or quotes.\n\n"
        "Caption:\n"
        f'\"\"\"{text}\"\"\"'
    )


def classify_with_api(text: str, candidates: Optional[List[str]], api_url: str, api_key: str) -> str:
    """
    HTTP-based LLM classification. If `candidates` is provided, the model must pick one of them.
    If not, the model should generate a short freeform category name.
    """
    if not api_url or not api_key:
        raise RuntimeError("api_url and api_key are required for HTTP LLM classification.")

    if candidates:
        prompt = _build_prompt_with_candidates(text, candidates)
    else:
        prompt = _build_prompt_freeform(text)

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"prompt": prompt, "max_output_tokens": 64, "temperature": 0.0}

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        body = resp.text.strip()
        if not body:
            return "Uncategorized"
        choice = body.splitlines()[0].strip().strip(' "\'')
        if candidates:
            for c in candidates:
                if choice.lower() == c.lower():
                    return c
            for c in candidates:
                if c.lower() in choice.lower() or choice.lower() in c.lower():
                    return c
        return choice or "Uncategorized"
    except Exception:
        return "Uncategorized"

