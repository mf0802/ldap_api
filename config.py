# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class LdapConfig:
    def __init__(self):
        # --- Domain B (Target Domain / Your original main setup) ---
        # Now points to the secure LDAPS server from your .env
        self.url = os.getenv("DOMAIN_B_SERVER", "ldaps://localhost:3636")
        self.bind_dn = os.getenv("DOMAIN_B_USER")
        self.bind_pw = os.getenv("DOMAIN_B_PASSWORD")
        self.search_base = "DC=samdom,DC=example,DC=com"
        
        # --- Domain A (Source Domain for Cloning) ---
        # Now points to the secure LDAPS server from your .env
        self.domain_a_url = os.getenv("DOMAIN_A_SERVER", "ldaps://localhost:636")
        self.domain_a_bind_dn = os.getenv("DOMAIN_A_USER")
        self.domain_a_bind_pw = os.getenv("DOMAIN_A_PASSWORD")
        self.domain_a_search_base = "DC=domainA,DC=local"

        # Security and environment settings
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.api_key = os.getenv("X_API_KEY") or os.getenv("LOCAL_DEVELOPMENT_KEY")

        # Multi-forest configuration for domain-specific searches
        # Updated with secure LDAPS URLs for local development
        self.forests = {
            "://example.com": {
                "url": self.url,
                "search_base": self.search_base
            },
            "domainA.local": {
                "url": self.domain_a_url,
                "search_base": self.domain_a_search_base
            },
            "prod.firma.local": {
                "url": "ldap://prod-dc01.firma.local:389",
                "search_base": "DC=prod,DC=firma,DC=local"
            },
            "test.forest.net": {
                "url": "ldap://test-dc01.forest.net:389",
                "search_base": "DC=test,DC=forest,DC=net"
            }
        }
        
        # Validation for Domain B (Target) environment variables
        if not all([self.url, self.bind_dn, self.bind_pw]):
            raise ValueError("Missing one or more required Domain B configuration variables (DOMAIN_B_*).")
            
        # Validation for Domain A (Source) environment variables
        if not all([self.domain_a_url, self.domain_a_bind_dn, self.domain_a_bind_pw]):
            raise ValueError("Missing one or more required Domain A configuration variables (DOMAIN_A_*).")
            
        # Validation for the API security key
        if not self.api_key:
            raise ValueError("Missing 'X_API_KEY' or 'LOCAL_DEVELOPMENT_KEY' in environment variables.")

# Singleton instance used throughout the API
settings = LdapConfig()
