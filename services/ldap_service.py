import os
import ssl
import time
from ldap3 import Server, Connection, ALL, Tls
# Use the correct ldap3 network exceptions
from ldap3.core.exceptions import LDAPCommunicationError, LDAPSocketOpenError
from config import settings
from errors import AppError

def _connect_with_retry(server_url: str, bind_dn: str, bind_pw: str, tls_config: Tls) -> Connection:
    """Tries to connect to LDAP. Retries on network errors, fails instantly on auth errors."""
    max_retries = settings.LDAP_MAX_RETRIES
    delay = settings.LDAP_RETRY_DELAY_SECS
    
    # Track the last exception to raise if the loop terminates unexpectedly
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            server = Server(server_url, use_ssl=True, tls=tls_config, get_info=ALL)
            return Connection(server, user=bind_dn, password=bind_pw, auto_bind=True)
        except (LDAPCommunicationError, LDAPSocketOpenError) as e:
            last_exception = e
            if attempt == max_retries - 1:
                raise  # Out of attempts, raise the network error
            
            time.sleep(delay * (attempt + 1))

    # Static type checkers require this fallback so the function never returns None
    if last_exception:
        raise last_exception
    raise LDAPCommunicationError("LDAP connection attempts exhausted without an explicit error.")

def connect_ldap() -> Connection:
    """Create and return a secure ldaps connection to the default domain B."""
    try:
        tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
        return _connect_with_retry(settings.url, settings.bind_dn, settings.bind_pw, tls_config)
    except Exception as e:
        raise AppError(
            status_code=500,
            error="LDAP connection error",
            details=f"Could not connect to default domain B: {str(e)}"
        )

def connect_to_domain(domain_name: str) -> Connection:
    """Dynamically establish an ldaps connection based on the forest name."""
    domain_key = domain_name.lower()
    if domain_key not in settings.forests:
        raise AppError(
            status_code=400,
            error="Configuration error",
            details=f"Domain '{domain_name}' is not configured in settings.forests"
        )
        
    config = settings.forests[domain_key]
    try:
        tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
        return _connect_with_retry(config["url"], config["bind_dn"], config["bind_pw"], tls_config)
    except Exception as e:
        raise AppError(
            status_code=500,
            error="Connection failed",
            details=f"Could not connect to {domain_name}: {str(e)}"
        )
