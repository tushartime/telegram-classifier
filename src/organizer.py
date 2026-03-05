import json
import re
from pathlib import Path
from typing import List, Dict, Optional
import os
import datetime
import hashlib
import time


def sanitize_name(s: str, max_len: int = 80) -> str:
    # remove illegal filename chars and trim
    invalid = r'<>:"/\\|?*\n\r\t'
    s = "".join(ch for ch in s if ch not in invalid)
    s = s.strip()
    if len(s) > max_len:
        s = s[: max_len - 3].rstrip() + "..."
    return s or "untitled"


SECTION_RE = re.compile(r"\b(module|week|chapter|part|section)\s*[:\-\s]*#?\s*(\d+)", re.I)


def infer_section(caption: str) -> str:
    if not caption:
        return "Misc"
    m = SECTION_RE.search(caption)
    if m:
        name = m.group(1).title()
        num = m.group(2)
        return f"{name} {num}"
    # look for "Lecture 1", "Lec 01"
    m2 = re.search(r"\b(lecture|lec)\s*[:\-\s]*#?\s*(\d+)", caption, re.I)
    if m2:
        return f"Lecture {m2.group(2)}"
    # fallback: group by month-year
    try:
        # sometimes captions include dates, otherwise use today's month-year
        return "Misc"
    except Exception:
        return "Misc"


def classify_topic(
    caption: str,
    user_categories: Optional[List[str]] = None,
    allowed_categories: Optional[List[str]] = None,
    max_categories: int = 0,
) -> str:
    """
    Classify a caption into a category using ONLY the LLM when configured.
    - If `user_categories` is provided (e.g. "Verbal, Quant"), the LLM must choose one of them.
    - If no categories are provided, the LLM invents a short category name for each caption.
    - If no LLM backend is configured, everything falls into 'Uncategorized'.
    Results are cached via LLM_CACHE_PATH to avoid repeated calls.
    """
    text = (caption or "").strip()
    if not text:
        return "Uncategorized"

    backend = os.getenv("LLM_BACKEND", "").lower()
    # When an LLM backend is configured, we rely solely on the LLM (plus cache).
    cache_path = os.getenv("LLM_CACHE_PATH", "")
    cache = {}
    if cache_path:
        try:
            cache_p = Path(cache_path)
            if cache_p.exists():
                cache = json.loads(cache_p.read_text(encoding="utf8"))
        except Exception:
            cache = {}

    def _cache_lookup(text: str):
        key_base = text
        if user_categories:
            key_base += "||UC:" + ",".join(user_categories)
        if allowed_categories:
            key_base += "||AC:" + ",".join(allowed_categories)
        key = hashlib.sha256(key_base.encode("utf8")).hexdigest()
        entry = cache.get(key)
        if not entry:
            return None
        # optional TTL support - if present and expired, treat as miss
        ttl = entry.get("_ttl", 0)
        ts = entry.get("_ts", 0)
        if ttl and (time.time() - ts) > ttl:
            return None
        return entry.get("category")

    def _cache_store(text: str, category: str, ttl: int = 0):
        try:
            key_base = text
            if user_categories:
                key_base += "||UC:" + ",".join(user_categories)
            if allowed_categories:
                key_base += "||AC:" + ",".join(allowed_categories)
            key = hashlib.sha256(key_base.encode("utf8")).hexdigest()
            cache[key] = {"category": category, "_ts": int(time.time()), "_ttl": int(ttl)}
            if cache_path:
                Path(cache_path).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf8")
        except Exception:
            pass

    # If an LLM backend is configured, use it (with cache).
    if backend:
        # Try cache lookup first
        cached = None
        try:
            cached = _cache_lookup(text)
        except Exception:
            cached = None
        if cached:
            return cached

        try:
            from src.llm_classifier import classify_with_api
            # Decide candidate list for the LLM:
            # - If user_categories are provided, always use them.
            # - Else, if allowed_categories is provided (we already reached max), use that list.
            # - Else, let the LLM invent freeform categories (cand=None).
            cand: Optional[List[str]] = None
            if user_categories:
                cand = list(user_categories)
            elif allowed_categories:
                cand = list(allowed_categories)
            choice = None
            if backend in ("gemini", "http"):
                api_url = os.getenv("GEMINI_API_URL") or os.getenv("LLM_API_URL")
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
                if api_url and api_key:
                    choice = classify_with_api(caption, cand, api_url, api_key)
            if choice:
                ttl = int(os.getenv("LLM_CACHE_TTL", "0") or 0)
                try:
                    _cache_store(text, choice, ttl=ttl)
                except Exception:
                    pass
                return choice
        except Exception:
            # if LLM completely fails, fall back to Uncategorized
            return "Uncategorized"

        # If LLM returns nothing usable, also treat as Uncategorized
        return "Uncategorized"

    # No LLM backend configured: simple fallback
    return "Uncategorized"


