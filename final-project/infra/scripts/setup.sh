#!/bin/bash
set -e

ROLE="${role}"
REDIS_HOST="${redis_host}"

# System deps
apt-get update -y
apt-get install -y python3.11 python3-pip git docker.io docker-compose-plugin curl
systemctl enable docker && systemctl start docker

# Clone the factory repo
git clone https://github.com/YOUR_ORG/YOUR_FACTORY_REPO /opt/factory
cd /opt/factory

# Write .env
cat > /opt/factory/.env <<ENVFILE
ANTHROPIC_API_KEY=${anthropic_api_key}
GITHUB_TOKEN=${github_token}
GITHUB_WEBHOOK_SECRET=${github_webhook_secret}
REDIS_HOST=${redis_host}
REDIS_PASSWORD=${redis_password}
ENVFILE

chmod 600 /opt/factory/.env

# Start the right service for this role
case "$ROLE" in
  orchestrator)
    docker compose up -d orchestrator spec-watcher
    ;;
  implementor)
    docker compose up -d implementor
    ;;
  reviewer)
    docker compose up -d reviewer
    ;;
esac
