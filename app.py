"""Basic AI chatbot backend (Flask).

Flow: browser -> POST /chat -> this server -> AI API -> reply -> browser.
The API key stays on the server (loaded from .env) and never reaches the browser.
"""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

load_dotenv()  # reads variables from the .env file

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a friendly, helpful assistant. Keep answers clear and concise. "
    "Use Markdown when it helps (lists, code blocks).",
)
MAX_HISTORY = 20  # only send the last N messages to keep requests small

app = Flask(__name__)

# The OpenAI SDK works with any OpenAI-compatible provider via base_url.
client = OpenAI(api_key=API_KEY, base_url=BASE_URL) if API_KEY else None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    if client is None:
        return jsonify(error="API_KEY is missing. Add it to your .env file."), 500

    data = request.get_json(silent=True) or {}
    history = data.get("messages", [])

    # Basic validation: keep only well-formed user/assistant messages
    clean = [
        {"role": m["role"], "content": str(m["content"])}
        for m in history
        if isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and m.get("content")
    ][-MAX_HISTORY:]

    if not clean or clean[-1]["role"] != "user":
        return jsonify(error="Please send a message."), 400

    # System prompt goes first, then the conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + clean

    try:
        response = client.chat.completions.create(model=MODEL, messages=messages)
        reply = response.choices[0].message.content
        return jsonify(reply=reply)
    except Exception as e:  # network error, bad key, rate limit, etc.
        return jsonify(error=f"AI request failed: {e}"), 502


if __name__ == "__main__":
    app.run(debug=True, port=5000)
