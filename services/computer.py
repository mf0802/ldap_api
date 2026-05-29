from pydantic import BaseModel
from services.ldap_service import connect_to_domain
from errors import AppError

class CreateComputerPayload(BaseModel):
    domain_name: str  # e.g., "domaina.local", "://example.com", or "test.forest.net"
    computer_name: str
    ou_dn: str  # Target organizational unit DN for the new computer object

class ComputerCreationResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

def create_computer(payload: CreateComputerPayload) -> ComputerCreationResponse:
    """
    Create a new Active Directory computer account in the targeted domain environment.
    Returns a standardized API response model.
    """
    try:
        # 1. Dynamically establish a secure connection to the targeted forest
        conn, search_base = connect_to_domain(payload.domain_name)
        
        try:
            dn = f"CN={payload.computer_name},{payload.ou_dn}"
            
            # Active Directory requires computer names to end with a '$' character for sAMAccountName
            sam_name = f"{payload.computer_name}$"
            
            attrs = {
                'objectClass': ['top', 'person', 'organizationalPerson', 'user', 'computer'],
                'sAMAccountName': sam_name,
                'userAccountControl': '4096'  # WORKSTATION_TRUST_ACCOUNT flag for computer accounts
            }
            
            # Try to create the computer object in LDAP
            if not conn.add(dn, attributes=attrs):
                raise AppError(
                    status_code=400,
                    error="bad_request",
                    details=conn.result.get('description', 'Failed to create computer')
                )
            
            return ComputerCreationResponse(
                message=f"Computer account created successfully on domain '{payload.domain_name}'.",
                distinguished_name=dn
            )
        finally:
            # 2. Guarantee structural socket breakdown to eliminate connection leakage
            conn.unbind()

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during computer creation: {str(e)}"
        )
