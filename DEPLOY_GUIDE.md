# Crypto News Bot — Railway deploy qollanmasi

Bu loyiha GitHub’ga yuklangan:
**https://github.com/aabdukarimov997-ui/crypto-news-bot**

## 1. Railway hisobiga kirish (brauzer orqali)

1. https://railway.com sahifasiga kiring.
2. Botni deploy qilmoqchi bo‘lgan boshqa hisobni tanlang.
3. Dashboard’dan **New Project → Deploy from GitHub repo** ni tanlang.
4. Yuqoridagi `crypto-news-bot` repozitoriysini tanlang.

> Muhim: Berilgan `rlwy_oacs_...` tokeni CLI va GraphQL API bilan ishlatilmadi (Not Authorized). Shuning uchun brauzer orqali deploy qilish eng ishonchli usul.

## 2. PostgreSQL qo'shish

Railway project ichida **New → Database → Add PostgreSQL** tugmasini bosing. Railway avtomatik `DATABASE_URL` o‘zgaruvchisini yaratadi.

## 3. Muhit o'zgaruvchilari (Environment Variables)

Bot xizmatining **Variables** bo‘limida quyigilarni to‘ldiring:

| O‘zgaruvchi | Tavsiya qiymati | Izoh |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | @BotFather’dan olingan token |
| `TELEGRAM_CHANNEL_ID` | `-100...` | Yangiliklar chiqadigan kanal ID |
| `ADMIN_IDS` | `[6194170580]` | Admin Telegram IDlari (JSON ro‘yxat) |
| `DB_TYPE` | `postgres` | Railway PostgreSQL uchun |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Railway avtomatik beradi yoki quyidagi shaklda: `postgresql+asyncpg://user:pass@postgres:5432/db` |
| `AI_PROVIDER` | `dashscope` | DashScope int’l endpoint ishlatiladi |
| `AI_MODEL` | `qwen-turbo` | Asosiy model |
| `DASHSCOPE_API_KEY` | `sk-...` | DashScope API kaliti |
| `DASHSCOPE_API_BASE` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Int’l endpoint |
| `AI_BACKUP_PROVIDER` | `openrouter` (ixtiyoriy) | Backup provayder |
| `AI_BACKUP_API_KEY` | `sk-...` (ixtiyoriy) | Backup kalit |
| `RSS_SOURCES` | `https://www.coindesk.com/arc/outboundfeeds/rss/,...` | Manba URL’lari |
| `NEWS_CHECK_INTERVAL` | `300` | Yangiliklar tekshiruvi (sekund) |
| `DIGEST_HOUR` | `23` | Kunlik dajest soati |
| `DIGEST_MINUTE` | `0` | Kunlik dajest daqiqasi |
| `DIGEST_TIMEZONE` | `Asia/Tashkent` | Vaqt zonasi |

## 4. Telegram kanalga botni admin qilish

Kanal sozlamalaridan botni admin qiling, quyidagi huquqlar bilan:
- Send Messages
- Edit Messages
- Delete Messages
- Post Messages

## 5. Deploy tugmasini bosish

Railway avtomatik build qiladi va botni ishga tushiradi. Loglar bo‘limida xatoliklar tekshiriladi:
- `railway logs` (agar CLI orqali autentifikatsiya o‘rnatsangiz).

## 6. Yangi kodni qayta deploy qilish

GitHub `main` branch’ga har bir `git push` bilan Railway avtomatik qayta deploy qiladi.

## Muhim eslatmalar

- Bu polling bot, shuning uchun `railway.toml` da `healthcheckPath` yo‘q.
- `DB_TYPE=postgres` bo‘lganda bot Railway PostgreSQL bilan ishlaydi.
- Botni bir vaqtning o‘zida faqat bitta nusxasi ishlatishingiz kerak, aks holda `TelegramConflictError` yuzaga keladi.
