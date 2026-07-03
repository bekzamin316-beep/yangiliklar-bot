#!/bin/bash

# Crypto News Bot Deploy Script
set -e

echo "🚀 Starting deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Installing..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed. Please logout and login again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose plugin not found."
    exit 1
fi

# Create .env if not exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration:"
    echo "   nano .env"
    exit 1
fi

# Pull latest changes (if in git repo)
if [ -d .git ]; then
    echo "📥 Pulling latest changes..."
    git pull || true
fi

# Build and start services
echo "🔨 Building containers..."
docker compose down --remove-orphans || true
docker compose up -d --build

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# Check status
echo "📊 Service status:"
docker compose ps

echo ""
echo "✅ Deployment complete!"
echo "Use 'docker compose logs -f' to view logs"
echo "Use 'docker compose down' to stop services"
