import os
import re
import json
from typing import Any, Dict, List

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# ---------- Конфигурация ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)
CORS(app)

# ---------- Данные каталога ----------
DATA: List[Dict[str, Any]] = []
PRODUCTS: List[Dict[str, Any]] = []  # если нужен второй список

ROOT = os.path.dirname(__file__)
PATH_JSON = os.path.join(ROOT, "1.json")

def load_data() -> None:
    global DATA, PRODUCTS
    try:
        with open(PATH_JSON, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Приводим к списку словарей (на случай разной структуры)
        if isinstance(raw, list):
            DATA = raw
        elif isinstance(raw, dict):
            vals = []
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
    # запасной вариант: проверяем в слитном тексте записи
    for rec in DATA:
        if q in norm(record_text(rec)):
            return rec
    return None

ARTICLE_RX = re.compile(r"^(100|104|106|108|250)-\d{3}$")

# ---------- Маршруты ----------
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

        # 1) Быстрый путь: артикул/код
        #    Сначала проверим шаблон вида 100-xxx/106-xxx и т.п.
        rx = ARTICLE_RX.search(user_message)
        if rx:
            rec = find_by_article(rx.group(0))
            if rec:
                return jsonify({"reply": pretty_rec(rec)})
            else:
                return jsonify({"reply": "Код распознан, но в базе такого артикула нет."})

        # затем обычный поиск по введённой строке
        rec = find_by_article(user_message)
        if rec:
            return jsonify({"reply": pretty_rec(rec)})

        # 2) Консультант: вопрос НЕ про конкретный артикул — отвечаем GPT
        system_prompt = (
            "Ты — «Иваныч», технический консультант по смазочному оборудованию "
            "(централизованные системы смазки, фитинг, шланги/трубки, гриз ниппели, распределители, "
            "удалённые точки смазки и т. п.). "
            "Отвечай кратко и по делу. "
            "Если вопрос вне темы смазочного оборудования — вежливо скажи, "
            "что консультируешь только по смазочному оборудованию."
        )

        few_shots = [
            {"role": "user", "content": "Что такое удалённая точка смазки и зачем она нужна?"},
            {"role": "assistant", "content": "Удалённая точка смазки — это выведенное наружу место подкачки смазки, "
                                             "чтобы обслуживать узлы без разборки/остановки. Это ускоряет обслуживание "
                                             "и повышает безопасность."},
            {"role": "user", "content": "Какой диаметр трубки выбрать для централизованной смазки?"},
            {"role": "assistant", "content": "Обычно используют 4–6 мм (наружный диаметр) для ответвлений и 8–10 мм "
                                             "для магистралей. Окончательно — по расходу/давлению и длине трассы."},
            {"role": "user", "content": "Сколько стоит авиабилеты в Париж?"},
            {"role": "assistant", "content": "Я консультирую только по смазочному оборудованию."},
        ]

        messages = [{"role": "system", "content": system_prompt}] + few_shots + [
            {"role": "user", "content": user_message}
        ]

        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=350,
        )
        reply_text = rsp.choices[0].message.content.strip()
        return jsonify({"reply": reply_text})

    except Exception as e:
        app.logger.exception("Chat error")
        return jsonify({"reply": f"Ошибка: {e}"}), 500

def pretty_rec(rec: Dict[str, Any]) -> str:
    """Формируем понятный ответ по записи каталога."""
    # подбираем самые вероятные поля из разных вариантов
    name = rec.get("name") or rec.get("наименование") or rec.get("title")
    article = rec.get("article") or rec.get("артикул") or rec.get("sku") or rec.get("code")
    price = rec.get("price") or rec.get("цена")
    parts = []
    if name:    parts.append(f"Наименование: {name}")
    if article: parts.append(f"Артикул: {article}")
    if price:   parts.append(f"Цена: {price}")
    return "\n".join(parts) if parts else json.dumps(rec, ensure_ascii=False)

# ---------- Точка входа ----------
if __name__ == "__main__":
    load_data()
    app.run(host="0.0.0.0", port=5000, debug=False)
else:
    load_data()
