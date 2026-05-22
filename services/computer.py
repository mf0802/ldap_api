from pydantic import BaseModel
from services.ldap_service import connect_ldap
from errors import AppError

class CreateComputerPayload(BaseModel):
    computer_name: str
    ou_dn: str  # Target organizational unit DN for the new computer object

class ComputerCreationResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

def create_computer(payload: CreateComputerPayload) -> ComputerCreationResponse:
    """
    Create a new Active Directory computer account.
    Returns a standardized API response model.
    """
    try:
        conn = connect_ldap()
        dn = f"CN={payload.computer_name},{payload.ou_dn}"
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
        
        # Return structured data that automatically serializes to clean JSON
        return ComputerCreationResponse(
            message="Computer account created successfully.",
            distinguished_name=dn
        )

    except AppError as ae:
        # Re-raise expected application errors
        raise ae
    except Exception as e:
        # Catch unexpected connection or network errors
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during computer creation: {str(e)}"
        )
