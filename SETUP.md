# Setup guide

End-to-end walkthrough for getting tims-ai-assistant running.

## 1. Create the Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot`, pick a display name and a username (must end in `bot`).
3. Save the token — looks like `12345678:AAH....`. This is your `BOT_TOKEN`.
4. Optional but recommended: send `/setprivacy` → choose your bot → `Disable`
   if you want it to read all messages in groups (only relevant if you set
   `REPLY_IN_GROUPS=true`).
5. Optional: `/setjoingroups` → `Disable` to prevent strangers from adding the
   bot to random groups.

## 2. Pick an LLM provider

The bot speaks the OpenAI Chat Completions protocol, so you can use any
compatible provider. Pick one and grab an API key:

| Provider     | Why                                          | Base URL                                      | Example model                              |
|--------------|----------------------------------------------|-----------------------------------------------|--------------------------------------------|
| **OpenAI**   | Reliable, smartest                           | `https://api.openai.com/v1`                   | `gpt-4o-mini`                              |
| **DeepSeek** | Very cheap, smart                            | `https://api.deepseek.com/v1`                 | `deepseek-chat`                            |
| **Groq**     | Free tier, very fast                         | `https://api.groq.com/openai/v1`              | `llama-3.3-70b-versatile`                  |
| **OpenRouter** | Aggregator, has free tier              | `https://openrouter.ai/api/v1`                | `meta-llama/llama-3.1-8b-instruct:free`    |
| **Together** | Cheap                                         | `https://api.together.xyz/v1`                 | `meta-llama/Llama-3.3-70B-Instruct-Turbo`  |

Put the URL into `LLM_BASE_URL`, the model into `LLM_MODEL`, and the key into
`LLM_API_KEY`.

## 3. Find your admin Telegram ID

Forward any of your messages to [@userinfobot](https://t.me/userinfobot) to get
your numeric ID. Put it into `ADMIN_IDS` (comma-separated for multiple).

## 4. Local install

```bash
git clone https://github.com/Timo274/-tims-ai-assistant.git tims-ai-assistant
cd tims-ai-assistant
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # fill BOT_TOKEN, LLM_API_KEY, ADMIN_IDS, etc.

mkdir -p data logs
python -m bot
```

You should see `authenticated as @YourBot ...` in the console. Open Telegram,
send a message to your bot, and it'll reply.

## 5. Try the admin commands

In a private chat with the bot (only works for IDs in `ADMIN_IDS`):

| Command                | What it does                                  |
|------------------------|-----------------------------------------------|
| `/ping`                | sanity check                                  |
| `/stats`               | counters (users, messages, memories, model)   |
| `/users`               | list 20 most recently active users            |
| `/memory [user_id]`    | dump memory + summary for that user           |
| `/forget <user_id>`    | wipe memories + summaries for that user       |
| `/reset <user_id>`     | wipe everything (messages too)                |
| `/block <user_id>`     | bot ignores this user from now on             |
| `/unblock <user_id>`   | re-enable                                     |
| `/pause` / `/resume`   | global mute / unmute                          |
| `/admin_help`          | print this list                               |

## 6. Database

By default the bot uses SQLite at `./data/bot.db`. The schema is created
automatically on first run. The reference DDL is in [`schema.sql`](schema.sql).

To use PostgreSQL instead, set:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME
```

Tables will be created on first run.

## 7. Tuning behaviour

The most useful knobs in `.env`:

- `LLM_TEMPERATURE` — higher = more chaotic, lower = more conservative.
  Default `0.95`. Drop to `0.75` if replies get too unhinged.
- `REPLY_DEBOUNCE_SECONDS` — how long to wait after the last incoming message
  before replying. Default `2.5` — feels human. Increase to `4-5` for an
  even chiller vibe.
- `TYPING_DELAY_PER_CHAR` / `TYPING_DELAY_MIN` / `TYPING_DELAY_MAX` —
  typing-indicator pacing.
- `CONTEXT_RECENT_MESSAGES` / `SUMMARISE_AFTER_MESSAGES` — how aggressively to
  fold old history into long-term summaries.
- `MEMORY_TOP_K` — how many memory snippets to inject per reply.
- `RATE_LIMIT_MESSAGES` / `RATE_LIMIT_WINDOW_SECONDS` — per-user flood limit.

## 8. Logs

Every request and every reply gets logged to:

- console (stdout)
- `./logs/bot.log` (rotated daily, 14 days kept)

Log level via `LOG_LEVEL` (`DEBUG` / `INFO` / `WARNING`).
