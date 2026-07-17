terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Networking ───────────────────────────────────────────────────────────────

resource "aws_security_group" "factory" {
  name        = "software-factory"
  description = "Software Factory — 3 VMs + Redis"

  # SSH from admin only
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  # Webhook (orchestrator) — public
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Redis — internal only
  ingress {
    from_port = 6379
    to_port   = 6379
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Project = "software-factory" }
}

# ── Redis VM (shared queue) ──────────────────────────────────────────────────

resource "aws_instance" "redis" {
  ami           = var.ami_id
  instance_type = "t3.micro"
  key_name      = var.key_name

  vpc_security_group_ids = [aws_security_group.factory.id]

  user_data = <<-EOF
    #!/bin/bash
    apt-get update -y && apt-get install -y redis-server
    sed -i 's/^bind 127.0.0.1.*/bind 0.0.0.0/' /etc/redis/redis.conf
    echo "requirepass ${var.redis_password}" >> /etc/redis/redis.conf
    systemctl restart redis-server && systemctl enable redis-server
  EOF

  tags = { Name = "factory-redis", Role = "redis" }
}

# ── VM1: Orchestrator ────────────────────────────────────────────────────────

resource "aws_instance" "orchestrator" {
  ami           = var.ami_id
  instance_type = "t3.small"
  key_name      = var.key_name

  vpc_security_group_ids = [aws_security_group.factory.id]

  user_data = templatefile("${path.module}/scripts/setup.sh", {
    role                  = "orchestrator"
    redis_host            = aws_instance.redis.private_ip
    redis_password        = var.redis_password
    anthropic_api_key     = var.anthropic_api_key
    github_token          = var.github_token
    github_webhook_secret = var.github_webhook_secret
  })

  tags = { Name = "factory-orchestrator", Role = "orchestrator" }
}

# ── VM2: Implementor ─────────────────────────────────────────────────────────

resource "aws_instance" "implementor" {
  ami           = var.ami_id
  instance_type = "t3.medium"  # more CPU for running tests
  key_name      = var.key_name

  vpc_security_group_ids = [aws_security_group.factory.id]

  user_data = templatefile("${path.module}/scripts/setup.sh", {
    role                  = "implementor"
    redis_host            = aws_instance.redis.private_ip
    redis_password        = var.redis_password
    anthropic_api_key     = var.anthropic_api_key
    github_token          = var.github_token
    github_webhook_secret = var.github_webhook_secret
  })

  tags = { Name = "factory-implementor", Role = "implementor" }
}

# ── VM3: Reviewer ────────────────────────────────────────────────────────────

resource "aws_instance" "reviewer" {
  ami           = var.ami_id
  instance_type = "t3.small"
  key_name      = var.key_name

  vpc_security_group_ids = [aws_security_group.factory.id]

  user_data = templatefile("${path.module}/scripts/setup.sh", {
    role                  = "reviewer"
    redis_host            = aws_instance.redis.private_ip
    redis_password        = var.redis_password
    anthropic_api_key     = var.anthropic_api_key
    github_token          = var.github_token
    github_webhook_secret = var.github_webhook_secret
  })

  tags = { Name = "factory-reviewer", Role = "reviewer" }
}
