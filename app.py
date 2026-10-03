"""AI chatbot backend (Flask) - Day 2 + Day 3 version.

Request flow:
    browser -> POST /chat -> validate -> rate limit -> AI API -> reply -> browser

The API key stays on the server (loaded from .env) and never reaches the browser.
The server is stateless: the browser sends the conversation history with every
request, and the server trims it before calling the AI.
"""
import logging
import os
import time
from collections import defaultdict, deque

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

load_dotenv()  # reads variables from the .env file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("chatbot")


def _int_env(name, default):
    """Read an integer setting from the environment, fall back to a default."""
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# ---------- Configuration (all overridable from .env) ----------
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o-mini")

MAX_HISTORY = _int_env("MAX_HISTORY", 20)  # max messages sent to the AI
MAX_HISTORY_CHARS = _int_env("MAX_HISTORY_CHARS", 12000)  # max total characters
MAX_MESSAGE_CHARS = _int_env("MAX_MESSAGE_CHARS", 2000)  # max length of one message
RATE_LIMIT_PER_MIN = _int_env("RATE_LIMIT_PER_MIN", 20)  # requests per IP per minute
REQUEST_TIMEOUT = _int_env("REQUEST_TIMEOUT", 30)  # seconds to wait for the AI

# A structured system prompt: role, style, rules.
DEFAULT_SYSTEM_PROMPT = """# Role
You are "CodeBuddy", a friendly AI assistant that helps beginner programmers
and AI interns learn to code and understand AI concepts.

# Style
- Be clear, patient and concise. Use simple words first, then add detail if asked.
- Use Markdown: short lists and fenced code blocks with the language name.
- Give a small example when it helps.

# Rules
- If you are not sure about something, say so. Never invent facts, libraries or links.
- If a question is unclear, ask one short clarifying question.
- Politely decline harmful or illegal requests.
- Never ask for or repeat API keys, passwords or other secrets.
"""
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT") or DEFAULT_SYSTEM_PROMPT

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # reject huge request bodies (64 KB)

# The OpenAI SDK works with any OpenAI-compatible provider via base_url.
client = (
    OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=REQUEST_TIMEOUT, max_retries=2)
    if API_KEY
    else None
)

# Very simple in-memory rate limiter: remembers recent request times per IP.
_requests = defaultdict(deque)


def error(message, status):
    """Return a JSON error in one consistent format."""
    return jsonify(error=message), status


def is_rate_limited(ip):
    now = time.time()
    recent = _requests[ip]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= RATE_LIMIT_PER_MIN:
        return True
    recent.append(now)
    return False


def clean_messages(raw):
    """Validate and trim the conversation.

    Returns (messages, None) on success or (None, error_message) on failure.
    """
    if not isinstance(raw, list) or not raw:
        return None, "Please send a message."

    cleaned = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            cleaned.append({"role": role, "content": content})

    if not cleaned or cleaned[-1]["role"] != "user":
        return None, "Please send a message."
    if len(cleaned[-1]["content"]) > MAX_MESSAGE_CHARS:
        return None, f"Message is too long (maximum {MAX_MESSAGE_CHARS} characters)."

    # Keep only the newest messages: limit by count first, then by total characters.
    cleaned = cleaned[-MAX_HISTORY:]
    kept, total = [], 0
    for m in reversed(cleaned):
        total += len(m["content"])
        if total > MAX_HISTORY_CHARS and kept:
            break
        kept.append(m)
    kept.reverse()

    # The history sent to the AI should start with a user message.
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    return kept, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """Simple status check (useful for deployment and monitoring)."""
    return jsonify(status="ok", model=MODEL, configured=client is not None)


@app.route("/chat", methods=["POST"])
def chat():
    if client is None:
        return error("Server is not configured: API_KEY is missing in .env.", 500)

    ip = request.remote_addr or "unknown"
    if is_rate_limited(ip):
        return error("Too many requests. Please wait a minute and try again.", 429)

    data = request.get_json(silent=True) or {}
    history, problem = clean_messages(data.get("messages"))
    if problem:
        return error(problem, 400)

    # System prompt goes first, then the conversation history.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    started = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0.7
        )
        reply = response.choices[0].message.content or "(The AI returned an empty answer.)"
        log.info(
            "chat ok ip=%s messages=%d time=%.2fs", ip, len(history), time.time() - started
        )
        return jsonify(reply=reply)
    except AuthenticationError:
        log.error("AI provider rejected the API key")
        return error("The AI service rejected the API key. Check your .env file.", 502)
    except RateLimitError:
        log.warning("AI provider rate limit or quota reached")
        return error("The AI service is busy or the quota is used up. Try again soon.", 429)
    except APITimeoutError:
        log.warning("AI request timed out after %ss", REQUEST_TIMEOUT)
        return error("The AI service took too long to answer. Please try again.", 504)
    except APIConnectionError:
        log.warning("Could not connect to the AI service")
        return error("Could not reach the AI service. Check your internet connection.", 502)
    except APIStatusError as e:
        log.error("AI provider error status=%s", e.status_code)
        return error(f"The AI service returned an error (status {e.status_code}).", 502)
    except Exception:  # last safety net so the server never crashes with a traceback page
        log.exception("Unexpected error in /chat")
        return error("Something went wrong on the server.", 500)


@app.errorhandler(413)
def too_large(_e):
    return error("Request is too large.", 413)


if __name__ == "__main__":
    # Debug mode is OFF by default (safer). Turn on with FLASK_DEBUG=1 in .env.
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=5000)
