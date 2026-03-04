from functools import lru_cache

import boto3
from langfuse import Langfuse
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    cognito_client_secret: str = ""
    cognito_domain: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # App
    api_title: str = "Amazon Stock Agent"
    api_environment: str = "development"
    app_port: int = 8000
    debug: bool = True
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_boto_session() -> boto3.Session:
    settings = get_settings()
    return boto3.Session(
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )



def get_cognito_client():
    return get_boto_session().client("cognito-idp")


def get_s3_client():
    return get_boto_session().client("s3")


def get_langfuse() -> Langfuse:
    settings = get_settings()
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
