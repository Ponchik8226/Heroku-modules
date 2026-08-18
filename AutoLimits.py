from .. import loader, utils
import asyncio
import re
import time
import io
import aiohttp
from telethon.tl.types import Message, ChatAdminRights, InputChatUploadedPhoto
from telethon import functions
from ..inline.types import InlineCall


AVATAR_URL = "https://x0.at/Qnlh.jpg"


@loader.tds
class AutoLimits(loader.Module):
    """Модуль для автоматического перевода лимитов в боте MineEvo"""

    strings = {"name": "AutoLimits"}

    async def client_ready(self):
        self.running = False
        self.cooldown_sec = 0
        self.got_cooldown = False
        self.got_success = False
        self.got_no_money = False
        self.limitss = ""
        self.last_send = 0.0
        self._evo_channel = None

        dly = self.get("dly")
        if dly is None or float(dly) < 60:
            self.set("dly", 60.0)
        if self.get("achk") is None:
            self.set("achk", False)
        if self.get("achk_every") is None:
            self.set("achk_every", 10)

        found_old = None
        found_new = None
        async for dialog in self._client.iter_dialogs():
            title = getattr(dialog.entity, 'title', '')
            if title == 'mlimits':
                found_old = dialog.entity
            elif title == 'Evo limits':
                found_new = dialog.entity
            if found_old and found_new:
                break

        if found_new is not None:
            self._evo_channel = found_new
        elif found_old is not None:
            self._evo_channel = found_old
            try:
                await self._client(functions.channels.EditTitleRequest(
                    channel=self._evo_channel, title='Evo limits'
                ))
            except Exception:
                pass
            await self._set_avatar(self._evo_channel)
        else:
            self._evo_channel, _ = await utils.asset_channel(
                self._client, "EvoLim", "Группа для работы модуля AutoLimits",
                silent=True, archive=True, _folder="hikka",
            )
            try:
                await self._client(functions.channels.InviteToChannelRequest(
                    self._evo_channel, ["@mine_evo_bot"]
                ))
            except Exception:
                pass
            try:
                await self._client(functions.channels.EditAdminRequest(
                    channel=self._evo_channel,
                    user_id="@mine_evo_bot",
                    admin_rights=ChatAdminRights(ban_users=True, post_messages=True, edit_messages=True),
                    rank="EVO",
                ))
            except Exception:
                pass
            await self._set_avatar(self._evo_channel)

    async def _set_avatar(self, channel):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(AVATAR_URL) as resp:
                    photo_bytes = await resp.read()
            uploaded = await self._client.upload_file(
                io.BytesIO(photo_bytes), file_name="avatar.jpg"
            )
            await self._client(functions.channels.EditPhotoRequest(
                channel=channel,
                photo=InputChatUploadedPhoto(file=uploaded)
            ))
        except Exception:
            pass

    def _format_time(self, ss: int) -> str:
        ss = int(ss)
        sss = ss % 60
        mmm = (ss // 60) % 60
        hhh = (ss // 3600) % 24
        ddd = (ss // 86400) % 7
        www = round((ss // 604800) % 4.28)
        mmmth = (ss // 2592000) % 12
        y = ss // 31536000
        if y > 0:
            return f"{y}г. {mmmth}мес. {www}нед. {ddd}д. {hhh}ч. {mmm}мин. {sss}с."
        if mmmth > 0:
            return f"{mmmth}мес. {www}нед. {ddd}д. {hhh}ч. {mmm}мин. {sss}с."
        if www > 0:
            return f"{www}нед. {ddd}д. {hhh}ч. {mmm}мин. {sss}с."
        if ddd > 0:
            return f"{ddd}д. {hhh}ч. {mmm}мин. {sss}с."
        if hhh > 0:
            return f"{hhh}ч. {mmm}мин. {sss}с."
        if mmm > 0:
            return f"{mmm}мин. {sss}с."
        return f"{sss}с."

    async def _check_limit(self, player: str, status_msg=None) -> bool:
        limitp = self.get("Sum")
        while True:
            self.got_cooldown = False
            self.got_success = False
            self.got_no_money = False
            self.limitss = ""
            self.last_send = time.time()
            await self._client.send_message(self._evo_channel, f"Перевести {player} {limitp}")

            for _ in range(10):
                await asyncio.sleep(0.5)
                if self.got_cooldown or self.limitss or self.got_success or self.got_no_money:
                    break

            if self.got_no_money:
                return False

            if self.got_cooldown:
                elapsed = time.time() - self.last_send
                wait = max(0, self.cooldown_sec - elapsed)
                if status_msg:
                    await status_msg.edit(
                        f"<emoji document_id=5981043230160981261>⏱</emoji> <b>Кулдаун {self.cooldown_sec}с. — жду перед проверкой лимита...</b>"
                    )
                await asyncio.sleep(wait)
                self.got_cooldown = False
                continue

            if self.limitss:
                return True

            if self.got_success:
                # Лимит игрока выше суммы проверки проверочная сумма прошла как реальный перевод, продолжаем переводить ею же
                self.limitss = limitp
                return True

            saved = self.db.get(self.name, "limitss", "")
            if saved:
                self.limitss = saved
                return True

            return False

    async def _wait_after_transfer(self):
        for _ in range(10):
            await asyncio.sleep(0.5)
            if self.got_cooldown or self.got_no_money:
                break

        if self.got_no_money:
            return

        elapsed = time.time() - self.last_send
        if self.got_cooldown:
            wait = max(0, self.cooldown_sec - elapsed)
        else:
            wait = max(0, self.get("dly") - elapsed)

        await asyncio.sleep(wait)

    def _cfg_text(self) -> str:
        achk = self.get("achk")
        achk_every = self.get("achk_every")
        achk_status = f"каждые <code>{achk_every}</code> переводов" if achk else "<i>выключена</i>"
        return (
            f"<emoji document_id=5981043230160981261>⏱</emoji> <b>Задержка:</b> <code>{self.get('dly')}</code> сек.\n"
            f"<emoji document_id=5215239948420003628>💵</emoji> <b>Сумма проверки:</b> <code>{self.get('Sum')}</code>\n"
            f"<emoji document_id=5416117059207572332>➡️</emoji> <b>Перевод:</b> <i>{'Включён' if self.running else 'Выключен'}</i>\n"
            f"🔄 <b>Авто-проверка лимита:</b> {achk_status}"
        )

    def _cfg_markup(self) -> list:
        return [
            [
                {"text": "⏱ Задержка", "callback": self.idly},
                {"text": "💵 Сумма проверки", "callback": self.lsm},
            ],
            [{"text": "🔄 Авто-проверка лимита", "callback": self.iachk}],
            [{"text": "🔻 Закрыть", "action": "close"}],
        ]

    async def _run_loop(self, player, total, done, message, status_msg=None):
        since_last_chk = 0
        limits = total - done

        while self.running and limits > 0:
            if self.get("achk") and since_last_chk >= self.get("achk_every"):
                since_last_chk = 0
                if not await self._check_limit(player):
                    self.running = False
                    no_money_msg = (
                        f"<emoji document_id=5240241223632954241>🚫</emoji> <b>Недостаточно денег для перевода игроку <code>{player}</code>!\n"
                        f"Переведено: <code>{done}</code>/<code>{total}</code></b>"
                    )
                    if status_msg:
                        return await status_msg.edit(no_money_msg)
                    return await utils.answer(message, no_money_msg)
                self.db.set(self.name, "limitss", self.limitss)
                await self._wait_after_transfer()
                if not self.running:
                    return

            self.got_cooldown = False
            self.got_no_money = False
            self.last_send = time.time()
            await self._client.send_message(self._evo_channel, f"Перевести {player} {self.limitss}")
            limits -= 1
            done += 1
            since_last_chk += 1
            self.db.set(self.name, "limitsr", done)
            self.db.set(self.name, "limmm", limits)

            await self._wait_after_transfer()

            if self.got_no_money:
                self.running = False
                no_money_msg = (
                    f"<emoji document_id=5240241223632954241>🚫</emoji> <b>Недостаточно денег для перевода игроку <code>{player}</code>!\n"
                    f"Переведено: <code>{done}</code>/<code>{total}</code></b>"
                )
                if status_msg:
                    return await status_msg.edit(no_money_msg)
                return await utils.answer(message, no_money_msg)

        if not self.running:
            return

        done_msg = (
            f"<emoji document_id=5332533929020761310>✅</emoji> <b>Все лимиты игроку <code>{player}</code> переведены: <code>{total}</code></b>"
        )
        if status_msg:
            await status_msg.edit(done_msg)
        else:
            await utils.answer(message, done_msg)

    @loader.command()
    async def mlp(self, message):
        """- Перевод лимитов\n[ник игрока] [количество лимитов]"""
        args = utils.get_args_split_by(message, " ")
        cmd = f'{utils.escape_html(self.get_prefix())}mlp'

        if not args:
            return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nУкажите ник игрока и количество лимитов.\nФормат: <code>{cmd} [ник] [количество]</code></b>")
        if len(args) == 1:
            return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nУкажите количество лимитов.\nФормат: <code>{cmd} [ник] [количество]</code></b>")
        if len(args) > 2:
            return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nСлишком много аргументов.\nФормат: <code>{cmd} [ник] [количество]</code></b>")
        if not self.get("Sum"):
            return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nУстановите сумму проверки: <code>{utils.escape_html(self.get_prefix())}lscfg sm [сумма]</code></b>")

        player, total = args[0], int(args[1])
        self.db.set(self.name, "player", player)
        self.db.set(self.name, "limitsf", str(total))
        self.db.set(self.name, "limitsr", 0)
        self.db.set(self.name, "limmm", total)

        status_msg = await utils.answer(message, f"<emoji document_id=5215239948420003628>💵</emoji> <b>Проверяю лимит у бота...</b>")

        if not await self._check_limit(player, status_msg):
            if self.got_no_money:
                return await status_msg.edit(
                    f"<emoji document_id=5240241223632954241>🚫</emoji> <b>Недостаточно денег для перевода игроку <code>{player}</code>!</b>"
                )
            return await status_msg.edit("🚫 <b>Не удалось получить сумму лимита от бота</b>")

        self.db.set(self.name, "limitss", self.limitss)

        await status_msg.edit(
            f"<emoji document_id=5215239948420003628>💵</emoji> <b>Лимит: <code>{self.limitss}</code> — начинаю переводы через минуту...</b>"
        )
        await self._wait_after_transfer()

        self.running = True
        eta = self._format_time(total * self.get("dly"))
        await status_msg.edit(
            f"<emoji document_id=5215239948420003628>💵</emoji> <b>Начинаю перевод лимитов игроку <code>{player}</code>: {total}</b>\n"
            f"<emoji document_id=5981043230160981261>⏱</emoji> <b>Примерно:</b> <i>{eta}</i>"
        )

        await self._run_loop(player, total, 0, message, status_msg)

    @loader.command()
    async def mstop(self, message):
        """- Остановить перевод лимитов"""
        self.running = False
        await utils.answer(message, "<emoji document_id=5447644880824181073>⚠️</emoji> Перевод лимитов остановлен")

    @loader.command()
    async def mcon(self, message):
        """- Продолжить перевод лимитов после остановки"""
        player = self.db.get(self.name, "player", "")
        limitsf = self.db.get(self.name, "limitsf", 0)
        done = int(self.db.get(self.name, "limitsr", 0))
        total = int(limitsf)
        remaining = total - done
        cmd = f'{utils.escape_html(self.get_prefix())}mcon'

        if not self.get("Sum"):
            return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nУстановите сумму проверки</b>")
        if remaining <= 0:
            return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nВсе лимиты уже переведены</b>")

        self.limitss = self.db.get(self.name, "limitss", "")
        self.running = True
        eta = self._format_time(remaining * self.get("dly"))

        await utils.answer(message,
            f"<emoji document_id=5215239948420003628>💵</emoji> <b>Продолжаю перевод лимитов игроку <code>{player}</code>\n"
            f"Осталось: <code>{remaining}</code></b>\n"
            f"<emoji document_id=5981043230160981261>⏱</emoji> <b>Примерно:</b> <i>{eta}</i>"
        )

        await self._run_loop(player, total, done, message)

    @loader.command()
    async def lchk(self, message):
        """- Прогресс перевода лимитов"""
        player = self.db.get(self.name, "player", "")
        done = int(self.db.get(self.name, "limitsr", 0))
        total = int(self.db.get(self.name, "limitsf", 0))
        remaining = total - done
        t = self._format_time(remaining * self.get("dly"))

        await utils.answer(message,
            f"<emoji document_id=5215239948420003628>💵</emoji> <b>Игрок <code>{player}</code> | Переведено: <code>{done}</code>/<code>{total}</code></b>\n"
            f"<emoji document_id=5981043230160981261>⏱</emoji> <b>Примерно:</b> <i>{t}</i>"
        )

    @loader.command()
    async def lscfg(self, message: Message):
        """- Настройки модуля"""
        args = utils.get_args_split_by(message, " ")
        cmd = f'{utils.escape_html(self.get_prefix())}lscfg'

        if not args or len(args) != 2:
            return await utils.answer(message,
                f"<emoji document_id=5240241223632954241>📖</emoji> <b>Справка | <code>{cmd}</code>\n\n"
                f"Доступные параметры:\n"
                f"▫️ <code>{cmd} dly [сек]</code> — задержка между переводами (мин. 60 сек.)\n"
                f"▫️ <code>{cmd} sm [сумма]</code> — сумма для проверки лимита\n"
                f"▫️ <code>{cmd} achk [N]</code> — проверка лимита каждые N переводов (мин. 2)</b>"
            )

        pp, zz = args[0], args[1]

        if pp == "dly":
            try:
                val = float(zz)
            except ValueError:
                return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nУкажите число</b>")
            if val < 60:
                return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nМинимум — 60 секунд</b>")
            self.set("dly", val)
            return await utils.answer(message, f"<emoji document_id=5332533929020761310>✅</emoji> <b>Задержка: <code>{val}</code> сек.</b>")

        if pp == "sm":
            self.set("Sum", zz)
            return await utils.answer(message, f"<emoji document_id=5332533929020761310>✅</emoji> <b>Сумма проверки: <code>{zz}</code></b>")

        if pp == "achk":
            try:
                val = int(zz)
            except ValueError:
                return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nУкажите целое число</b>")
            if val < 2:
                return await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nМинимум — 2 перевода</b>")
            self.set("achk_every", val)
            return await utils.answer(message, f"<emoji document_id=5332533929020761310>✅</emoji> <b>Авто-проверка: каждые <code>{val}</code> переводов</b>")

        await utils.answer(message, f"🚫 <b>Ошибка | <code>{cmd}</code>\nДоступные параметры: <code>dly</code>, <code>sm</code>, <code>achk</code></b>")

    @loader.command()
    async def mlcfg(self, message):
        """- Конфиг модуля"""
        await self.inline.form(
            text=self._cfg_text(),
            message=message,
            reply_markup=self._cfg_markup(),
        )

    async def ibackl(self, call: InlineCall):
        await call.edit(text=self._cfg_text(), reply_markup=self._cfg_markup())

    async def idly(self, call: InlineCall):
        await call.edit(
            text=(
                f"<emoji document_id=5981043230160981261>⏱</emoji> <b>Текущая задержка: <code>{self.get('dly')}</code> сек.</b>\n\n"
                f"Чтобы изменить:\n<code>{self.get_prefix()}lscfg dly [секунды]</code>\n<i>Минимум — 60 секунд</i>"
            ),
            reply_markup=[[{"text": "◀️ Назад", "callback": self.ibackl}]],
        )

    async def lsm(self, call: InlineCall):
        await call.edit(
            text=(
                f"<emoji document_id=5215239948420003628>💵</emoji> <b>Текущая сумма проверки: <code>{self.get('Sum')}</code></b>\n\n"
                f"Чтобы изменить:\n<code>{self.get_prefix()}lscfg sm [сумма]</code>"
            ),
            reply_markup=[[{"text": "◀️ Назад", "callback": self.ibackl}]],
        )

    async def iachk(self, call: InlineCall):
        achk = self.get("achk")
        achk_every = self.get("achk_every")
        status = f"<i>Включена</i> — каждые <code>{achk_every}</code> переводов" if achk else "<i>Выключена</i>"
        await call.edit(
            text=(
                f"🔄 <b>Авто-проверка лимита</b>\n"
                f"Статус: {status}\n\n"
                f"Модуль перепроверяет актуальный лимит каждые N переводов.\n"
                f"Минимум — <b>2 перевода</b>.\n\n"
                f"Чтобы задать интервал:\n"
                f"<code>{self.get_prefix()}lscfg achk [число]</code>"
            ),
            reply_markup=[
                [{"text": "✅ Включить" if not achk else "🔴 Выключить", "callback": self.toggle_achk}],
                [{"text": "◀️ Назад", "callback": self.ibackl}],
            ],
        )

    async def toggle_achk(self, call: InlineCall):
        self.set("achk", not self.get("achk"))
        await self.iachk(call)

    @loader.watcher()
    async def lim(self, message):
        sender_id = getattr(message, 'sender_id', None)
        if sender_id != 5522271758:
            return

        if "недостаточно денег" in message.raw_text:
            self.got_no_money = True

        if "можно перевести максимум" in message.raw_text:
            match = re.search(r"можно перевести максимум(.*?)$", message.raw_text, re.DOTALL)
            if match:
                self.limitss = match.group(1).replace("$", "").strip()
                self.db.set(self.name, "limitss", self.limitss)

        if "✔" in message.raw_text and "перевел" in message.raw_text:
            self.got_success = True

        if "осталось подождать" in message.raw_text:
            seconds = 0
            m = re.search(r"(\d+)м\.", message.raw_text)
            if m:
                seconds += int(m.group(1)) * 60
            s = re.search(r"(\d+)с\.", message.raw_text)
            if s:
                seconds += int(s.group(1))
            if seconds > 0:
                self.cooldown_sec = seconds
                self.got_cooldown = True
