# tims-ai-assistant

Production-ready Telegram autopilot bot for [@timsAiAssistent_bot](https://t.me/timsAiAssistent_bot).
The bot autonomously replies to Telegram messages as if it were a real person — an 18-year-old
Ukrainian finance student into crypto, analytics, luxury watches, tech and internet culture.

> Designed to feel human. Not a customer support bot. Not ChatGPT.

## Highlights

- **aiogram 3** + async architecture, multiple chats in parallel
- **OpenAI-compatible** LLM client — works with OpenAI, DeepSeek, Groq, OpenRouter, Together, etc.
- **Per-user persistent memory** with automatic fact extraction
- **Long-term conversation summaries** so context never blows up
- **Personality engine** with tone adaptation (recruiter vs. friend vs. random)
- **Message queue** with debounce for natural multi-message replies
- **Rate limiting**, prompt-injection protection, structured logging
- **Admin commands** for stats / pause / reset / memory inspection
- **SQLite** by default, **PostgreSQL** supported via env var
- **Docker** + **systemd** deployment recipes

## Quick start

```bash
git clone https://github.com/Timo274/-tims-ai-assistant.git tims-ai-assistant
cd tims-ai-assistant
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN and LLM_API_KEY
python -m bot
```

See [SETUP.md](SETUP.md) for a full walkthrough and [DEPLOY.md](DEPLOY.md) for VPS deployment.

## Project layout

```
bot/
  main.py            entrypoint
  config.py          dotenv-backed settings
  logger.py          rotating + console logging
  db/                async SQLAlchemy models + repository
  llm/               OpenAI-compatible async client + prompt library
  personality/       persona definition + tone adaptation
  memory/            fact extractor, retriever, long-term summarizer
  reply/             reply pipeline, context builder, debounce queue
  handlers/          aiogram handlers (messages, /start, admin)
  middleware/        rate-limit, prompt-protection, request logging
  utils/             token counting, time helpers
schema.sql           reference SQL schema (auto-applied on first run)
Dockerfile
docker-compose.yml
systemd/tims-ai-bot.service
```

## License

MIT.
