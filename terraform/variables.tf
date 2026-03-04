variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "api_container_image" {
  description = "Docker image URI for the FastAPI agent (ECR)"
  type        = string
}

variable "instance_type" {
  description = "Instance type for Agentcore runtime"
  type        = string
  default     = "ml.m5.large"
}

variable "cognito_callback_url" {
  description = "OAuth callback URL for Cognito"
  type        = string
  default     = "http://localhost:8000/auth/callback"
}
