
from flask import Flask, request, jsonify
import json

app = Flask(__name__)

with open("1.json", "r", encoding="utf-8") as f:
    data = json.load(f)

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    for item in data:
        if item["code"] == user_input:
            return jsonify({"reply": item["name"]})
    return jsonify({"reply": "Артикул не найден."})

@app.route("/", methods=["GET"])
def home():
    return "Ivanych 2 is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
