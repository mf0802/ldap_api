from ldap3 import Server, Connection, ALL
from config import settings
from errors import AppError

def connect_ldap() -> Connection:
    """Create and return a bound LDAP connection using configuration settings."""
    try:
        server = Server(settings.url, get_info=ALL) # type: ignore
        conn = Connection(server, user=settings.bind_dn, password=settings.bind_pw, auto_bind=True)
        return conn
    except Exception as e:
        # Wrap any LDAP connection error in the application-specific exception type
        raise AppError(status_code=500, error="LDAP Connection Error", details=str(e))