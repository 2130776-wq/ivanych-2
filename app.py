import os
import re
import json
from typing import List, Dict, Any, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

# ====== OpenAI (новый SDK) ======
# Работает через переменную окружения OPENAI_API_KEY
try:
    from openai import OpenAI
    _client: Optional[OpenAI] = OpenAI()  # возьмёт ключ из окружения
except Exception:
    _client = None


app = Flask(__name__)
CORS(app)


# ====== Загрузка базы (1.json) ======
DATA: List[Dict[str, Any]] = []


def load_data():
    """Безопасно загрузить 1.json в список словарей."""
    global DATA
    DATA = []
    try:
        path = os.path.join(os.path.dirname(__file__), "1.json")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, list):
            DATA = raw
        elif isinstance(raw, dict):
            # если корень — словарь, соберём все списки/записи из values
            flat: List[Dict[str, Any]] = []
            for v in raw.values():
                if isinstance(v, list):
                    flat.extend(v)
                elif isinstance(v, dict):
                    flat.append(v)
            DATA = flat if flat else [raw]
        else:
            DATA = []
    except Exception as e:
        app.logger.error(f"[load_data] Ошибка загрузки 1.json: {e}")
        DATA = []


# ====== Утилиты ======
ARTICLE_RE = re.compile(r"^(100|104|106|108|250)-\d{3}$", re.IGNORECASE)

def norm(s: Any) -> str:
    """Нормализуем строку: убираем пробелы, приводим дефисы, lower()."""
    if not isinstance(s, str):
        s = str(s)
    s = s.strip()
    s = s.replace("—", "-").replace("–", "-").replace("‑", "-")
    s = re.sub(r"\s+", "", s)
    return s.lower()

def record_text(rec: Dict[str, Any]) -> str:
    """Склеим все строковые значения записи для свободного поиска."""
    parts: List[str] = []
    def collect(v):
        if isinstance(v, dict):
            for vv in v.values():
                collect(vv)
        elif isinstance(v, list):
            for vv in v:
                collect(vv)
        else:
            parts.append(str(v))
    collect(rec)
    return " | ".join(parts)

def find_by_article(code_or_text: str) -> Optional[Dict[str, Any]]:
    """
    Поиск записи в DATA:
    - сначала по "типичным" ключам артикула: article, art, sku, код, артикул
    - если не нашли — в склеенной строке записи
    """
    q = norm(code_or_text)
    if not q:
        return None

    candidate_keys = {"article", "art", "sku", "код", "артикул", "code"}
    for rec in DATA:
        for k, v in rec.items():
            if k.lower() in candidate_keys and norm(v) == q:
                return rec

    for rec in DATA:
        if q in norm(record_text(rec)):
            return rec

    return None


# ====== Health ======
@app.route("/health", methods=["GET"])
def health():
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    return jsonify({"ok": True, "records": len(DATA), "openai_key": has_key})


