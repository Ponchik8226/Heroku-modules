from .. import loader, utils

@loader.tds
class MsgEVO(loader.Module):
    """Модуль для отправки запросов боту @mine_evo_bot"""
    strings = {"name": "MsgEVO"}

    @loader.command(ru_doc="[запрос] — Отправить запрос боту")
    async def evocmd(self, message):
        """[запрос] — Отправить запрос боту"""
        args = utils.get_args_raw(message)

        if not args:
            return await utils.answer(message, "<b>❌ Укажи запрос:</b> <code>.evo [текст]</code>")

        try:
            async with self._client.conversation("@mine_evo_bot", timeout=15) as conv:
                await conv.send_message(args)
                response = await conv.get_response()
        except Exception as e:
            return await utils.answer(message, f"<b>⚠️ Ошибка:</b> <code>{utils.escape_html(str(e))}</code>")

        await utils.answer(
            message,
            f"<emoji document_id=5357121491508928442>👀</emoji> <b>Запрос:</b>\n"
            f"<blockquote>{utils.escape_html(args)}</blockquote>\n\n"
            f"<emoji document_id=5309832892262654231>🤖</emoji> <b>Ответ:</b>\n"
            f"<blockquote>{response.text}</blockquote>"
        )