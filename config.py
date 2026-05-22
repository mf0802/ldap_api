# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class LdapConfig:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.api_key = os.getenv("X_API_KEY") or os.getenv("LOCAL_DEVELOPMENT_KEY")
        
        # Backward compatibility aliases pointing to Domain B
        self.url: str = os.getenv("DOMAIN_B_SERVER", "ldaps://localhost:3636")
        self.bind_dn: str = os.getenv("DOMAIN_B_USER","")
        self.bind_pw: str = os.getenv("DOMAIN_B_PASSWORD", "")
        self.search_base: str = os.getenv("DOMAIN_B_SEARCH_BASE", "DC=samdom,DC=example,DC=com")

        self.LDAP_MAX_RETRIES = int(os.getenv("LDAP_MAX_RETRIES", 3))
        self.LDAP_RETRY_DELAY_SECS = int(os.getenv("LDAP_RETRY_DELAY_SECS", 2))
        
        # Multi-forest configuration loaded 100% from environment variables
        self.forests = {
            "domaina.local": {
                "url": os.getenv("DOMAIN_A_SERVER", "ldaps://localhost:636"),
                "bind_dn": os.getenv("DOMAIN_A_USER"),
                "bind_pw": os.getenv("DOMAIN_A_PASSWORD"),
                "search_base": os.getenv("DOMAIN_A_SEARCH_BASE", "DC=domainA,DC=local")
            },
            "samdom.example.com": {
                "url": self.url,
                "bind_dn": self.bind_dn,
                "bind_pw": self.bind_pw,
                "search_base": self.search_base
            },
            "test.forest.net": {
                "url": os.getenv("DOMAIN_C_SERVER", "ldaps://localhost:4636"),
                "bind_dn": os.getenv("DOMAIN_C_USER"),
                "bind_pw": os.getenv("DOMAIN_C_PASSWORD"),
                "search_base": os.getenv("DOMAIN_C_SEARCH_BASE", "DC=test,DC=forest,DC=net")
            }
        }
        
        # Basic validation to prevent app start with missing critical config
        if not self.api_key:
            raise ValueError("Missing 'X_API_KEY' or 'LOCAL_DEVELOPMENT_KEY' in environment variables.")

settings = LdapConfig()
