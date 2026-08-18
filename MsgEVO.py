import asyncio
from telethon.errors import YouBlockedUserError
from .. import loader, utils


@loader.tds
class MsgEvo(loader.Module):
    """Модуль для отправки запросов боту @mine_evo_bot"""

    strings = {
        "name": "MsgEvo",
        "no_args": "<b>❌ Укажи запрос:</b> <code>.evo [текст]</code>",
        "loading": "<b>⏳ Отправляю запрос боту...</b>",
        "timeout": (
            "<b>⚠️ Бот не ответил на запрос.</b>\n"
            "<i>Возможно, такой команды нет или бот временно недоступен.</i>"
        ),
        "blocked": (
            "<b>❌ Вы заблокировали бота @mine_evo_bot.</b>\n"
            "<i>Разблокируйте его, чтобы использовать модуль.</i>"
        ),
        "error": "<b>⚠️ Ошибка:</b> <code>{}</code>",
        "result": (
            "👀 <b>Запрос:</b>\n"
            "<blockquote>{}</blockquote>\n\n"
            "🤖 <b>Ответ:</b>\n"
            "<blockquote>{}</blockquote>"
        ),
    }

    @loader.command(ru_doc="[запрос] — Отправить запрос боту mine_evo_bot")
    async def evocmd(self, message):
        """[запрос] — Отправить запрос боту"""
        args = utils.get_args_raw(message)

        if not args:
            return await utils.answer(message, self.strings("no_args"))

        message = await utils.answer(message, self.strings("loading"))

        try:
            async with self._client.conversation("@mine_evo_bot", timeout=6) as conv:
                await conv.send_message(args)
                response = await conv.get_response()
        except asyncio.TimeoutError:
            return await utils.answer(message, self.strings("timeout"))
        except YouBlockedUserError:
            return await utils.answer(message, self.strings("blocked"))
        except Exception as e:
            return await utils.answer(
                message, self.strings("error").format(utils.escape_html(str(e)))
            )

        safe_args = utils.escape_html(args)
        bot_response = response.text or "[Бот прислал медиа или сообщение без текста]"

        await utils.answer(
            message,
            self.strings("result").format(safe_args, bot_response),
        )
