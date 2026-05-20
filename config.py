import os
from dotenv import load_dotenv

load_dotenv()

class LdapConfig:
    def __init__(self):
        # LDAP connection settings
        self.url = os.getenv("LDAP_URL")
        self.bind_dn = os.getenv("LDAP_BIND_DN")
        self.bind_pw = os.getenv("LDAP_BIND_PW")
        self.search_base = os.getenv("LDAP_SEARCH_BASE")
        
        # Security and environment settings
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.api_key = os.getenv("LOCAL_DEVELOPMENT_KEY")

        # Multi-forest configuration for domain-specific searches
        self.forests = {
            "samdom.example.com": {
                "url": os.getenv("LDAP_URL", "ldap://localhost:389"),
                "search_base": "DC=samdom,DC=example,DC=com"
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
        
        # Basic validation for required LDAP environment variables
        if not all([self.url, self.bind_dn, self.bind_pw, self.search_base]):
            raise ValueError("Missing one or more required LDAP environment variables.")
            
        # Validation for the local development API key
        if not self.api_key:
            raise ValueError("Missing 'LOCAL_DEVELOPMENT_KEY' in environment variables.")

# Singleton instance used throughout the API
settings = LdapConfig()
