# app.py
import os
import re
import json
from typing import Any, Dict, List, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

# ==== OpenAI (новый SDK) ====
# Требуется переменная окружения OPENAI_API_KEY
try:
    from openai import OpenAI
    _openai_available = True
except Exception:
    _openai_available = False

# ================== БРЕНД/ГОЛОС ==================
COMPANY_NAME   = "SALPI"
CONTACT_EMAIL  = "info@salpi.ru"

SYSTEM_PROMPT = f"""
Ты — Иваныч, консультант компании {COMPANY_NAME}.
Говори только от лица нашей компании: «мы», «у нас», «наша компания».
Запрещено:
- советовать обращаться к сторонним поставщикам, магазинам, маркетплейсам, «официальным дилерам», «производителю» и т.п.;
- давать рекомендации «поискать в интернете» или «проверить у поставщика».
Если клиент просит «где купить/у кого уточнить/к кому обратиться» — отвечай:
«Мы поможем напрямую. Напишите нам на {CONTACT_EMAIL}, и мы оформим всё под ключ.»
Если вопрос вне нашей темы — мягко верни в нашу тематику и предложи написать на {CONTACT_EMAIL}.
Пиши кратко, по делу, без воды. Если уместно — предлагай оформить заявку по почте.
"""

FORBIDDEN_SUPPLIER_PATTERNS = [
    r"обратит[её]сь.*(сторонн|другим)\s+поставщик",
    r"обратит[её]сь.*магази[нн]",
    r"у\s+поставщик[аоуе]",
    r"у\s+производител[яея]",
    r"в\s+специализированные?\s+магазин",
    r"поискать\s+в\s+интернет[еах]",
    r"свяжитесь\s+с\s+дилер",
    r"обратитесь\s+к\s+продавц",
]

def enforce_company_voice(text: str) -> str:
    """Подправляем стиль и блокируем упоминание сторонних поставщиков."""
    # 1) «мы-голос»
    text = re.sub(r"(?<!\S)я(?!\S)", "мы", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\bмой\b", "наш", text)
    text = re.sub(r"(?i)\bмоя\b", "наша", text)
    text = re.sub(r"(?i)\bмои\b", "наши", text)
    text = re.sub(r"(?i)\bменя\b", "нас",  text)

    # 2) запрет сторонних поставщиков
    if any(re.search(p, text, flags=re.IGNORECASE) for p in FORBIDDEN_SUPPLIER_PATTERNS):
        text = (
            f"Мы работаем самостоятельно. "
            f"Напишите нам на {CONTACT_EMAIL} — подготовим счет и проведем поставку."
        )
    return text

# ================== ДАННЫЕ (1.json) ==================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(APP_DIR, "1.json")
DATA: List[Dict[str, Any]] = []

def load_data() -> None:
    global DATA
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Нормализуем к списку словарей:
        if isinstance(raw, list):
            DATA = raw
        elif isinstance(raw, dict):
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
    except Exception:
        DATA = []

def norm(s: Any) -> str:
    s = str(s) if s is not None else ""
    s = s.strip()
    s = s.replace("—", "-").replace("–", "-").replace("‑", "-")
    s = re.sub(r"\s+", "", s)
    return s.lower()

def record_text(rec: Dict[str, Any]) -> str:
    parts: List[str] = []
    def collect(v: Any):
        if isinstance(v, dict):
            for vv in v.values(): collect(vv)
        elif isinstance(v, list):
            for vv in v: collect(vv)
        else:
            parts.append(str(v))
    collect(rec)
    return " | ".join(parts)

def find_by_article(q: str) -> Optional[Dict[str, Any]]:
    """Ищем сначала по ключевым полям артикула, затем по сплющенному тексту записи."""
    qn = norm(q)
    if not qn:
        return None

    article_keys = {"code", "article", "sku", "артикул", "код"}
    for rec in DATA:
        for k, v in rec.items():
            if k.lower() in article_keys and norm(v) == qn:
                return rec
    for rec in DATA:
        if qn in norm(record_text(rec)):
            return rec
    return None

# ================== ФАСТ-РЕСПОНСЫ (FAQ/правила) ==================
RE_DELIVERY   = re.compile(r"\b(доставк\w*|отправ\w*|отгруз\w*|грузите)\b", re.IGNORECASE)
RE_AVAILABLE  = re.compile(r"(есть\s+в\s+наличии|наличие|\bв\s+наличии\b|\bсейчас\s+есть\b)", re.IGNORECASE)
RE_MIN_QTY    = re.compile(r"(минимальн\w+\s+количеств\w+|минималк\w+|\bсколько\s+минимум\b)", re.IGNORECASE)
RE_DISCOUNT   = re.compile(r"(скидк\w+|дисконт)", re.IGNORECASE)
RE_COUNTRY    = re.compile(r"(производств\w+|страна)", re.IGNORECASE)
RE_CHINA      = re.compile(r"\bкитай\b", re.IGNORECASE)
RE_TUBE       = re.compile(r"(трубка|шланг|рвд)", re.IGNORECASE)
RE_IDENTITY   = re.compile(r"(ты\s*(кто|человек|живой)|кто\s*ты)", re.IGNORECASE)
RE_BUY        = re.compile(r"(купить|приобрест[ьи]|заказ(ать)?|сч[её]т|оплатить)", re.IGNORECASE)

# Простейший список грубых слов (можно расширять)
INSULT_WORDS = [
    "дурак","дебил","идиот","тупой","тупица","кретин","мразь","урод","сволочь"
]

def check_insult(q: str) -> bool:
    return any(w in q.lower() for w in INSULT_WORDS)

# ================== Flask ==================
app = Flask(__name__)
CORS(app)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "records": len(DATA)})

