# Bepul serverga ko'chirish — Render.com (kartasiz)

Bot 24/7, karta talab qilmasdan ishlashi uchun. Jami ~10 daqiqa.

## Arxitektura

| Qism | Xizmat | Narx | Karta |
|---|---|---|---|
| Bot (24/7) | Render.com free web-service | $0 | ❌ kerak emas |
| PostgreSQL | Neon.tech | $0 | ❌ kerak emas |
| Redis (ixtiyoriy) | Upstash yoki avto-kashf* | $0 | ❌ kerak emas |

\* Railway'dagi avto-kashf faqat loyiha ichida ishlaydi — Render'da Upstash tavsiya etiladi, bo'lmasa bot eslab qolmasdan ishlayveradi.

Uxlamaslik tizimi: bot har 10 daqiqada o'zining `/health` sahifasiga so'rov yuboradi (`PING_INTERVAL_SECONDS` bilan o'zgartiriladi). Zaxira: cron-job.org.

---

## 1-qadam: Neon Postgres (~3 daqiqa)

1. [neon.tech](https://neon.tech) → **Sign up with GitHub** (`bekzamin316-beep` bilan bir klik)
2. Project yaratish (nomi: `crypto-news`)
3. Dashboard'da **Connection string** ni nusxalang:
   `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`
4. **Eski ma'lumotlarni saqlash kerak bo'lsa** — tayyor zaxira fayllar lokalda turadi:
   - `~/yangiliklar-bot-backup/db/railway-<sana>.dump` — barcha data (10 jadval)
   - Neon'ga ko'chirish: `NEON_URL='<neon string>' ./scripts/neon-restore.sh`
   - (Config `postgres://` ni avtomatik `postgresql+asyncpg://` ga o'zgartiradi — stringni tahrirlash shart emas.)

## 2-qadam: Render Web Service (~4 daqiqa)

1. [render.com](https://render.com) → **Get Started** → **GitHub** bilan kirish
2. **New +** → **Web Service**
3. Repo ro'yxatidan **bekzamin316-beep/yangiliklar-bot** ni tanlang → Connect
4. Sozlamalar (ko'pi avtomatik `render.yaml` dan olinadi):
   - Runtime: **Python 3**
   - Build: `pip install -r requirements.txt`
   - Start: `python -m src.main`
   - Instance type: **Free**
5. **Environment Variables** bo'limiga qo'shing:

| Key | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather tokeni |
| `TELEGRAM_CHANNEL_ID` | Kanal ID (-100...) |
| `ADMIN_IDS` | Sizning Telegram ID |
| `DB_TYPE` | `postgres` |
| `DATABASE_URL` | Neon string (1-qadam) |
| `ADMIN_PASSWORD` | Admin panel PIN |
| `AI_PROVIDER` | `dashscope` |
| `DASHSCOPE_API_KEY` | DashScope kalitingiz |

6. **Create Web Service**

## 3-qadam: Tekshirish (~3 daqiqa build)

Render **Logs** tabida:

```
Health server listening on 0.0.0.0:10000
Database initialized
Scheduler configured (digest): ... digest at 08:00, 12:00, 18:00, 22:00
```

Ko'rsangiz — tayyor! Kanalda yangiliklar kelishini kuzatasiz.

## 4-qadam (tavsiya): zaxira ping

[cron-job.org](https://cron-job.org) → bepul akkaunt → yangi job:
- URL: `https://crypto-news-bot.onrender.com/health` (Render sizga bergan manzil)
- Interval: har 10 daqiqa

## Boshqa bot ulash

Xuddi shu repodan yana bir **Web Service** yarating, faqat boshqa qiymatlar:
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `ADMIN_IDS`. Ikkala mustaqil bot ishlaydi.

---

## Cheklovlar

- Free instans RAM 512MB — bu bot uchun yetarli (hozirgi sarfi ~150-250MB)
- Render ba'zan free konteynerlarni restart qiladi — bot avtomatik tiklanadi
- Railway'dan ma'lumot ko'chirish: xohlasangiz oldin dump olib Neon'ga yuklayman

---

## Zaxira va "muddat tugadi" rejasi (avtomatlashtirilgan)

Hammasi lokal saqlanadi — Railway to'xtasa, 10 daqiqada boshqa provayderga o'tasiz.

### Avtomatik zaxira scriptlari (`scripts/`)

| Script | Nima qiladi |
|---|---|
| `./scripts/backup-env.sh` | Railway'ning 37 ta env o'zgaruvchisini → `~/yangiliklar-bot-backup/env-*.env` + Render uchun tayyor `render.env` |
| `./scripts/db-dump.sh` | Postgres dump (SSH tunnel, public kerak emas) → `~/yangiliklar-bot-backup/db/railway-<sana>.dump` |
| `NEON_URL='...' ./scripts/neon-restore.sh` | Dump faylini Neon'ga ko'chiradi |

Zaxira joylari (repo'dan TASHQARIDA, git'ga tushmaydi):
```
~/yangiliklar-bot-backup/
├── db/railway-2026-10-07.dump    # data (10 jadval)
├── env-bot-2026-10-07.env        # bot o'zgaruvchilari (37 ta)
├── env-postgres-2026-10-07.env
├── env-redis-2026-10-07.env
└── render.env                    # Render'ga paste qilishga tayyor
```

### Muddat tugaganda qilinadigan ishlar (qo'llanma)

1. **Neon** (bepul, karta kerak emas): dump'ni ko'chirish
   ```bash
   NEON_URL='postgresql://...' ./scripts/neon-restore.sh
   ```
2. **Render**: `render.yaml` bilan Web Service yuqoridagi 2-qadam bo'yicha,
   env'larni `~/yangiliklar-bot-backup/render.env` dan joylashtirish,
   `DATABASE_URL` = Neon stringi (qayta tahrirlash shart emas — config avtomatik o'zgartiradi)
3. **Tekshirish**: Logs'da `Database initialized` + `Digest complete` ko'rinishi kerak
4. **Telegram'da uzilish bo'lmaydi** — faqat 10-15 daqiqa o'chiq bo'ladi (bot joyida qayta ishga tushadi)

> Redis'siz ham ishlaydi (AI limitlar cheatlashtiriladi) — xohlasangiz Upstash bepul qo'shing.

### Hozirgi holat (2026-10-07 dan beri)

- **Asosiy server: Render** — https://crypto-news-bot-lf0w.onrender.com
  (`srv-db366g942hec738n7810`, bepul plan, Singapore, self-ping 600s yoqilgan)
- **Railway faol emas**: deployment o'chirilgan **va GitHub manzili uzilgan**
  (`repo: null`) — push'lar Railway'ni avtomatik qayta ishga tushirmaydi,
  ya'ni ikkita bot Telegram'da konflikt qilmaydi.
- **Neon** — asosiy bazaga ulangan (Database URL to'g'ridan-to'g'gi, `sslmode` config tomonidan avtomatik moslashtiriladi).

**Railway'ga qaytish kerak bo'lsa** (masalan Render'da muammo chiqsa):

```bash
cd ~/yangiliklar-bot && source "$HOME/.railway/env"
# 1) GitHub manzilini qayta ulash
railway service source connect --repo bekzamin316-beep/yangiliklar-bot --branch main --service yangiliklar-bot
# 2) Render xizmatini to'xtatish (dashboard → Suspend) va Railway'ni ishga tushirish
railway redeploy -s yangiliklar-bot
```

> Muhim: **bir vaqtda faqat bitta server polling qilsin** — ikkisi birdan
> `TelegramConflictError` beradi. Bittasini o'chirib, keyin ikkinchisini yoqing.
