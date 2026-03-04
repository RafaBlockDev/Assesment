output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito App Client ID"
  value       = aws_cognito_user_pool_client.app.id
}

output "cognito_domain" {
  description = "Cognito Hosted UI domain"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "agentcore_cluster_arn" {
  description = "ECS cluster ARN (Agentcore runtime)"
  value       = aws_ecs_cluster.agentcore.arn
}

output "agentcore_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.agent.name
}

output "s3_documents_bucket" {
  description = "S3 bucket for financial documents"
  value       = aws_s3_bucket.documents.id
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for agent logs"
  value       = aws_cloudwatch_log_group.agentcore.name
}
