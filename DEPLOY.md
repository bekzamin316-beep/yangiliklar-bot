# Deploy Qo'llanmasi

## 1. Bepul VPS Variantlari

### A) Oracle Cloud Free Tier (Eng yaxshi variant)
- 4 ta ARM CPU, 24GB RAM, 200GB disk
- Doimiy bepul
- [Ro'yxatdan o'tish](https://cloud.oracle.com/)

### B) Google Cloud Run
- Oyiga 2 million so'rov bepul
- Serverless
- [Boshlash](https://cloud.google.com/run)

### C) Fly.io
- 3 ta shared CPU VM bepul
- [Fly.io](https://fly.io/)

### D) Railway.app
- $5 kredit oyiga
- Avtomatik deploy
- [Railway](https://railway.app/)

## 2. Oracle Cloud-da Deploy (Tavsiya etiladi)

### 2.1 SSH orqali ulanish
```bash
ssh -i ~/.ssh/id_rsa ubuntu@<IP_ADDRESS>
```

### 2.2 Docker o'rnatish
```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
sudo apt install git -y
```

### 2.3 Loyihani yuklash
```bash
git clone <SIZNING_REPO_URL>
cd crypto-news-bot
```

### 2.4 .env faylini yaratish
```bash
nano .env
```

Quyidagi ma'lumotlarni kiriting:
```
TELEGRAM_BOT_TOKEN=8391268919:AAG1KEDtKUCTdQeghOoOFQYSYn2FSel9SOg
TELEGRAM_CHANNEL_ID=-1001234567890
ADMIN_ID=<SIZNING_TELEGRAM_ID>
ENCRYPTION_KEY=<RANDOM_32_CHAR_STRING>
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/crypto_news_bot
REDIS_URL=redis://redis:6379/0
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<SIZNING_OPENROUTER_KALIT>
```

**Muhim:** 
- `ADMIN_ID` ni olish uchun @userinfobot ga yozing
- `ENCRYPTION_KEY` uchun: `openssl rand -hex 32` buyrug'ini ishlatish mumkin
- AI API kalitlarni mos provayderlardan oling

### 2.5 Deploy qilish
```bash
docker compose up -d --build
```

### 2.6 Loglarni tekshirish
```bash
docker compose logs -f bot
```

### 2.7 Botni test qilish
Telegram'da botingizga `/start` deb yozing.

## 3. Railway.app-da Deploy (Eng oson)

### 3.1 GitHubga kodni yuklang
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <SIZNING_GITHUB_REPO>
git push -u origin main
```

### 3.2 Railway'da loyiha yarating
1. [railway.app](https://railway.app) ga kiring
2. "New Project" tugmasini bosing
3. "Deploy from GitHub repo" tanlang
4. Repozitoriyangizni tanlang

### 3.3 Ma'lumotlar bazasini qo'shing
1. "New" -> "Database" -> "PostgreSQL"
2. PostgreSQL avtomatik yaratiladi

### 3.4 Redis qo'shing
1. "New" -> "Datastore" -> "Redis"

### 3.5 Environment Variables sozlash
Railway dashboard'da "Variables" bo'limida quyidagilarni qo'shing:

```
TELEGRAM_BOT_TOKEN=8391268919:AAG1KEDtKUCTdQeghOoOFQYSYn2FSel9SOg
TELEGRAM_CHANNEL_ID=-1001234567890
ADMIN_ID=<SIZNING_ID>
ENCRYPTION_KEY=<RANDOM_KEY>
DATABASE_URL=${{ Postgres.DATABASE_URL }}
REDIS_URL=${{ Redis.REDIS_URL }}
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<SIZNING_KALIT>
```

### 3.6 Deploy
Railway avtomatik deploy qiladi. Status yashil bo'lganda bot tayyor.

## 4. Xatoliklarni tuzatish

### Bot ishga tushmayapti
```bash
docker compose logs bot
```

### Database xatoligi
```bash
docker compose restart db
docker compose logs db
```

### Redis xatoligi
```bash
docker compose restart redis
docker compose logs redis
```

### Botni qayta ishga tushirish
```bash
docker compose down
docker compose up -d --build
```

### Loglarni ko'rish
```bash
docker compose logs -f
docker compose logs -f bot
docker compose logs -f db
docker compose logs -f redis
```

## 5. Admin Panel ishlatish

Bot ishga tushgach, Telegram'da:

1. `/start` - Botni boshlash
2. `/stats` - Statistika ko'rish
3. `/ai` - AI sozlamalarini o'zgartirish
4. `/sources` - RSS manbalarini boshqarish
5. `/prompts` - Promptlarni tahrirlash
6. `/digest` - Kunlik digest vaqti
7. `/system` - Tizim holati

## 6. Muhim eslatmalar

1. **Xavfsizlik**: `.env` faylni hech qachon GitHubga yuklamang
2. **API Kalitlar**: Har doim maxfiy saqlang
3. **Backup**: Ma'lumotlar bazasini muntazam backup qiling
4. **Monitoring**: `docker stats` bilan resurslarni kuzating
5. **Yangilash**: `docker compose pull && docker compose up -d`

## 7. Yordam

Agar muammo yuzaga kelsa:
1. Loglarni tekshiring: `docker compose logs -f`
2. Xato xabarini o'qing
3. .env fayldagi qiymatlarni tekshiring
4. Docker container'larning holatini tekshiring: `docker compose ps`
