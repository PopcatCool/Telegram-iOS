"""Forwards incoming Telegram messages to the Bark app (api.day.app) as push notifications.

Runs as an extra session of your account. It only listens: it never marks
anything as read and never reports the account as online.
"""
import asyncio
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

from telethon import TelegramClient, errors, events, functions, types, utils

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
QR_PAGE_PATH = BASE_DIR / "login-qr.html"
# chats that currently have a notification in Bark, with the number of messages it covers
UNREAD_PATH = BASE_DIR / "notified.json"
# Bark caches the icon by URL: change the file name when the icon changes
DEFAULT_ICON_URL = "https://raw.githubusercontent.com/PopcatCool/Telegram-iOS/master/bark-relay/icon-sparkling.png"
MUTE_CACHE_SECONDS = 600


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"Нет файла {CONFIG_PATH}. Скопируй config.example.json в config.json и заполни.")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    for key in ("api_id", "api_hash", "bark_key"):
        if not config.get(key):
            sys.exit(f"В config.json не заполнено поле {key}")
    return config


config = load_config()
client = TelegramClient(str(BASE_DIR / "relay"), int(config["api_id"]), config["api_hash"])
mute_cache = {}


def load_unread_counts():
    try:
        return {int(chat_id): count for chat_id, count in json.loads(UNREAD_PATH.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


unread_counts = load_unread_counts()


def save_unread_counts():
    UNREAD_PATH.write_text(json.dumps(unread_counts), encoding="utf-8")


def notification_id(chat_id):
    # One notification per chat: a new message replaces it, reading the chat deletes it
    return f"chat{chat_id}"


def settings_muted(settings):
    """True/False if the settings decide it, None if they defer to the default."""
    mute_until = getattr(settings, "mute_until", None)
    if mute_until is None:
        return None
    if isinstance(mute_until, datetime):
        return mute_until > datetime.now(timezone.utc)
    return mute_until > time.time()


async def cached_muted(key, peer):
    cached = mute_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]
    settings = await client(functions.account.GetNotifySettingsRequest(peer=peer))
    muted = settings_muted(settings)
    mute_cache[key] = (muted, time.time() + MUTE_CACHE_SECONDS)
    return muted


async def is_muted(event):
    muted = await cached_muted(event.chat_id, types.InputNotifyPeer(await event.get_input_chat()))
    if muted is not None:
        return muted
    if event.is_private:
        default = await cached_muted("users", types.InputNotifyUsers())
    elif event.is_group:
        default = await cached_muted("chats", types.InputNotifyChats())
    else:
        default = await cached_muted("broadcasts", types.InputNotifyBroadcasts())
    return bool(default)


def describe(message):
    if message.message:
        return message.message
    if message.photo:
        return "🖼 Фото"
    if message.voice:
        return "🎤 Голосовое сообщение"
    if message.video_note:
        return "📹 Видеосообщение"
    if message.video:
        return "📹 Видео"
    if message.sticker:
        return "Стикер"
    if message.gif:
        return "GIF"
    if message.document:
        return "📎 Файл"
    return "Сообщение"


def send_to_bark(payload):
    request = urllib.request.Request(
        config.get("bark_server", "https://api.day.app").rstrip("/") + "/push",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


@client.on(events.NewMessage(incoming=True))
async def on_message(event):
    try:
        if event.is_channel and not event.is_group and not config.get("notify_channels", False):
            return
        if config.get("skip_muted", True) and await is_muted(event):
            return

        chat = await event.get_chat()
        sender = await event.get_sender()
        chat_title = utils.get_display_name(chat) or "Telegram"
        count = unread_counts.get(event.chat_id, 0) + 1
        payload = {
            "device_key": config["bark_key"],
            "id": notification_id(event.chat_id),
            "title": chat_title if count == 1 else f"{chat_title} ({count})",
            "body": "Новое сообщение" if config.get("hide_text", False) else describe(event.message)[:500],
            "group": str(event.chat_id),
            "icon": config.get("icon_url") or DEFAULT_ICON_URL,
            "url": f"{config.get('url_scheme', 'burmalda')}://openchat?id={event.chat_id}",
        }
        if event.is_group and sender is not None:
            payload["subtitle"] = utils.get_display_name(sender)
        await asyncio.to_thread(send_to_bark, payload)
        unread_counts[event.chat_id] = count
        save_unread_counts()
    except Exception as error:
        print(f"[{datetime.now():%H:%M:%S}] ошибка: {error!r}")


@client.on(events.MessageRead(inbox=True))
async def on_read(event):
    """The chat was read on any device: remove its notification from Bark."""
    try:
        if unread_counts.pop(event.chat_id, None) is None:
            return
        save_unread_counts()
        await asyncio.to_thread(send_to_bark, {
            "device_key": config["bark_key"],
            "id": notification_id(event.chat_id),
            "delete": "1",
        })
    except Exception as error:
        print(f"[{datetime.now():%H:%M:%S}] ошибка: {error!r}")


CODE_DELIVERY = {
    "SentCodeTypeApp": "сообщением в приложение Telegram: чат «Telegram» с синей галочкой. "
                       "Уведомления не будет, открой этот чат вручную (в Burmaldagram или официальном клиенте)",
    "SentCodeTypeSms": "по SMS",
    "SentCodeTypeCall": "голосовым звонком",
    "SentCodeTypeFlashCall": "сбросом звонка: код — последние цифры входящего номера",
    "SentCodeTypeMissedCall": "пропущенным звонком: код — последние цифры входящего номера",
    "SentCodeTypeEmailCode": "на почту, привязанную к аккаунту",
    "SentCodeTypeFragmentSms": "через Fragment",
    "SentCodeTypeFirebaseSms": "по SMS",
}


def print_code_delivery(sent):
    kind = type(getattr(sent, "type", None)).__name__
    print(f"Telegram отправил код {CODE_DELIVERY.get(kind, f'способом {kind}')}.")
    next_kind = type(getattr(sent, "next_type", None)).__name__
    if getattr(sent, "next_type", None) is not None:
        print(f"Если не пришёл, введи r: следующий способ — {CODE_DELIVERY.get(next_kind, next_kind)}.")


def show_login_qr(url, open_page):
    """Prints the QR code in the terminal and keeps a self-refreshing page with it next to the script."""
    import qrcode
    import qrcode.image.svg

    svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=12).to_string(encoding="unicode")
    QR_PAGE_PATH.write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="3"><title>Вход в релей</title>'
        '<body style="margin:0;background:#fff;display:flex;flex-direction:column;align-items:center;'
        'justify-content:center;min-height:100vh;font-family:sans-serif">'
        f'<div style="width:320px">{svg}</div>'
        '<p>Burmaldagram → Настройки → Устройства → Подключить устройство</p></body>',
        encoding="utf-8",
    )
    terminal_qr = qrcode.QRCode(border=1)
    terminal_qr.add_data(url)
    try:
        terminal_qr.print_ascii(invert=True)
    except UnicodeEncodeError:
        pass
    if open_page and hasattr(os, "startfile"):
        os.startfile(QR_PAGE_PATH)


