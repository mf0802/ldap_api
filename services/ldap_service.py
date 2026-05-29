import os
import ssl
import time
from typing import Tuple
from ldap3 import Server, Connection, ALL, Tls
from ldap3.core.exceptions import LDAPCommunicationError, LDAPSocketOpenError
from config import settings
from errors import AppError

def _connect_with_retry(server_url: str, bind_dn: str, bind_pw: str, tls_config: Tls) -> Connection:
    """Tries to connect to LDAP. Retries on network errors, fails instantly on auth errors."""
    max_retries = settings.LDAP_MAX_RETRIES
    delay = settings.LDAP_RETRY_DELAY_SECS
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            server = Server(server_url, use_ssl=True, tls=tls_config, get_info=ALL)
            return Connection(server, user=bind_dn, password=bind_pw, auto_bind=True)
        except (LDAPCommunicationError, LDAPSocketOpenError) as e:
            last_exception = e
            if attempt == max_retries - 1:
                raise 
            
            time.sleep(delay * (attempt + 1))

    if last_exception:
        raise last_exception
    raise LDAPCommunicationError("LDAP connection attempts exhausted without an explicit error.")

def connect_to_domain(domain_name: str) -> Tuple[Connection, str]:
    """Dynamically establish an ldaps connection and return it along with its search base."""
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
        connection = _connect_with_retry(config["url"], config["bind_dn"], config["bind_pw"], tls_config)
        
        # Return both connection and search base for use in API queries
        return connection, config["search_base"]
        
    except Exception as e:
        raise AppError(
            status_code=500,
            error="Connection failed",
            details=f"Could not connect to {domain_name}: {str(e)}"
        )
