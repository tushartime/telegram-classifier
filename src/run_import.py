import argparse
import os
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Import sibling modules directly (script lives in src/)
from indexer import run_fetch
from organizer import build_tree, export_to_folders


def main():
    p = argparse.ArgumentParser(description="Index a Telegram channel and generate folder shortcuts")
    p.add_argument("--channel", required=True, help="Channel username or id (e.g. some_channel or @some_channel)")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--out", default=os.getenv("OUTPUT_DIR", "./output"))
    p.add_argument("--course-name", default=None)
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Fetching messages from Telegram...")
    run_fetch(args.channel, args.limit, str(out))
    index_path = out / "index.json"
    if not index_path.exists():
        print("Index not found, aborting.")
        return

    print("Building structure...")
    # set cache path for this run (keeps per-output cache)
    cache_path = out / ".llm_cache.json"
    os.environ["LLM_CACHE_PATH"] = str(cache_path)
    tree = build_tree(str(index_path))
    # persist tree so Electron UI can render the same categorized structure
    tree_path = out / "tree.json"
    with tree_path.open("w", encoding="utf8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)

    course_name = args.course_name or (tree.get("channel") or "Course")
    print(f"Exporting folders to {out}...")
    export_to_folders(tree, str(out), course_name)
    print("Done.")


if __name__ == "__main__":
    main()