# ====== Основной чат ======
@app.route("/chat", methods=["POST"])
def chat():
    try:
        payload = request.get_json(silent=True) or {}
        user_message = (payload.get("message") or "").strip()
        if not user_message:
            return jsonify({"reply": "Пустой запрос."})

        q = user_message.lower()
        app.logger.info(f"[CHAT] input='{user_message}' norm='{norm(user_message)}'")

        # ---------- БЫСТРЫЕ ГОТОВЫЕ ОТВЕТЫ (1–9) ----------
        # 1) доставка / отгрузка
        if re.search(r"\b(доставк\w*|отправ\w*|отгруз\w*|грузите)\b", q, re.IGNORECASE):
            return jsonify({
                "reply": "Доставка ТК Деловые Линии: до терминала в городе отгрузки бесплатно, далее за ваш счёт. Или СДЭК."
            })

        # 2) есть в наличии
        if re.search(r"\b(есть в наличии|в наличии)\b", q, re.IGNORECASE):
            return jsonify({
                "reply": "Да, есть в наличии, хотите счет? Если ДА — заполните заявку и направьте нам по электронной почте вместе с карточкой предприятия, почта: info@salpi.ru. Если НЕТ — напрасно, коллега)"
            })

        # 3) минимальное количество
        if re.search(r"\b(минимальн\w* количеств\w*)\b", q, re.IGNORECASE):
            return jsonify({"reply": "В основном кратно 10 шт."})

        # 4) скидка / дисконт
        if re.search(r"\b(скидк\w*|дисконт)\b", q, re.IGNORECASE):
            return jsonify({"reply": "Зависит от количества, вам сколько?"})

        # 5) производство / страна
        if re.search(r"\b(производств\w*|страна)\b", q, re.IGNORECASE):
            return jsonify({"reply": "Чехия, Германия."})

        # 6) Китай
        if re.search(r"\b(китай)\b", q, re.IGNORECASE):
            return jsonify({"reply": "Нет."})

        # 7) трубка / шланг / РВД
        if re.search(r"\b(трубк\w*|шланг|рвд)\b", q, re.IGNORECASE):
            return jsonify({
                "reply": "У нас есть трубка 6х1,5 мм код 100-003-25, есть шланг высокого давления до 800 bar, наружный диаметр 8,6 мм, стенка 2,3 мм, код 100-002."
            })

        # 8) ты человек / живой / ты кто
        if re.search(r"\b(ты человек|живой|ты кто)\b", q, re.IGNORECASE):
            return jsonify({
                "reply": "Я бот Иваныч! Хочешь поговорить с настоящим специалистом? Тогда тебе к Дмитрию! Звони/пиши ему, контакты на сайте."
            })

        # 9) оскорбления
        if re.search(r"\b(дурак|идиот|тупой|придурок|осёл|осел|козел|козёл|урод)\b", q, re.IGNORECASE):
            return jsonify({"reply": "Хм... сам такой 😏"})

        # ---------- Поиск по базе артикулов ----------
        # Если в запросе есть код вида 100-*** / 104-*** / 106-*** / 108-*** / 250-***
        m = re.search(r"(100|104|106|108|250)-\d{3}", q, re.IGNORECASE)
        rec = None
        if m:
            rec = find_by_article(m.group(0))

        if not rec:
            # если кода не было или не нашли — пробуем общим поиском по полям
            rec = find_by_article(user_message)

        if rec:
            # красиво сформируем ответ из найденной записи
            name = rec.get("name") or rec.get("наименование") or rec.get("title")
            article = rec.get("article") or rec.get("артикул") or rec.get("sku") or rec.get("code")
            price = rec.get("price") or rec.get("цена")
            parts = []
            if name:    parts.append(f"Наименование: {name}")
            if article: parts.append(f"Артикул: {article}")
            if price:   parts.append(f"Цена: {price}")
            reply = "\n".join(parts) if parts else json.dumps(rec, ensure_ascii=False)
            return jsonify({"reply": reply})

        # ---------- GPT‑фолбэк (если есть ключ) ----------
        if not _client or not os.getenv("OPENAI_API_KEY"):
            # Ключа нет — отвечаем без GPT
            return jsonify({
                "reply": "По теме смазочного оборудования подскажу: задайте артикул (например, 106-003) или уточните вопрос."
            })

        system_prompt = (
            "Ты — Иваныч, эксперт-консультант по смазочному оборудованию. "
            "Отвечай только по теме смазочных систем, их компонентов и применения. "
            "Если вопрос не по теме — отвечай: 'Я могу консультировать только по смазочному оборудованию.' "
            "Если спрашивают про наличие — говори: 'для точного корректного ответа о наличии сделайте запрос нам по электронной почте'."
        )

        completion = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=350,
        )
        reply_text = completion.choices[0].message.content.strip()
        return jsonify({"reply": reply_text})

    except Exception as e:
        app.logger.exception("chat error")
        return jsonify({"reply": f"Ошибка: {e}"}), 500


# ====== Старт ======
if __name__ == "__main__":
    load_data()
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    load_data()