async def login_with_qr():
    try:
        import qrcode  # noqa: F401
    except ImportError:
        sys.exit("Для входа по QR нужен пакет qrcode: python -m pip install qrcode")
    print("Открой Burmaldagram → Настройки → Устройства → Подключить устройство и отсканируй QR-код.")
    print(f"QR-код также открыт в браузере ({QR_PAGE_PATH.name}), он обновляется сам.")
    qr = await client.qr_login()
    open_page = True
    try:
        while True:
            show_login_qr(qr.url, open_page)
            open_page = False
            try:
                await qr.wait()
                return
            except asyncio.TimeoutError:
                await qr.recreate()
            except errors.SessionPasswordNeededError:
                await client.sign_in(password=getpass("Облачный пароль (двухэтапная проверка): "))
                return
    finally:
        QR_PAGE_PATH.unlink(missing_ok=True)


async def login():
    await client.connect()
    if await client.is_user_authorized():
        return
    if input("Вход: Enter — по QR-коду, 2 — по номеру телефона: ").strip() == "2":
        await login_with_code()
    else:
        await login_with_qr()


async def login_with_code():
    phone = input("Номер телефона в международном формате, например +380671234567: ").strip()
    sent = await client.send_code_request(phone)
    print_code_delivery(sent)
    while True:
        code = input("Код (или r — отправить заново): ").strip()
        if code.lower() == "r":
            sent = await client(functions.auth.ResendCodeRequest(phone_number=phone, phone_code_hash=sent.phone_code_hash))
            print_code_delivery(sent)
            continue
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            return
        except errors.SessionPasswordNeededError:
            await client.sign_in(password=getpass("Облачный пароль (двухэтапная проверка): "))
            return
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeEmptyError):
            print("Неверный код, попробуй ещё раз.")


async def main():
    try:
        await login()
    except errors.FloodWaitError as error:
        sys.exit(f"Telegram просит подождать {error.seconds} с перед новой попыткой входа.")
    except errors.ApiIdInvalidError:
        sys.exit("api_id или api_hash в config.json неверные.")
    except (errors.PhoneNumberInvalidError, errors.PhoneNumberBannedError) as error:
        sys.exit(f"Проблема с номером: {error}")
    me = await client.get_me()
    print(f"Релей запущен для {utils.get_display_name(me)}. Ctrl+C для остановки.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    finally:
        client.loop.run_until_complete(client.disconnect())
