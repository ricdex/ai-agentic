variable "aws_region" {
  default = "us-east-1"
}

variable "ami_id" {
  description = "Ubuntu 22.04 LTS (us-east-1)"
  default     = "ami-0c7217cdde317cfec"
}

variable "key_name" {
  description = "EC2 Key Pair name for SSH access"
}

variable "admin_cidr" {
  description = "Your IP/CIDR for SSH access, e.g. 1.2.3.4/32"
}

variable "redis_password" {
  description = "Password for Redis"
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key"
  sensitive   = true
}

variable "github_token" {
  description = "GitHub token with repo + issues + pull_requests scopes"
  sensitive   = true
}

variable "github_webhook_secret" {
  description = "GitHub webhook secret"
  sensitive   = true
}
