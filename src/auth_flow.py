import argparse
import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
DEFAULT_SESSION = os.getenv("SESSION_NAME", "telegram_course_session")


async def send_code(phone: str, session_name: str):
    client = TelegramClient(session_name or DEFAULT_SESSION, API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        # Print only the phone_code_hash so Electron can capture it
        print(sent.phone_code_hash)
    finally:
        await client.disconnect()


async def sign_in(phone: str, code: str, code_hash: str, session_name: str, password: str | None = None):
    client = TelegramClient(session_name or DEFAULT_SESSION, API_ID, API_HASH)
    await client.connect()
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
        except SessionPasswordNeededError:
            if not password:
                # Signal to the caller that a password is required
                print("PASSWORD_NEEDED")
                return
            await client.sign_in(password=password)
        me = await client.get_me()
        # If we got here, login succeeded and session is saved to disk
        print("OK")
    finally:
        await client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Handle Telegram login without interactive prompts")
    parser.add_argument("action", choices=["send-code", "sign-in"])
    parser.add_argument("--phone", required=True)
    parser.add_argument("--session", default=None)
    parser.add_argument("--code", default=None)
    parser.add_argument("--code-hash", default=None)
    parser.add_argument("--password", default=None)

    args = parser.parse_args()

    if args.action == "send-code":
        asyncio.run(send_code(args.phone, args.session or DEFAULT_SESSION))
    else:
        if not args.code or not args.code_hash:
            raise SystemExit("code and code-hash are required for sign-in")
        asyncio.run(
            sign_in(
                phone=args.phone,
                code=args.code,
                code_hash=args.code_hash,
                session_name=args.session or DEFAULT_SESSION,
                password=args.password,
            )
        )


if __name__ == "__main__":
    main()