# артикулы вида 100-123, 104-456, 106-003 и т.п.
ARTICLE_CODE = re.compile(r"\b(100|104|106|108|250)-\d{3}\b")

def article_reply(rec: Dict[str, Any]) -> str:
    name   = rec.get("name") or rec.get("наименование") or rec.get("title")
    code   = rec.get("code") or rec.get("артикул") or rec.get("article") or rec.get("sku")
    price  = rec.get("price") or rec.get("цена")
    out = []
    if name:  out.append(f"Наименование: {name}")
    if code:  out.append(f"Артикул: {code}")
    if price: out.append(f"Цена: {price}")
    return "\n".join(out) if out else json.dumps(rec, ensure_ascii=False)

def maybe_hard_reply(q: str) -> Optional[str]:
    """Фиксированные ответы, если совпали ключи."""
    # 9) Оскорбление
    if check_insult(q):
        return "Хм… сам такой 🙂"

    # 1) Доставка/отгрузка
    if RE_DELIVERY.search(q):
        return ("Доставка ТК «Деловые Линии»: до терминала в городе отгрузки бесплатно, "
                "далее за ваш счёт. Либо СДЭК.")

    # 2) Наличие
    if RE_AVAILABLE.search(q):
        return ("Да, есть в наличии. Хотите счёт? Если да — заполните заявку и отправьте вместе с "
                f"карточкой предприятия на {CONTACT_EMAIL}.")

    # 3) Минимальное количество
    if RE_MIN_QTY.search(q):
        return "В основном — кратно 10 шт."

    # 4) Скидка
    if RE_DISCOUNT.search(q):
        return "Скидка зависит от количества. Сколько вам нужно?"

    # 5) Страна производства
    if RE_COUNTRY.search(q):
        return "Производство — Чехия, Германия."

    # 6) Китай?
    if RE_CHINA.search(q):
        return "Китай — нет."

    # 7) Трубка/шланг/РВД
    if RE_TUBE.search(q):
        return ("У нас есть трубка 6×1,5 мм — код 100-003-25. "
                "И шланг высокого давления до 800 bar (Ø 8,6 мм, стенка 2,3 мм) — код 100-002.")

    # 8) Кто ты?
    if RE_IDENTITY.search(q):
        return (f"Я бот Иваныч, консультант {COMPANY_NAME}! "
                f"Хочешь поговорить с живым специалистом? Пиши/звони Дмитрию — контакты на сайте. "
                f"Также можно на почту: {CONTACT_EMAIL}.")

    # 10) Купить/оформление
    if RE_BUY.search(q):
        return (f"Отправьте заявку на почту {CONTACT_EMAIL}. Мы выставим счёт, после оплаты отгрузим. "
                "Доставка — Деловые Линии или СДЭК.")

    return None

def make_gpt_reply(user_input: str) -> str:
    """Запрос в OpenAI (если доступен ключ). Иначе — заглушка."""
    if not _openai_available:
        return "Мы можем помочь по смазочному оборудованию. Напишите нам на почту для деталей."
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Не задан API‑ключ. Напишите нам на почту — поможем оперативно."

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # можно поменять на доступную модель
            temperature=0.3,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_input},
            ],
        )
        text = resp.choices[0].message.content.strip()
        return enforce_company_voice(text)
    except Exception as e:
        # не роняем сервис
        return f"Мы на связи. Напишите нам на {CONTACT_EMAIL} — ответим быстро. (Тех.заметка: {e})"

@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_input = (payload.get("message") or "").strip()
    if not user_input:
        return jsonify({"reply": "Пустой запрос."})

    # 0) Фикс-ответы (FAQ/правила)
    hard = maybe_hard_reply(user_input)
    if hard:
        return jsonify({"reply": hard})

    # 1) Поиск артикулов вида 100-123 и т.п.
    code_match = ARTICLE_CODE.search(user_input)
    if code_match:
        # если нашли шаблон кода, ищем среди записей
        cand = find_by_article(code_match.group(0))
        if cand:
            return jsonify({"reply": article_reply(cand)})

    # 2) Попытка поиска по базе (если ввели код/название без шаблона)
    cand = find_by_article(user_input)
    if cand:
        return jsonify({"reply": article_reply(cand)})

    # 3) GPT-ответ с жёсткими ограничениями голоса
    reply = make_gpt_reply(user_input)
    reply = enforce_company_voice(reply)
    return jsonify({"reply": reply})

# ===== entrypoints =====
if __name__ == "__main__":
    load_data()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
else:
    load_data()
