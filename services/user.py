import secrets
import string
from typing import Literal, Optional

from ldap3 import MODIFY_REPLACE
from pydantic import BaseModel
from services.ldap_service import connect_ldap
from services.ldap_service import connect_to_domain
from errors import AppError

class CreateUserPayload(BaseModel):
    sam_account_name: str
    first_name: str
    last_name: str
    ou_dn: str  # Target organizational unit DN for the new user

class DynamicCloneUserPayload(BaseModel):
    source_domain: str       # e.g., "domaina.local" or "test.forest.net"
    source_user_dn: str      # Full source Distinguished Name (DN)
    target_domain: str       # e.g., "://example.com"
    target_ou_dn: str        # Target OU where the user should be cloned into
    temporary_password: Optional[str] = None  # Optional, will be auto-generated if omitted

def create_user(payload: CreateUserPayload) -> str:
    """Create a new Active Directory user entry and return its distinguishedName."""
    conn = connect_ldap()
    dn = f"CN={payload.first_name} {payload.last_name},{payload.ou_dn}"
    attrs = {
        'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
        'sAMAccountName': payload.sam_account_name,
        'givenName': payload.first_name,
        'sn': payload.last_name,
        'userAccountControl': '514'  # Disabled account status, password must be set later
    }
    # Try to create the user object in LDAP and raise a structured error on failure
    if not conn.add(dn, attributes=attrs):
        raise AppError(status_code=400, error="LDAP Operation Failed", details=conn.result.get('description', 'Failed to create user'))
    
    return dn

def generate_ad_compliant_password(length: int = 16) -> str:
    """Generate a random password that meets strict Active Directory complexity rules."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^*()_+-="
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure it contains at least one lowercase, one uppercase, one digit, and one special character
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^*()_+-=" for c in password)):
            return password
        
def clone_user(payload: DynamicCloneUserPayload) -> dict:
    """
    Clones a user from any configured source domain to any target domain,
    copies optional attributes, sets a password, and enforces password change on next logon.
    """
    # Determine the password: Use provided one or generate a random secure one
    generated_pass = False
    password_to_use = payload.temporary_password
    
    if not password_to_use:
        password_to_use = generate_ad_compliant_password()
        generated_pass = True

    # 1. Dynamically fetch connections for the requested domain combination
    conn_source = connect_to_domain(payload.source_domain)
    conn_target = connect_to_domain(payload.target_domain)
    
    # Using try...finally to absolutely guarantee network connection cleanup
    try:
        # 2. Fetch user data from the source domain
        from ldap3.core.exceptions import LDAPInvalidDnError # Import the specific error
        
        try:
            if not conn_source.search(
                search_base=payload.source_user_dn, 
                search_filter='(objectClass=user)', 
                attributes=[
                    'sAMAccountName', 'givenName', 'sn', 'displayName', 
                    'mail', 'title', 'department', 'telephoneNumber'
                ]
            ) or not conn_source.entries:
                raise AppError(
                    status_code=404, 
                    error="Source User Not Found", 
                    details=f"Could not find user in source domain '{payload.source_domain}'"
                )
        except LDAPInvalidDnError:
            raise AppError(
                status_code=400,
                error="Invalid DN Syntax",
                details=f"The syntax for 'source_user_dn' ({payload.source_user_dn}) is malformed. Use format: CN=Name,OU=OU,DC=Domain,DC=com"
            )
            
        source_entry = conn_source.entries[0]
        
        # 3. Prepare target DN for target domain
        cn_value = f"{source_entry.givenName.value} {source_entry.sn.value}"
        target_dn = f"cn={cn_value},{payload.target_ou_dn}"
        
        # 4. Build attribute dictionary for the new target user
        # 'userAccountControl': '512' enables the account immediately (Normal Account)
        target_attrs = {
            'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
            'cn': cn_value,
            'sn': source_entry.sn.value,
            'givenName': source_entry.givenName.value,
            'displayName': source_entry.displayName.value,
            'sAMAccountName': source_entry.sAMAccountName.value,
            'userAccountControl': '512' 
        }
        
        # Dynamically copy optional attributes if they exist in the source account
        optional_attrs = ['mail', 'title', 'department', 'telephoneNumber']
        for attr in optional_attrs:
            if hasattr(source_entry, attr) and getattr(source_entry, attr).value:
                target_attrs[attr] = getattr(source_entry, attr).value

        # 5. Create the initial account structure in the target domain
        if not conn_target.add(target_dn, attributes=target_attrs):
            raise AppError(
                status_code=400, 
                error="Clone Operation Failed", 
                details=conn_target.result.get('description', f"Failed to create cloned user structure in '{payload.target_domain}'")
            )
            
        # 6. Set temporary password via secure LDAPS connection
        try:
            encoded_password = f'"{password_to_use}"'.encode('utf-16-le')
            password_changes = {'unicodePwd': [(MODIFY_REPLACE, [encoded_password])]}
            
            # Execute modification safely over TLS
            conn_target.modify(target_dn, password_changes)
            
            # Verify the LDAP result code (0 = success)
            if conn_target.result.get('result', 0) != 0:
                conn_target.delete(target_dn)
                raise AppError(
                    status_code=400, 
                    error="Password Setup Failed", 
                    details=conn_target.result.get('description', 'Password policy violation.')
                )
                
        except Exception as e:
            conn_target.delete(target_dn)
            raise AppError(
                status_code=400, 
                error="Password Operation Exception", 
                details=str(e)
            )
            
        # 7. Enforce "User must change password at next logon"
        # The value [0] must be explicitly passed inside the tuple list
        pwd_expiry_changes = {'pwdLastSet': [(MODIFY_REPLACE, [0])]}
        
        if not conn_target.modify(target_dn, pwd_expiry_changes):
            raise AppError(
                status_code=400, 
                error="Force Password Change Failed", 
                details=conn_target.result.get('description', 'Could not set pwdLastSet to 0')
            )
            
        # Return rich structured data including the dynamic temporary password
        return {
            "status": "success",
            "message": f"User cloned successfully to '{payload.target_domain}'",
            "dn": target_dn,
            "temporary_password": password_to_use,
            "auto_generated": generated_pass
        }

    finally:
        # The finally block ALWAYS runs, preventing any network socket leaks in Docker
        if 'conn_source' in locals() and conn_source:
            conn_source.unbind()
        if 'conn_target' in locals() and conn_target:
            conn_target.unbind()