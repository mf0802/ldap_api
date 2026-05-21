import os
import ssl

from ldap3 import Server, Connection, ALL, Tls
from config import settings
from errors import AppError

def connect_ldap() -> Connection:
    """
    Create and return a secure LDAPS connection to the default Domain B (samdom).
    Ensures backward compatibility for all existing single-domain routes.
    """
    try:
        # Ignore self-signed certificates for local Docker development
        tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
        server = Server(settings.url, use_ssl=True, tls=tls_config, get_info=ALL)
        
        conn = Connection(
            server, 
            user=settings.bind_dn, 
            password=settings.bind_pw, 
            auto_bind=True
        )
        return conn
    except Exception as e:
        raise AppError(
            status_code=500, 
            error="LDAP Connection Error", 
            details=f"Could not connect to default Domain B: {str(e)}"
        )

def connect_to_domain(domain_name: str) -> Connection:
    """Dynamically establish an LDAPS connection based on the forest name."""
    # Normalize input to lowercase
    domain_key = domain_name.lower()
    
    # Check if the requested domain is configured
    if domain_key not in settings.forests:
        raise AppError(
            status_code=400, 
            error="Configuration Error", 
            details=f"Domain '{domain_name}' is not configured in settings.forests"
        )
        
    config = settings.forests[domain_key]
    
    try:
        tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
        server = Server(config["url"], use_ssl=True, tls=tls_config, get_info=ALL)
        
        return Connection(
            server, 
            user=config["bind_dn"], 
            password=config["bind_pw"], 
            auto_bind=True
        )
    except Exception as e:
        raise AppError(
            status_code=500, 
            error="Connection Failed", 
            details=f"Could not connect to {domain_name}: {str(e)}"
        )