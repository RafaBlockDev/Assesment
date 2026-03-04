import hashlib
import hmac
import base64
import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_cognito_client, get_settings, Settings

logger = logging.getLogger(__name__)
security = HTTPBearer()


class CognitoAuth:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client = get_cognito_client()

    def _get_secret_hash(self, username: str) -> str:
        msg = username + self._settings.cognito_client_id
        secret = self._settings.cognito_client_secret.encode("utf-8")
        digest = hmac.new(secret, msg.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    def verify_token(self, token: str) -> dict[str, Any]:
        """Validate a Cognito access token and return its claims."""
        try:
            response = self._client.get_user(AccessToken=token)
            return {
                "username": response["Username"],
                "attributes": {
                    attr["Name"]: attr["Value"]
                    for attr in response.get("UserAttributes", [])
                },
            }
        except self._client.exceptions.NotAuthorizedException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is invalid or expired",
            )
        except self._client.exceptions.UserNotFoundException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        except Exception as e:
            logger.error("Token verification failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error",
            )

    def get_user_info(self, token: str) -> dict[str, Any]:
        """Extract user profile information from a valid token."""
        data = self.verify_token(token)
        attrs = data["attributes"]
        return {
            "username": data["username"],
            "email": attrs.get("email", ""),
            "name": attrs.get("name", ""),
            "email_verified": attrs.get("email_verified", "false") == "true",
            "sub": attrs.get("sub", ""),
        }

    def initiate_auth(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate user with username/password and return tokens."""
        try:
            auth_params = {
                "USERNAME": username,
                "PASSWORD": password,
            }
            if self._settings.cognito_client_secret:
                auth_params["SECRET_HASH"] = self._get_secret_hash(username)

            response = self._client.initiate_auth(
                ClientId=self._settings.cognito_client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters=auth_params,
            )
            result = response["AuthenticationResult"]
            return {
                "access_token": result["AccessToken"],
                "id_token": result["IdToken"],
                "refresh_token": result.get("RefreshToken", ""),
                "expires_in": result["ExpiresIn"],
                "token_type": result["TokenType"],
            }
        except self._client.exceptions.NotAuthorizedException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        except self._client.exceptions.UserNotFoundException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        except Exception as e:
            logger.error("Auth initiation failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error",
            )


def get_cognito_auth() -> CognitoAuth:
    return CognitoAuth()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth: CognitoAuth = Depends(get_cognito_auth),
) -> dict[str, Any]:
    """FastAPI dependency that extracts and validates the current user."""
    return auth.get_user_info(credentials.credentials)
