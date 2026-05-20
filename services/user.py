from pydantic import BaseModel
from services.ldap_service import connect_ldap
from errors import AppError

class CreateUserPayload(BaseModel):
    sam_account_name: str
    first_name: str
    last_name: str
    ou_dn: str  # Target organizational unit DN for the new user

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