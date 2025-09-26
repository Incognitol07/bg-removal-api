from fastapi import Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED
from app.core.config import settings

API_KEY_NAME = "X-API-Key"
API_KEY =  settings.API_KEY

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )
