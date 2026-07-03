# Tezkor Boshlash Qo'llanmasi

## 1-Qadam: Loyihani GitHubga yuklash

```bash
cd /workspace
git init
git add .
git commit -m "Crypto News Bot initial commit"
git branch -M main
git remote add origin https://github.com/SIZNING_USERNAME/crypto-news-bot.git
git push -u origin main
```

## 2-Qadam: Railway.app-da Deploy (Eng Oson)

### A) GitHub orqali
1. [railway.app](https://railway.app) ga kiring
2. "New Project" -> "Deploy from GitHub repo"
3. Repozitoriyangizni tanlang

### B) Ma'lumotlar bazasini qo'shish
1. "New" -> "Database" -> "PostgreSQL"
2. Avtomatik yaratiladi

### C) Redis qo'shish
1. "New" -> "Datastore" -> "Redis"

### D) Environment Variables
Railway dashboard'da quyidagilarni qo'shing:

```
TELEGRAM_BOT_TOKEN=8391268919:AAG1KEDtKUCTdQeghOoOFQYSYn2FSel9SOg
TELEGRAM_CHANNEL_ID=-1001234567890
ADMIN_ID=SIZNING_ID_BU_YERDA
ENCRYPTION_KEY=openssl_rand_hex_32_natija
DATABASE_URL=${{ Postgres.DATABASE_URL }}
REDIS_URL=${{ Redis.REDIS_URL }}
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=SIZNING_OPENROUTER_KALITINGIZ
```

**Muhim:** 
- `ADMIN_ID` ni @userinfobot dan oling
- `ENCRYPTION_KEY` uchun terminalda: `openssl rand -hex 32`

## 3-Qadam: Oracle Cloud-da Deploy (Bepul VPS)

### SSH orqali ulanish
```bash
ssh -i ~/.ssh/id_rsa ubuntu@<IP_ADDRESS>
```

### Docker o'rnatish
```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
sudo apt install git -y
```

### Loyihani yuklash
```bash
git clone https://github.com/SIZNING_USERNAME/crypto-news-bot.git
cd crypto-news-bot
```

### .env faylini sozlash
```bash
nano .env
```

Quyidagi qiymatlarni kiriting:
```
TELEGRAM_BOT_TOKEN=8391268919:AAG1KEDtKUCTdQeghOoOFQYSYn2FSel9SOg
TELEGRAM_CHANNEL_ID=-1001234567890
ADMIN_ID=SIZNING_TELEGRAM_ID
ENCRYPTION_KEY=TASODIFIY_32_BELGI
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/crypto_news_bot
REDIS_URL=redis://redis:6379/0
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=SIZNING_KALIT
```

### Deploy
```bash
docker compose up -d --build
```

### Loglarni tekshirish
```bash
docker compose logs -f bot
```

## 4-Qadam: Botni test qilish

1. Telegram'da botingizni toping
2. `/start` tugmasini bosing
3. Admin panel ochilishi kerak

## Xatoliklarni tuzatish

### Bot ishga tushmayapti
```bash
docker compose logs bot
```

### Database xatosi
```bash
docker compose restart db
docker compose logs db
```

### Botni to'liq qayta ishga tushirish
```bash
docker compose down
docker compose up -d --build
```

### Resurslarni monitoring qilish
```bash
docker stats
```

## Foydali skriptlar

```bash
# Deploy qilish
./scripts/deploy.sh

# Backup yaratish
./scripts/backup.sh

# Monitoring
./scripts/monitor.sh
```

## Admin buyruqlar

Telegram'da:
- `/start` - Boshlash
- `/stats` - Statistika
- `/ai` - AI sozlamalari
- `/sources` - RSS manbalar
- `/prompts` - Promptlarni tahrirlash
- `/digest` - Digest vaqti
- `/system` - Tizim holati

## Keyingi qadamlar

1. AI API kalitlarni qo'shing (OpenRouter, Groq, yoki Gemini)
2. RSS manbalarni tekshiring
3. Kanal ID to'g'riligiga ishonch hosil qiling
4. Botni test qiling
5. Daily digest vaqtini sozlang
