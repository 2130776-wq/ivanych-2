import os
import re
import json
from typing import Any, Dict, List

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# ---------- Конфигурация ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = Flask(__name__)
CORS(app)

ROOT = os.path.dirname(__file__)
PATH_JSON = os.path.join(ROOT, "1.json")

ARTICLE_RX = re.compile(r"^(100|104|106|108|250)-\d{3}$", re.IGNORECASE)

# ---------- Данные каталога ----------
DATA: List[Dict[str, Any]] = []

def load_data() -> None:
    global DATA
    try:
        with open(PATH_JSON, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            DATA = raw
        elif isinstance(raw, dict):
            vals: List[Dict[str, Any]] = []
            for v in raw.values():
                if isinstance(v, list):
                    vals.extend(v)
                elif isinstance(v, dict):
                    vals.append(v)
            DATA = vals or [raw]
        else:
            DATA = []
    except Exception as e:
        app.logger.exception("Failed to load 1.json")
        DATA = []

def norm(s: Any) -> str:
    s = "" if s is None else str(s)
    s = s.strip()
    s = s.replace("—", "-").replace("–", "-").replace("‑", "-")
    s = re.sub(r"\s+", "", s)
    return s.lower()

def record_text(rec: Dict[str, Any]) -> str:
    parts: List[str] = []
    def collect(v):
        if isinstance(v, dict):
            for vv in v.values():
                collect(vv)
        elif isinstance(v, list):
            for vv in v:
                collect(vv)
        else:
            parts.append("" if v is None else str(v))
    collect(rec)
    return " | ".join(parts)

def find_by_article(query: str) -> Dict[str, Any] | None:
    q = norm(query)
    if not q:
        return None
    candidate_keys = {"article", "art", "sku", "код", "артикул", "code"}
    for rec in DATA:
        for k, v in rec.items():
            if k and norm(k) in candidate_keys and norm(v) == q:
                return rec
    for rec in DATA:
        if q in norm(record_text(rec)):
            return rec
    return None

def pretty_rec(rec: Dict[str, Any]) -> str:
    name = rec.get("name") or rec.get("наименование") or rec.get("title")
    article = rec.get("article") or rec.get("артикул") or rec.get("sku") or rec.get("code")
    price = rec.get("price") or rec.get("цена")
    parts = []
    if name:    parts.append(f"Наименование: {name}")
    if article: parts.append(f"Артикул: {article}")
    if price:   parts.append(f"Цена: {price}")
    return "\n".join(parts) if parts else json.dumps(rec, ensure_ascii=False)

# ---------- Быстрые ответы (FAQ-правила) ----------
def quick_reply(user_text: str) -> str | None:
    t = user_text.lower().strip()

    # 1) доставка / отгрузка
    if any(x in t for x in ["доставка", "доставку", "отправите", "отгрузите"]):
        return "Доставка ТК Деловые Линии, до терминала в городе отгрузки бесплатно, далее за ваш счет или СДЭК"

    # 2) есть в наличии / какое количество / ветка «ДА/НЕТ»
    if ("есть в наличии" in t) or ("какое количество" in t):
        return "Да, есть в наличии, хотите счёт?"
    # Ответ «да» — без контекста считаем, что это «да, хочу счёт»
    if t in {"да", "да.", "да!", "оформляйте", "счёт", "хочу счёт", "выставляйте счёт"}:
        return "Заполните заявку и направьте нам по электронной почте вместе с карточкой предприятия. Почта: info@salpi.ru"
    if t in {"нет", "нет.", "не надо", "пока нет"}:
        return "Напрасно, коллега)"

    # 3) минимальное количество
    if "минималь" in t:  # покроет «минимальное», «минималка» и т.п.
        return "В основном кратно 10 шт"

    # 4) скидка / дисконт
    if any(x in t for x in ["скидка", "скидки", "дисконт"]):
        return "Зависит от количества, вам сколько?"

    # 5) производство / страна
    if any(x in t for x in ["производство", "страна"]):
        return "Чехия, Германия"

    # 6) Китай
    if "китай" in t:
        return "Нет"

    # 7) трубка / шланг / рвд
    if any(x in t for x in ["трубка", "шланг", "рвд"]):
        return "У нас есть трубка 6×1,5 мм, код 100-003-25. Есть шланг высокого давления до 800 bar, наружный диаметр 8,6 мм, стенка 2,3 мм, код 100-002"

    return None

# ---------- Роуты ----------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "records": len(DATA)})

@app.route("/chat", methods=["POST"])
def chat():
    try:
        payload = request.get_json(silent=True) or {}
        user_message: str = (payload.get("message") or "").strip()
        if not user_message:
            return jsonify({"reply": "Пустой запрос."})

        # A) Моментальные ответы по правилам
        qr = quick_reply(user_message)
        if qr:
            return jsonify({"reply": qr})

        # B) Быстрый путь по коду (100/104/106/108/250-xxx)
        if ARTICLE_RX.match(user_message):
            rec = find_by_article(user_message)
            if rec:
                return jsonify({"reply": pretty_rec(rec)})
            else:
                return jsonify({"reply": "Код распознан, но в базе такого артикула нет."})

        # C) Поиск по базе без точного кода
        rec = find_by_article(user_message)
        if rec:
            return jsonify({"reply": pretty_rec(rec)})

        # D) Консультант (GPT), если ключ задан
        if client:
            system_prompt = (
                "Ты — «Иваныч», технический консультант по смазочному оборудованию "
                "(централизованные системы смазки, фитинги, шланги/трубки, ниппели, распределители, "
                "удалённые точки смазки и т.п.). Отвечай кратко и по делу. "
                "Если вопрос вне темы — вежливо сообщи, что консультируешь только по смазочному оборудованию."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            rsp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.2,
                max_tokens=350,
            )
            return jsonify({"reply": rsp.choices[0].message.content.strip()})

        # E) Если ключа нет — нейтральный ответ
        return jsonify({"reply": "По базе не нашёл. Могу подсказать по подбору, уточните задачу."})

    except Exception as e:
        app.logger.exception("Chat error")
        return jsonify({"reply": f"Ошибка: {e}"}), 500

# ---------- Точка входа ----------
load_data()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
