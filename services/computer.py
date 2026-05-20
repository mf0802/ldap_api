from pydantic import BaseModel
from services.ldap_service import connect_ldap
from errors import AppError

class CreateComputerPayload(BaseModel):
    computer_name: str
    ou_dn: str  # Target organizational unit DN for the new computer object

def create_computer(payload: CreateComputerPayload) -> str:
    """Create a new Active Directory computer account and return its distinguishedName."""
    conn = connect_ldap()
    dn = f"CN={payload.computer_name},{payload.ou_dn}"
    sam_name = f"{payload.computer_name}$"
    attrs = {
        'objectClass': ['top', 'person', 'organizationalPerson', 'user', 'computer'],
        'sAMAccountName': sam_name,
        'userAccountControl': '4096'  # WORKSTATION_TRUST_ACCOUNT flag for computer accounts
    }
    # Try to create the computer object in LDAP and raise a structured error on failure
    if not conn.add(dn, attributes=attrs):
        raise AppError(
            status_code=400,
            error="LDAP Operation Failed",
            details=conn.result.get('description', 'Failed to create computer')
        )
    
    return dn