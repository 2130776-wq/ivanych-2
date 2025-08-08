from flask import Flask, request, jsonify
from flask_cors import CORS
import json, re, os
from typing import List, Dict, Any

app = Flask(__name__)
CORS(app)  # важное — чтобы фронт не ловил CORS

DATA: List[Dict[str, Any]] = []

def load_data():
    global DATA
    path = os.path.join(os.path.dirname(__file__), "1.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Приводим к списку словарей, даже если корень — dict
    if isinstance(raw, list):
        DATA = raw
    elif isinstance(raw, dict):
        # если корень-словарь, берём его значения (или завернём в один элемент)
        # чаще всего нужные записи сидят в каком-то ключе; берём все values
        vals = list(raw.values())
        flat: List[Dict[str, Any]] = []
        for v in vals:
            if isinstance(v, list):
                flat.extend(v)
            elif isinstance(v, dict):
                flat.append(v)
        DATA = flat if flat else [raw]
    else:
        DATA = []

def norm(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    s = s.strip()
    # заменяем любые тире/длинные дефисы на обычный
    s = s.replace("—", "-").replace("–", "-").replace("‑", "-")
    # убираем лишние пробелы вокруг дефисов и вообще
    s = re.sub(r"\s+", "", s)
    return s.lower()

def record_text(rec: Dict[str, Any]) -> str:
    """Склейка всех строковых значений записи, для поиска по ней."""
    parts: List[str] = []
    def collect(v):
        if isinstance(v, dict):
            for vv in v.values():
                collect(vv)
        elif isinstance(v, list):
            for vv in v:
                collect(vv)
        else:
            if isinstance(v, str):
                parts.append(v)
            else:
                # числа тоже учитываем
                parts.append(str(v))
    collect(rec)
    return " | ".join(parts)

def find_by_article(query: str) -> Dict[str, Any] | None:
    q = norm(query)
    if not q:
        return None

    # Ищем сначала по полям, которые часто используют для артикула
    candidate_keys = {"article", "art", "sku", "код", "артикул"}
    for rec in DATA:
        for k, v in rec.items():
            if k.lower() in candidate_keys:
                if norm(v) == q:
                    return rec

    # Если не нашли — ищем в склеенной строке записи
    for rec in DATA:
        txt = record_text(rec)
        if q in norm(txt):
            return rec

    return None

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "records": len(DATA)})

@app.route("/chat", methods=["POST"])
def chat():
    try:
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        if not message:
            return jsonify({"reply": "Пустой запрос."})

        app.logger.info(f"[CHAT] raw='{message}' norm='{norm(message)}' records={len(DATA)}")
        rec = find_by_article(message)
        if not rec:
            return jsonify({"reply": "Не найдено 🙁"})

        # Формируем понятный ответ
        # Пробуем вытащить самые ожидаемые поля, иначе — покажем запись целиком
        name = rec.get("name") or rec.get("наименование") or rec.get("title")
        article = rec.get("article") or rec.get("артикул") or rec.get("sku")
        price = rec.get("price") or rec.get("цена")
        line = []
        if name:    line.append(f"Наименование: {name}")
        if article: line.append(f"Артикул: {article}")
        if price:   line.append(f"Цена: {price}")
        reply = "\n".join(line) if line else json.dumps(rec, ensure_ascii=False)
        return jsonify({"reply": reply})

    except Exception as e:
        app.logger.exception("Chat error")
        return jsonify({"reply": f"Ошибка: {e}"}), 500

if __name__ == "__main__":
    # при локальном запуске
    load_data()
    app.run(host="0.0.0.0", port=5000)
else:
    # при запуске на Render
    load_data()
