# meta developer: @tgmirass

import ast
import math
import re
from decimal import ROUND_DOWN, Decimal, getcontext

from telethon.tl.types import Message

from .. import loader, utils

getcontext().prec = 50
_MAX_RESULT_BITS = 1_000_000


class _PowTransformer(ast.NodeTransformer):
    """Заменяет все ** в AST на вызов _safe_pow."""

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Pow):
            return ast.Call(
                func=ast.Name(id="_safe_pow", ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
        return node


def _safe_pow(base, exp):
    """Вычисляет base**exp, но заранее оценивает размер результата."""
    try:
        base_f = abs(float(base))
        exp_f = float(exp)
        if base_f > 1 and exp_f > 0 and exp_f * math.log2(base_f) > _MAX_RESULT_BITS:
            raise ValueError("Результат слишком велик для вычисления")
    except OverflowError:
        raise ValueError("Результат слишком велик для вычисления")
    return base**exp


@loader.tds
class CalcHelper(loader.Module):
    """🧮 Калькулятор с поддержкой суффиксов к/k"""

    strings = {"name": "CalcHelper"}

    @staticmethod
    def _replace_suffixes(expr: str) -> str:
        expr = expr.replace("^", "**")
        expr = expr.lower().replace("k", "к")

        def replacer(m):
            num = m.group(1)
            power = len(m.group(2))
            return f"({num}*{1000**power})"

        return re.sub(r"([\d.]+)(к+)", replacer, expr)

    @staticmethod
    def _format_result(value) -> str:
        is_negative = value < 0
        abs_val = abs(value)

        # e-нотация
        if isinstance(value, int):
            s = str(abs_val)
            exp = len(s) - 1
            if exp == 0:
                e_str = s
            else:
                frac = s[1:7].rstrip("0")
                e_str = (f"{s[0]}.{frac}" if frac else s[0]) + f"e+{exp}"
            if is_negative:
                e_str = "-" + e_str
        else:
            e_str = f"{value:.6e}"
            e_str = re.sub(r"(\.\d*?)0+(e)", r"\1\2", e_str)
            e_str = re.sub(r"\.(e)", r"\1", e_str)
            e_str = re.sub(r"e([+-])0*(\d)", r"e\1\2", e_str)

        # полное число (до 24 цифр)
        full = None
        if isinstance(value, int) and len(str(abs_val)) <= 24:
            s = str(abs_val)
            groups = []
            while len(s) > 3:
                groups.append(s[-3:])
                s = s[:-3]
            groups.append(s)
            full = ("-" if is_negative else "") + " ".join(reversed(groups))
        elif not isinstance(value, int) and abs_val < 10**15:
            if float(value) == int(value):
                return CalcHelper._format_result(int(value))
            full_str = f"{value:,.6f}".replace(",", " ").rstrip("0").rstrip(".")
            if full_str not in ("0", "-0", ""):
                full = full_str

        # сокращённое
        suffixes = [
            (10**100, "гугол"),
            (10**99,  "дуотригинтиллион"),
            (10**96,  "унтригинтиллион"),
            (10**93,  "тригинтиллион"),
            (10**90,  "новемвигинтиллион"),
            (10**87,  "октовигинтиллион"),
            (10**84,  "септвигинтиллион"),
            (10**81,  "сексвигинтиллион"),
            (10**78,  "квинвигинтиллион"),
            (10**75,  "кватуорвигинтиллион"),
            (10**72,  "тревигинтиллион"),
            (10**69,  "дуовигинтиллион"),
            (10**66,  "унвигинтиллион"),
            (10**63,  "вигинтиллион"),
            (10**60,  "новемдециллион"),
            (10**57,  "октодециллион"),
            (10**54,  "септендециллион"),
            (10**51,  "сексдециллион"),
            (10**48,  "квиндециллион"),
            (10**45,  "кватуордециллион"),
            (10**42,  "тредециллион"),
            (10**39,  "дуодециллион"),
            (10**36,  "ундециллион"),
            (10**33,  "дециллион"),
            (10**30,  "нониллион"),
            (10**27,  "октиллион"),
            (10**24,  "септиллион"),
            (10**21,  "секстиллион"),
            (10**18,  "квинтиллион"),
            (10**15,  "квадриллион"),
            (10**12,  "трлн"),
            (10**9,   "млрд"),
            (10**6,   "млн"),
            (10**3,   "тыс"),
        ]

        short = None
        for threshold, name in suffixes:
            if abs_val >= threshold:
                if isinstance(value, int):
                    whole = abs_val // threshold
                    if whole >= 10**15:
                        break  # слишком большое только e-нотация
                    frac_int = (abs_val % threshold) * 1000 // threshold
                    d_str = str(whole) if frac_int == 0 else f"{whole}.{frac_int:03d}".rstrip("0")
                    if is_negative:
                        d_str = "-" + d_str
                else:
                    d = Decimal(str(round(value, 6))) / Decimal(threshold)
                    d = d.quantize(Decimal("0.001"), rounding=ROUND_DOWN)
                    d_str = f"{d:f}".rstrip("0").rstrip(".")
                short = f"{d_str} {name}"
                break

        lines = []
        if full:
            lines.append(f"🔢 <code>{full}</code>")
        if short:
            lines.append(f"📊 <code>{short}</code>")
        if full is None:  # e-нотация нужна только когда полное число не помещается
            lines.append(f"🔬 <code>{e_str}</code>")
        return "\n".join(lines)

    @loader.command()
    async def c(self, message: Message):
        """[выражение] — вычислить. Суффиксы: к/k=×1000, кк=×1млн, ккк=×1млрд..."""
        raw = utils.get_args_raw(message).strip()
        if not raw:
            return await utils.answer(
                message,
                "🧮 <b>Калькулятор</b>\n\n"
                "<b>Использование:</b> <code>.c выражение</code>\n\n"
                "<b>Примеры:</b>\n"
                "<code>.c 50ккк * 60600</code>\n"
                "<code>.c 1кк + 500к</code>\n"
                "<code>.c (2к + 3к) * 4кк</code>\n"
                "<code>.c 10^100</code>\n\n"
                "<b>Суффиксы:</b> к/k — ×1000 за каждую букву\n"
                "<b>Степень:</b> ** или ^\n"
                "<b>Функции:</b> sqrt, log, log10, floor, ceil, pi, e",
            )

        original = raw
        try:
            expr = self._replace_suffixes(raw)

            tree = ast.parse(expr, mode="eval")
            tree = _PowTransformer().visit(tree)
            ast.fix_missing_locations(tree)
            code = compile(tree, "<string>", "eval")

            allowed = {
                "__builtins__": {},
                "_safe_pow": _safe_pow,
                "abs": abs, "round": round, "min": min, "max": max,
                "sqrt": math.sqrt, "pow": pow, "log": math.log,
                "log10": math.log10, "floor": math.floor, "ceil": math.ceil,
                "pi": math.pi, "e": math.e,
            }
            result = eval(code, allowed)  # noqa: S307

            if not isinstance(result, (int, float)):
                raise ValueError("Результат не является числом")
            if isinstance(result, float):
                if math.isnan(result):
                    raise ValueError("Результат: NaN")
                if math.isinf(result):
                    raise ValueError("Результат: бесконечность")
                if result == int(result) and abs(result) < 10**300:
                    result = int(result)

            formatted = self._format_result(result)
            await utils.answer(
                message,
                f"🧮 <code>{utils.escape_html(original)}</code>\n\n"
                f"<blockquote>{formatted}</blockquote>",
            )

        except ZeroDivisionError:
            await utils.answer(
                message,
                f"❌ <b>Деление на ноль</b>\n<code>{utils.escape_html(original)}</code>",
            )
        except Exception as exc:
            await utils.answer(
                message,
                f"❌ <b>Ошибка:</b> <code>{utils.escape_html(str(exc))}</code>\n"
                f"Выражение: <code>{utils.escape_html(original)}</code>",
            )
