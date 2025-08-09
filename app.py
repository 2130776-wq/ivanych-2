from flask import Flask, request, jsonify
import openai
import json
import os
import re

app = Flask(__name__)

# Загружаем ключ из переменной окружения
openai.api_key = os.getenv("OPENAI_API_KEY")

# Загружаем данные из 1.json
with open("1.json", "r", encoding="utf-8") as f:
    products = json.load(f)

# Регулярка для кодов (100-***, 104-***, 106-***, 108-***, 250-***)
article_pattern = re.compile(r"^(100|104|106|108|250)-\d{3}$")

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"reply": "Пустой запрос."})

    # Проверяем, есть ли в запросе код нужного формата
    match = article_pattern.search(user_input)
    if match:
        # Ищем товар в 1.json по коду
        for item in products:
            if match.group(0) in item["code"]:
                return jsonify({"reply": f"Нашёл этот артикул: {item['name']}"})
        return jsonify({"reply": "Код найден в формате, но в базе нет такого артикула."})

    # Если кода нет — подключаем GPT
    try:
        prompt = f"""
Ты — Иваныч, эксперт-консультант по смазочному оборудованию.
Отвечай только по теме смазочных систем, их компонентов и применения.
Если вопрос не по теме — отвечай: 'Я могу консультировать только по смазочному оборудованию.'
Вопрос клиента: {user_input}
"""
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты технический консультант по смазочному оборудованию."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        reply = response.choices[0].message["content"].strip()
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Ошибка: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
