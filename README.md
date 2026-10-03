# AI Chatbot

## What I built
A simple web chatbot. You type a message, it is sent to an AI model, and the reply is shown in the chat window. It works end-to-end and includes these bonus features:

- Conversation history (the AI remembers earlier messages)
- System prompt (sets the bot's behaviour)
- Loading state ("Thinking..." while waiting)
- Error handling (missing key, bad key, network/rate-limit errors)
- Basic chat UI
- Markdown rendering of replies (lists, code blocks, bold)

## Technology used
- **Python 3** + **Flask** (backend)
- **OpenAI Python SDK** (works with OpenAI, Groq, Gemini and other OpenAI-compatible APIs through `BASE_URL`)
- **HTML / CSS / JavaScript** (frontend, no framework)
- `marked` + `DOMPurify` (safe Markdown rendering)
- `python-dotenv` (loads secrets from `.env`)

## How to run
```bash
# 1. Clone the repo
git clone <your-repo-url>
cd ai-chatbot

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env            # Windows: copy .env.example .env
# open .env and paste your key into API_KEY

# 5. Start the app
python app.py
```
Open http://127.0.0.1:5000 in your browser.

## API integration approach
1. The browser sends the full conversation (`messages`) to `POST /chat` as JSON.
2. The Flask server validates it, keeps the last 20 messages, and puts the system prompt first.
3. The server calls `client.chat.completions.create(model, messages)`.
4. The reply text is returned as JSON and displayed (rendered as Markdown) in the page.

The API key lives only on the server in `.env` (ignored by git), so it is never exposed to the browser or GitHub. History is kept in the browser and re-sent each request, because the AI API itself is stateless.

## What I learned
- How a client/server app talks to an AI API end-to-end
- Why API keys must stay server-side and out of git (`.env` + `.gitignore`)
- That chat models are stateless, so "memory" means resending the history
- The role of the system prompt, and the value of loading and error states
- OpenAI-compatible APIs let you switch providers by changing only `BASE_URL`, `MODEL` and the key
- I learned that AI models don't remember by themselves, so the chat history must be sent again with each message.

## What I would improve next
- Stream the response token by token
- Save conversations (database or local storage)
- Add voice input and voice output
- Trim history by token count instead of message count
- Add rate limiting and deploy online

## Screenshot
![demo](screenshot.png)
