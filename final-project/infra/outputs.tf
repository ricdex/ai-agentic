output "webhook_url" {
  value       = "http://${aws_instance.orchestrator.public_ip}:8000/webhook"
  description = "Paste this in GitHub repo → Settings → Webhooks"
}

output "orchestrator_ip" {
  value = aws_instance.orchestrator.public_ip
}

output "implementor_ip" {
  value = aws_instance.implementor.public_ip
}

output "reviewer_ip" {
  value = aws_instance.reviewer.public_ip
}

output "redis_private_ip" {
  value = aws_instance.redis.private_ip
}
