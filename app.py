from flask import Flask, request, jsonify
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

# Загружаем данные из файла
with open('1.json', encoding='utf-8') as f:
    data = json.load(f)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_input = request.json.get('message', '').strip()

        # Ищем совпадение
        for entry in data:
            if user_input == entry.get("code"):
                return jsonify({"reply": entry.get("name")})

        return jsonify({"reply": "Не найдено 😕"})
    except Exception as e:
        return jsonify({"reply": f"Ошибка: {str(e)}"})

@app.route('/')
def index():
    return 'Иваныч 2 работает.'

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
