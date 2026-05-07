# VPS deployment

Two recipes — pick whichever is closer to how you like to run things.

## Option A — Docker Compose (recommended)

Works on any Linux VPS with Docker installed. Survives reboots, restarts on
crash, persists DB + logs to host volumes.

```bash
# 1. Get a VPS (Hetzner CX11 / DigitalOcean $4 droplet / etc) — Ubuntu 22.04+.

# 2. Install Docker.
ssh root@your-vps
apt-get update && apt-get install -y docker.io docker-compose-plugin git

# 3. Clone & configure.
git clone https://github.com/Timo274/-tims-ai-assistant.git /opt/tims-ai-assistant
cd /opt/tims-ai-assistant
cp .env.example .env
nano .env    # fill in BOT_TOKEN, LLM_API_KEY, ADMIN_IDS

# 4. Run.
docker compose up -d --build

# 5. Check it.
docker compose logs -f bot
```

Updating later:

```bash
cd /opt/tims-ai-assistant
git pull
docker compose up -d --build
```

The bot writes to `./data/bot.db` and `./logs/` on the host (mounted into the
container). Back those two directories up if you care about memory persistence.

## Option B — bare-metal systemd

For folks who prefer running Python directly.

```bash
# Prereqs.
apt-get update
apt-get install -y python3.11 python3.11-venv git

# Create a dedicated user.
adduser --system --group --home /opt/tims-ai-assistant bot

# Clone.
sudo -u bot git clone https://github.com/Timo274/-tims-ai-assistant.git /opt/tims-ai-assistant
cd /opt/tims-ai-assistant

# Install.
sudo -u bot python3.11 -m venv .venv
sudo -u bot .venv/bin/pip install -r requirements.txt

# Configure.
sudo -u bot cp .env.example .env
sudo -u bot nano .env
sudo -u bot mkdir -p data logs

# Install the systemd unit.
cp systemd/tims-ai-bot.service /etc/systemd/system/tims-ai-bot.service
systemctl daemon-reload
systemctl enable --now tims-ai-bot.service

# Verify.
systemctl status tims-ai-bot.service
journalctl -u tims-ai-bot.service -f
```

Updating later:

```bash
cd /opt/tims-ai-assistant
sudo -u bot git pull
sudo -u bot .venv/bin/pip install -r requirements.txt
systemctl restart tims-ai-bot.service
```

## Connecting Telegram + OpenAI

1. **Telegram token** — get from [@BotFather](https://t.me/BotFather), put
   in `.env` as `BOT_TOKEN`.
2. **LLM key**:
   - For OpenAI: create at <https://platform.openai.com/api-keys>, set
     `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL=gpt-4o-mini`,
     `LLM_API_KEY=sk-...`.
   - For DeepSeek / Groq / OpenRouter / Together — see [`SETUP.md`](SETUP.md).
3. **Admin ID** — message [@userinfobot](https://t.me/userinfobot), put your
   numeric ID into `ADMIN_IDS`.

After saving `.env`, restart the service and send a DM to your bot.

## Hardening checklist

- [ ] `.env` file is `chmod 600` and owned by the bot user, not committed.
- [ ] Bot token is regenerated in @BotFather any time it leaks.
- [ ] You disabled `/setjoingroups` so randoms can't add your bot to channels.
- [ ] Firewall blocks everything except SSH (the bot uses long polling — no
      inbound port required).
- [ ] You back up `./data/bot.db` somewhere off-host.
- [ ] You set sensible `RATE_LIMIT_*` so a single chat can't burn your LLM budget.

## Cost & scale

- aiogram + asyncio handles thousands of simultaneous chats per process. The
  bottleneck will be your LLM provider's rate limits, not the bot.
- SQLite handles tens of thousands of users on a small VPS. Switch to
  PostgreSQL if you go higher (set `DATABASE_URL`).
- Long-term memory summaries keep per-user token usage roughly constant
  regardless of conversation length.
