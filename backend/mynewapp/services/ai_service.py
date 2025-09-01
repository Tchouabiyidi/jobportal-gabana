import json
import os
import requests
from typing import List, Dict, Any, Optional

OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY") or os.getenv("OPENROUTER_KEY")
# Fallback to hardcoded key ONLY if env not provided (user supplied explicitly). Consider using env in production.
if not OPENROUTER_API_KEY:
    OPENROUTER_API_KEY = "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"

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")


def _build_messages(resume_text: str, jobs: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    system = (
        "You are an assistant that selects the single best matching job for a job seeker. "
        "ALWAYS respond with strict JSON using this schema without markdown or commentary: "
        "{\n  \"best_job_id\": number,\n  \"score\": number,\n  \"reason\": string\n} "
        "Choose best_job_id from the provided list of jobs by id. Score in 0..100."
    )
    user_prompt = {
        "resume_text": resume_text,
        "jobs": jobs,
        "instruction": (
            "Pick the single best matching job id based on skills/experience overlap and role relevance. "
            "Return strict JSON, no extra text."
        ),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_prompt)},
    ]


def call_openrouter(messages: List[Dict[str, str]], *, timeout: int = 30) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        # Encourage JSON; many models follow instructions above.
        "temperature": 0.2,
    }
    resp = requests.post(OPENROUTER_API_URL, headers=headers, data=json.dumps(payload), timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content or ""


def parse_best_job_json(raw: str) -> Optional[Dict[str, Any]]:
    """Try to parse a JSON object from the model output.
    Handles cases where the model returns extra text by scanning for a JSON object.
    """
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Attempt to find first JSON object region
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = raw[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None
    return None


def recommend_best_job(resume_text: str, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calls the LLM to choose the best job id from provided list.
    Returns a dict: {"best_job_id": int|None, "score": int|None, "reason": str, "raw": str}
    """
    messages = _build_messages(resume_text, jobs)
    raw = call_openrouter(messages)
    parsed = parse_best_job_json(raw) or {}
    best_job_id = parsed.get("best_job_id")
    score = parsed.get("score")
    reason = parsed.get("reason")
    return {"best_job_id": best_job_id, "score": score, "reason": reason, "raw": raw}