def build_tree(index_path: str) -> Dict:
    p = Path(index_path)
    data = json.loads(p.read_text(encoding="utf8"))
    msgs = data.get("messages", [])
    # sort by date ascending
    msgs.sort(key=lambda m: m.get("date", ""))

    # Optional user-provided categories, comma-separated, e.g. "Verbal, Quant, Aptitude"
    user_cats_str = os.getenv("USER_CATEGORIES", "").strip()
    user_categories: Optional[List[str]] = None
    if user_cats_str:
        parsed = [c.strip() for c in user_cats_str.split(",") if c.strip()]
        if parsed:
            user_categories = parsed

    # Optional max number of categories (when user_categories is not provided)
    max_categories_env = os.getenv("MAX_CATEGORIES", "").strip()
    try:
        max_categories = int(max_categories_env) if max_categories_env else 0
    except ValueError:
        max_categories = 0

    # cache path for this tree
    cache_file = os.getenv("LLM_CACHE_PATH", str(Path(index_path).parent / ".llm_cache.json"))

    dynamic_categories: List[str] = []

    tree: Dict[str, Dict[str, List[Dict]]] = {}
    for msg in msgs:
        caption = msg.get("caption", "") or ""
        os.environ["LLM_CACHE_PATH"] = cache_file

        if user_categories:
            category = classify_topic(caption, user_categories=user_categories)
        else:
            # If we have already reached the requested max_categories, force assignments
            # into the existing dynamic_categories via allowed_categories.
            allowed = dynamic_categories if (max_categories and len(dynamic_categories) >= max_categories) else None
            category = classify_topic(
                caption,
                user_categories=None,
                allowed_categories=allowed,
                max_categories=max_categories,
            )
            if not allowed and category not in dynamic_categories:
                dynamic_categories.append(category)

        section = infer_section(caption)
        tree.setdefault(category, {}).setdefault(section, []).append(msg)
    return {"channel": data.get("channel"), "categories": tree}


def create_shortcut_file(path: Path, url: str):
    content = "[InternetShortcut]\n"
    content += f"URL={url}\n"
    # minimal .url file; Windows will open default browser / handler
    path.write_text(content, encoding="utf8")


def export_to_folders(tree: Dict, out_dir: str, course_name: str = "Course"):
    base = Path(out_dir) / sanitize_name(course_name)
    base.mkdir(parents=True, exist_ok=True)
    categories: Dict[str, Dict[str, List[Dict]]] = tree.get("categories", {})
    for cat_name, sections in categories.items():
        cat_folder = base / sanitize_name(cat_name)
        cat_folder.mkdir(parents=True, exist_ok=True)
        for sec_name, messages in sections.items():
            sec_folder = cat_folder / sanitize_name(sec_name)
            sec_folder.mkdir(parents=True, exist_ok=True)
            for idx, msg in enumerate(messages, start=1):
                short = (msg.get("caption") or "").split("\n")[0][:60]
                filename = f"{idx:02d} - {sanitize_name(short)}.url"
                target = sec_folder / filename
                create_shortcut_file(target, msg.get("link", ""))


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--index", default="./output/index.json")
    p.add_argument("--out", default="./output")
    p.add_argument("--course-name", default="Course")
    args = p.parse_args()
    tree = build_tree(args.index)
    export_to_folders(tree, args.out, args.course_name)
