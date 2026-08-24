# HF Spaces'ga ko'chirish — bosqichma-bosqich

Bot Hugging Face Spaces'da **1 yildan ham uzoq, kartasiz** ishlashi uchun to'liq qo'llanma.

## Arxitektura

| Qism | Xizmat | Narx |
|---|---|---|
| Bot konteyneri | HF Spaces (2 vCPU, 16GB RAM) | Bepul |
| PostgreSQL | Neon.tech | Bepul (0.5GB) |
| Redis (ixtiyoriy) | Upstash yoki avto-kashf | Bepul |

Uxlamaslik tizimi: bot har 15 daqiqada o'zining `/health` sahifasiga so'rov yuboradi (`SPACE_HOST` orqali). Zaxira sifatida cron-job.org ham qo'shish mumkin.

---

## 1-qadam: HF akkaunt va Space

1. [huggingface.co](https://huggingface.co) → Sign Up (bepul)
2. Yuqori o'ngda **New** → **Space**
3. Sozlamalar:
   - Space name: `crypto-news-bot`
   - License: boshqasi (any)
   - **Space SDK: Docker** → Blank
   - Visibility: Public (kod maxfiy narsa saqlamaydi — kalitlar Secrets'da bo'ladi)
4. **Create Space**

## 2-qadam: Kodni Space'ga yuklash

**A) Men qilsin:** [hf.co/settings/tokens](https://huggingface.co/settings/tokens) → New token → **Write** huquqi → token menga — men barcha fayllarni push qilaman.

**B) O'zingiz:** Space → Files → Add file → quyidagi fayllarni yuklang:
`Dockerfile`, `requirements.txt`, `pyproject.toml`, `.env.example` va butun `src/` papkasi (repo ildizidan).

## 3-qadam: Neon Postgres

1. [neon.tech](https://neon.tech) → Sign up with GitHub (kartasiz)
2. Project yaratish → **Connection string** ni nusxalang (`postgresql://...neon.tech/neondb`)
3. Oxiriga `?sslmode=require` qo'shilganini tekshiring

## 4-qadam: Secrets kiritish

Space → **Settings** → **Variables and secrets**:

| Name | Value | Secret |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather'dagi token | ✅ |
| `TELEGRAM_CHANNEL_ID` | Kanal ID (-100...) | ✅ |
| `ADMIN_IDS` | Sizning Telegram ID | ❌ |
| `DB_TYPE` | `postgres` | ❌ |
| `DATABASE_URL` | Neon connection string | ✅ |
| `ADMIN_PASSWORD` | Admin panel PIN (5 xona) | ✅ |
| `DIGEST_SOURCE_CHANNELS` | Digest manba kanallari | ❌ |

Ixtiyoriy: `REDIS_URL` (Upstash), `TELEGRAM_API_ID/HASH/SESSION_STRING` (Telethon), `DASHSCOPE_API_KEY`.

> AI provayder: `AI_PROVIDER` belgilanmasa kod DashScope'ni tanlaydi; kalit yo'q bo'lsa loglarda ko'rinadi.

## 5-qadam: Ishga tushirish

Secretlar saqlanganda Space avtomatik rebuild bo'ladi. **Logs** tabida quyidagilarni ko'rasiz:

```
Health server listening on 0.0.0.0:7860
Scheduler configured (digest): ... digest at 08:00, 12:00, 18:00, 22:00 (Asia/Tashkent)
Redis connected via auto-discovery        ← agar Upstash bo'lsa
Database initialized                      ← Neon
```

## Eski Railway'ni o'chirish

Yangi bot bir necha kun muammosiz ishlagach:
- Railway → perceptive-perfection → Settings → Delete project
- ⚠️ Avval eski ma'lumotlarni saqlash kerak bo'lsa — ayting, dump olaman

## Boshqa bot ulash (shu kod bilan)

Kod to'liq env-driven — yangi bot = yangi Space + boshqa secretlar:

1. Yangi Space oching (xuddi 1-qadam)
2. Xuddi shu kodni yuklang
3. Faqat boshqa qiymatlar: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `ADMIN_IDS`, boshqa `DIGEST_SCHEDULE_TIMES`
4. Ikki bot bir-biridan mustaqil ishlaydi

## Cheklovlar / bilib qo'yish kerak

- Free Space vaqti-vaqti bilan restart bo'ladi (~30-60s tiklanish)
- Restart paytidagi yangiliklar yo'qolmaydi — RSS'da qoladi, keyin yig'iladi
- Neon free bazada ma'lumot 6 oy faolsizda arxivlanadi — bot doim ishlab turganida muammo yo'q
