import logging
import ssl
import time
from typing import Tuple
from ldap3 import Server, Connection, ALL, Tls
from ldap3.core.exceptions import LDAPCommunicationError, LDAPSocketOpenError
from config import settings
from errors import AppError

# Just for debugging purposes, can be removed in production
logger = logging.getLogger("uvicorn.error")

def _connect_with_retry(server_url: str, bind_dn: str, bind_pw: str, tls_config: Tls) -> Connection:
    """Tries to connect to LDAPS. Retries on network errors, fails instantly on auth errors."""
    max_retries = settings.LDAP_MAX_RETRIES
    delay = settings.LDAP_RETRY_DELAY_SECS
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            server = Server(server_url, use_ssl=True, tls=tls_config, get_info=ALL)
            # Authenticate securely over the certificate channel using credentials
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
    """Dynamically establish a secure LDAPS connection. 
    Adapts automatically between Dev (mTLS) and Prod (Standard credentials over LDAPS) with zero code changes."""
    domain_key = domain_name.lower()
    if domain_key not in settings.forests:
        raise AppError(
            status_code=400,
            error="Configuration error",
            details=f"Domain '{domain_name}' is not configured in settings.forests"
        )
        
    config = settings.forests[domain_key]
    try:
        # 1. Determine strictness based on the environment flag
        # Development bypasses 'localhost' checks; Production strictly enforces certificate integrity
        validation_mode = ssl.CERT_REQUIRED if settings.environment == "production" else ssl.CERT_NONE
        
        # 2. Build Tls options dynamically based on available configuration keys
        tls_args = {
            "ca_certs_file": config["ca_cert_path"],
            "validate": validation_mode,
            "version": ssl.PROTOCOL_TLSv1_2
        }
        
        # 3. Only pass client certificates if they exist on the hosting file system
        if config["client_cert_path"] and config["client_key_path"]:
            tls_args["local_certificate_file"] = config["client_cert_path"]
            tls_args["local_private_key_file"] = config["client_key_path"]
            client_certs_sent = True
            
        tls_config = Tls(**tls_args)
        
        # 4. Bind using the standard credential flow
        connection = _connect_with_retry(
            config["url"], 
            config["bind_dn"], 
            config["bind_pw"], 
            tls_config
        )

        # --- LOGGER DEBUG OUTPUT ---
        logger.info(
            f"[LDAP CONNECT] Domain: {domain_name.upper()} | "
            f"URL: {config['url']} | "
            f"Auth: {connection.authentication} | "
            f"TLS: {connection.server.ssl} | "
            f"ClientCerts: {client_certs_sent} | "
            f"VerifyMode: {'Strict' if validation_mode == ssl.CERT_REQUIRED else 'Lax'} | "
            f"User: {connection.user}"
        )
        
        return connection, config["search_base"]
        
    except Exception as e:
        raise AppError(
            status_code=500,
            error="Connection failed",
            details=f"Could not connect to {domain_name}: {str(e)}"
        )


