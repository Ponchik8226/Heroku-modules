# meta developer: @tgmirass

import asyncio
import logging
import time

from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}д")
    if h: parts.append(f"{h}ч")
    if m: parts.append(f"{m}мин")
    parts.append(f"{s}сек")
    return " ".join(parts)


@loader.tds
class SpamHelper(loader.Module):
    """📨 Универсальный спам для любых чатов"""

    strings = {"name": "SpamHelper"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "antiflood_threshold", 50,
                "С какого количества сообщений включать антифлуд (чередование send/forward)",
            ),
        )
        self._slots: dict[int, dict] = {}
        self._next_slot_id = 1

    # ------------------------------------------------------------------ #
    #  БД                                                                  #
    # ------------------------------------------------------------------ #

    @property
    def _total_sent(self) -> int:
        return self.db.get(self.strings["name"], "total_sent", 0)

    @_total_sent.setter
    def _total_sent(self, value: int):
        self.db.set(self.strings["name"], "total_sent", value)

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    # ------------------------------------------------------------------ #
    #  Вспомогательные                                                     #
    # ------------------------------------------------------------------ #

    async def _save_to_fav(self, text: str) -> int:
        sent = await self.client.send_message("me", text)
        return sent.id

    async def _cleanup_fav(self, fav_id: int | None):
        if not fav_id:
            return
        try:
            await self.client.delete_messages("me", [fav_id])
        except Exception:
            pass

    async def _get_chat_name(self, chat_id: int) -> str:
        try:
            entity = await self.client.get_entity(chat_id)
            return (
                getattr(entity, "title", None)
                or getattr(entity, "first_name", None)
                or str(chat_id)
            )
        except Exception:
            return str(chat_id)

    async def _run_spam(
        self,
        slot_id: int,
        chat_id: int,
        topic_id: int | None,
        text: str,
        count: int,
        delay: float,
        reply_to: int | None,
    ):
        # в топиках антифлуд не используем — forward не поддерживает top_msg_id надёжно
        use_antiflood = count > int(self.config["antiflood_threshold"]) and not topic_id
        fav_id = None
        use_send = True
        flood_until = 0.0

        if use_antiflood:
            fav_id = await self._save_to_fav(text)
            self._slots[slot_id]["fav_id"] = fav_id

        try:
            sent = 0
            while sent < count:
                if slot_id not in self._slots:
                    break

                now = time.time()
                if now < flood_until:
                    await asyncio.sleep(flood_until - now)

                try:
                    if use_antiflood and not use_send:
                        await self.client.forward_messages(
                            entity=chat_id, messages=fav_id, from_peer="me"
                        )
                    else:
                        kwargs = {"message": text}
                        if reply_to:
                            kwargs["reply_to"] = reply_to
                        elif topic_id:
                            kwargs["reply_to"] = topic_id
                        await self.client.send_message(chat_id, **kwargs)

                    use_send = not use_send
                    self._slots[slot_id]["sent"] += 1
                    self._total_sent += 1
                    sent += 1

                except FloodWaitError as ex:
                    flood_until = time.time() + ex.seconds
                    await asyncio.sleep(ex.seconds + 1)
                    continue  # не засчитываем итерацию — сообщение не отправлено
                except RPCError:
                    if use_antiflood:
                        await self._cleanup_fav(fav_id)
                        fav_id = await self._save_to_fav(text)
                        self._slots[slot_id]["fav_id"] = fav_id
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("spam slot %s: %s", slot_id, exc)

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass
        finally:
            if use_antiflood:
                await self._cleanup_fav(fav_id)
            self._slots.pop(slot_id, None)

    # ------------------------------------------------------------------ #
    #  Команды                                                             #
    # ------------------------------------------------------------------ #

    @loader.command()
    async def spam(self, message: Message):
        """<количество> <задержка> <текст> — запустить спам (реплай = реплай-спам)"""
        args = utils.get_args_raw(message).strip()
        parts = args.split(maxsplit=2)

        if len(parts) < 3:
            return await utils.answer(message, "❌ <b>Формат:</b> <code>.spam 50 2 текст</code>")

        try:
            count = int(parts[0])
            delay = float(parts[1])
            text = parts[2]
        except ValueError:
            return await utils.answer(message, "❌ Количество и задержка должны быть числами.")

        if count < 1:
            return await utils.answer(message, "❌ Количество должно быть больше 0.")
        delay = max(0.1, delay)

        chat_id = message.chat_id

        topic_id = None
        if getattr(message, "reply_to", None) and getattr(message.reply_to, "forum_topic", False):
            topic_id = message.reply_to.reply_to_msg_id

        reply_to = None
        if message.is_reply:
            reply_msg = await message.get_reply_message()
            if reply_msg and not getattr(reply_msg.reply_to, "forum_topic", False):
                reply_to = reply_msg.id

        try:
            await message.delete()
        except Exception:
            pass

        slot_id = self._next_slot_id
        self._next_slot_id += 1
        chat_name = await self._get_chat_name(chat_id)

        # сначала создаём слот, потом таск — иначе _run_spam может дёрнуть
        # self._slots[slot_id] раньше чем он появится (race condition)
        self._slots[slot_id] = {
            "task": None,
            "chat_id": chat_id,
            "chat_name": chat_name,
            "text": text,
            "count": count,
            "delay": delay,
            "sent": 0,
            "fav_id": None,
            "started_at": time.time(),
        }
        self._slots[slot_id]["task"] = asyncio.create_task(
            self._run_spam(slot_id, chat_id, topic_id, text, count, delay, reply_to)
        )

    @loader.command()
    async def spamoff(self, message: Message):
        """[номер слота] — остановить спам. Без номера — остановить все"""
        args = utils.get_args_raw(message).strip()

        if not self._slots:
            return await utils.answer(message, "ℹ️ Нет активных спамов.")

        if args:
            try:
                slot_id = int(args)
            except ValueError:
                return await utils.answer(message, "❌ Укажи номер слота числом.")

            slot = self._slots.get(slot_id)
            if not slot:
                return await utils.answer(message, f"❌ Слот {slot_id} не найден.")

            slot["task"].cancel()
            try:
                await slot["task"]
            except (asyncio.CancelledError, Exception):
                pass
            await utils.answer(message, f"🛑 <b>Слот {slot_id} остановлен.</b>")
        else:
            stopped = len(self._slots)
            tasks = [s["task"] for s in self._slots.values() if s.get("task")]
            for t in tasks:
                t.cancel()
            for t in tasks:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            await utils.answer(message, f"🛑 <b>Остановлено слотов: {stopped}</b>")

    @loader.command()
    async def spamst(self, message: Message):
        """Показать активные слоты и статистику"""
        if not self._slots:
            return await utils.answer(
                message,
                f"ℹ️ Нет активных спамов.\n\n"
                f"📦 <b>Всего отправлено за всё время:</b> <code>{self._total_sent}</code>",
            )

        lines = [f"📨 <b>Активные слоты ({len(self._slots)}):</b>\n"]
        for slot_id, s in self._slots.items():
            text_preview = s["text"][:40] + ("..." if len(s["text"]) > 40 else "")
            elapsed = time.time() - s["started_at"]
            remaining = max(0, s["count"] - s["sent"]) * s["delay"]
            lines.append(
                f"<b>[{slot_id}]</b> {s['chat_name']}\n"
                f"   📨 <code>{utils.escape_html(text_preview)}</code>\n"
                f"   ✅ Отправлено: {s['sent']} / {s['count']}\n"
                f"   ⏱ Задержка: {s['delay']} сек\n"
                f"   🕐 Работает: {_fmt_time(elapsed)}\n"
                f"   ⏳ Осталось: ~{_fmt_time(remaining)}\n"
            )

        await utils.answer(
            message,
            "\n".join(lines) +
            f"\n📦 <b>Всего отправлено за всё время:</b> <code>{self._total_sent}</code>",
        )

    async def on_unload(self):
        tasks = [s["task"] for s in self._slots.values() if s.get("task")]
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass