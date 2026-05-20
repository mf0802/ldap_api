import os
import uvicorn
from fastapi import FastAPI, Security, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from errors import AppError, app_error_handler
from routes import ldap_routes

# Import the centralized configuration instance
from config import settings

app = FastAPI(title="LDAP API")

# Register the global error handler for AppError exceptions
app.add_exception_handler(AppError, app_error_handler)

# API key header configuration
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

async def validate_api_key(api_key: str = Depends(api_key_header)):
    # Validate against the API key loaded from environment/config
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key"
        )
    return api_key

# Mount the LDAP router and apply API key protection globally
app.include_router(
    ldap_routes.router,
    dependencies=[Depends(validate_api_key)]
)

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", 3000))
    print(f"LDAP API successfully started on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
