import os
import ssl

from ldap3 import Server, Connection, ALL, Tls
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

def connect_ldap_domain_a() -> Connection:
    """Establish a secure LDAPS connection to Domain A."""
    try:
        # Ignore self-signed certificate validation for local docker tests
        tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
        server = Server(settings.domain_a_url, use_ssl=True, tls=tls_config, get_info=ALL)
        return Connection(server, user=settings.domain_a_bind_dn, password=settings.domain_a_bind_pw, auto_bind=True)
    except Exception as e:
        raise AppError(status_code=500, error="Connection Failed", details=f"Domain A LDAPS Error: {str(e)}")

def connect_ldap_domain_b() -> Connection:
    """Establish a secure LDAPS connection to Domain B."""
    try:
        # Ignore self-signed certificate validation for local docker tests
        tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
        server = Server(settings.url, use_ssl=True, tls=tls_config, get_info=ALL)
        return Connection(server, user=settings.bind_dn, password=settings.bind_pw, auto_bind=True)
    except Exception as e:
        raise AppError(status_code=500, error="Connection Failed", details=f"Domain B LDAPS Error: {str(e)}")