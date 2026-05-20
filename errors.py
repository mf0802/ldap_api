from fastapi import Request
from fastapi.responses import JSONResponse

class AppError(Exception):
    def __init__(self, status_code: int, error: str, details: str):
        self.status_code = status_code
        self.error = error
        self.details = details

# Use exc: Exception so this handler can catch both AppError and general exceptions
async def app_error_handler(request: Request, exc: Exception):
    # Optional: a cast or isinstance check ensures the handler can distinguish AppError
    if not isinstance(exc, AppError):
        return JSONResponse(status_code=500, content={"error": "Internal Error", "details": str(exc)})
        
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "details": exc.details}
    )
