
from flask import Flask, request, jsonify
import json

app = Flask(__name__)

# Загружаем базу из файла
with open("1.json", "r", encoding="utf-8") as f:
    data = json.load(f)

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"reply": "Пожалуйста, введите артикул."})

    result = data.get(user_input)
    if result:
        return jsonify({"reply": result})
    else:
        return jsonify({"reply": "Артикул не найден."})

@app.route("/", methods=["GET"])
def index():
    return "Иваныч 2 работает!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
