# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class LdapConfig:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.api_key = os.getenv("X_API_KEY") or os.getenv("LOCAL_DEVELOPMENT_KEY")
        
        # 1. Read the comma-separated string from the environment
        raw_attributes = os.getenv("LEGAL_HOLD_ATTRIBUTE_NAMES", "description,comment")
        
        # 2. Parse it into a clean, whitespace-stripped list of lowercase strings
        self.legal_hold_attributes = [
            attr.strip().lower() for attr in raw_attributes.split(",") if attr.strip()
        ]
        
        self.LDAP_MAX_RETRIES = int(os.getenv("LDAP_MAX_RETRIES", 3))
        self.LDAP_RETRY_DELAY_SECS = int(os.getenv("LDAP_RETRY_DELAY_SECS", 2))
        
        # Dynamically parse all forests from the environment variables
        self.forests = self._parse_forests()
        
        # Backward compatibility aliases pointing specifically to Domain B (samdom.example.com)
        domain_b_config = self.forests.get("samdom.example.com", {})
        self.url: str = domain_b_config.get("url", "ldaps://localhost:3636")
        self.bind_dn: str = domain_b_config.get("bind_dn", "")
        self.bind_pw: str = domain_b_config.get("bind_pw", "")
        self.search_base: str = domain_b_config.get("search_base", "DC=samdom,DC=example,DC=com")

        # Basic validation to prevent app start with missing critical config
        if not self.api_key:
            raise ValueError("Missing 'X_API_KEY' or 'LOCAL_DEVELOPMENT_KEY' in environment variables.")


    def _parse_forests(self) -> dict:
        forests_map = {}
        project_root = os.path.dirname(os.path.abspath(__file__))
        default_certs_dir = os.path.join(project_root, "dev-certs")
        
        prefixes = set(
            key.rsplit('_', 1)[0] 
            for key in os.environ 
            if key.startswith('DOMAIN_') and key.endswith('_NAME')
        )
        
        for prefix in prefixes:
            domain_name = os.getenv(f"{prefix}_NAME")
            if not domain_name:
                continue
                
            # Check for explicitly provided paths, or fall back to defaults
            ca_path = os.getenv(f"{prefix}_CA_CERT_PATH", os.path.join(default_certs_dir, "ca.crt"))
            client_cert = os.getenv(f"{prefix}_CLIENT_CERT_PATH", os.path.join(default_certs_dir, "client.crt"))
            client_key = os.getenv(f"{prefix}_CLIENT_KEY_PATH", os.path.join(default_certs_dir, "client.key"))
            
            # Smart Check: If the client certificate files don't exist on disk, 
            # set them to None so the connection script knows it's a standard password-based LDAPS environment.
            if not os.path.exists(client_cert) or not os.path.exists(client_key):
                client_cert = None
                client_key = None

            forests_map[domain_name.lower()] = {
                "url": os.getenv(f"{prefix}_SERVER"),
                "bind_dn": os.getenv(f"{prefix}_USER"),
                "bind_pw": os.getenv(f"{prefix}_PASSWORD"),
                "search_base": os.getenv(f"{prefix}_SEARCH_BASE"),
                
                "ca_cert_path": ca_path,
                "client_cert_path": client_cert,
                "client_key_path": client_key,
            }
            
        return forests_map

settings = LdapConfig()
