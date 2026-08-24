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
4. Eski ma'lumotlarni saqlash kerak bo'lsa — ayting, Railway Postgres'dan dump olaman

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
