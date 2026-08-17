# meta developer: @tgmirass

from hikka import loader, utils
import asyncio
from datetime import datetime, timedelta
from telethon.errors import FloodWaitError

@loader.tds
class DelayedMessages(loader.Module):
    """Автоматическая отправка отложенных сообщений через указанные интервалы"""
    strings = {"name": "Отложка"}

    MAX_MESSAGES = 50
    MAX_INTERVAL = 43200  # 30 дней в минутах
    MIN_INTERVAL = 1

    @loader.command(ru_doc="Запланировать отправку: .pp [интервал мин] [количество] [сообщение]")
    async def ppcmd(self, message):
        """Отправка сообщений через заданные интервалы"""
        args = utils.get_args_raw(message).split(maxsplit=2)

        if len(args) != 3 or not args[0].isdigit() or not args[1].isdigit():
            return await utils.answer(
                message,
                "<b>❌ Использование:</b> <code>.pp [интервал мин] [количество] [сообщение]</code>"
            )

        interval, count, text = int(args[0]), int(args[1]), args[2].strip()
        chat_id = message.chat_id

        if not text:
            return await utils.answer(message, "<b>❌ Текст не может быть пустым.</b>")
        if interval < self.MIN_INTERVAL:
            return await utils.answer(message, f"⚠️ <b>Минимальный интервал:</b> {self.MIN_INTERVAL} мин.")
        if interval > self.MAX_INTERVAL:
            return await utils.answer(message, f"⚠️ <b>Максимальный интервал:</b> {self.MAX_INTERVAL // 1440} дней.")
        if count > self.MAX_MESSAGES:
            return await utils.answer(message, f"⚠️ <b>Максимум сообщений:</b> {self.MAX_MESSAGES}.")

        has_html = any(tag in text for tag in ("<b>", "<i>", "<code>", "<a "))
        has_md = any(s in text for s in ("**", "__", "`"))
        parse_mode = "html" if has_html else ("markdown" if has_md else None)

        preview = text[:50] + ("..." if len(text) > 50 else "")
        await utils.answer(
            message,
            f"📅 <b>Запланировано:</b> {count} сообщ.\n"
            f"⏳ <b>Интервал:</b> {interval} мин.\n"
            f"💬 <b>Текст:</b> {utils.escape_html(preview)}\n"
            f"🕒 <b>Старт:</b> {datetime.utcnow().strftime('%H:%M:%S')} UTC"
        )

        start_time = datetime.utcnow()
        i = 0
        while i < count:
            send_time = start_time + timedelta(minutes=interval * i)
            try:
                if i == 0:
                    await message.client.send_message(chat_id, text, parse_mode=parse_mode)
                else:
                    await message.client.send_message(chat_id, text, schedule=send_time, parse_mode=parse_mode)
                i += 1
            except FloodWaitError as e:
                await utils.answer(message, f"⏳ <b>FloodWait:</b> жду {e.seconds} сек...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                err = str(e).lower()
                if any(s in err for s in ("cannot schedule more", "you cannot schedule", "schedule more messages")):
                    return await utils.answer(
                        message,
                        "🚫 <b>Лимит Telegram на отложенные сообщения исчерпан.</b>\n"
                        "Удали старые или уменьши количество."
                    )
                return await utils.answer(
                    message, f"⚠️ <b>Ошибка:</b> <code>{utils.escape_html(str(e))}</code>"
                )