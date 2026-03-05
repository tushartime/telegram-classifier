import asyncio
import json
from datetime import timezone
from pathlib import Path
from typing import List, Dict, Any

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv
import os

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION = os.getenv("SESSION_NAME", "telegram_course_session")


async def fetch_index(channel: str, limit: int = 500, out_dir: str = "./output") -> List[Dict[str, Any]]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"

    client = TelegramClient(SESSION, API_ID, API_HASH)
    # In non-interactive contexts (Electron), we should not prompt for phone.
    # Instead, we rely on an existing authorized session and raise a clear
    # error if not logged in yet.
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "Telegram session is not authorized. "
            "Run `python src/run_import.py ...` once in a terminal, log in with your phone/code, "
            "then use the Electron UI."
        )

    entity = await client.get_entity(channel)
    messages = []
    async for msg in client.iter_messages(entity, limit=limit):
        # detect media (video / document)
        has_media = bool(msg.media)
        is_video = getattr(msg, "video", None) is not None
        if not has_media:
            continue

        caption = msg.text or msg.message or ""
        # build a t.me link if possible
        username = getattr(entity, "username", None)
        if username:
            link = f"https://t.me/{username}/{msg.id}"
        else:
            eid = str(getattr(entity, "id", ""))
            if eid.startswith("-100"):
                short = eid[4:]
            else:
                short = eid.lstrip("-")
            link = f"https://t.me/c/{short}/{msg.id}"

        mime_type = None
        size = None
        try:
            doc = getattr(msg.media, "document", None)
            if doc:
                mime_type = getattr(doc, "mime_type", None)
                size = getattr(doc, "size", None)
        except Exception:
            pass

        messages.append(
            {
                "message_id": msg.id,
                "date": msg.date.astimezone(timezone.utc).isoformat(),
                "caption": caption,
                "link": link,
                "is_video": is_video,
                "mime_type": mime_type,
                "size": size,
            }
        )

    # save index
    with index_path.open("w", encoding="utf8") as f:
        json.dump({"channel": str(channel), "messages": messages}, f, ensure_ascii=False, indent=2)

    await client.disconnect()
    return messages


def run_fetch(channel: str, limit: int, out_dir: str):
    return asyncio.run(fetch_index(channel, limit=limit, out_dir=out_dir))

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--channel", required=True)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--out", default="./output")
    args = p.parse_args()
    run_fetch(args.channel, args.limit, args.out)
