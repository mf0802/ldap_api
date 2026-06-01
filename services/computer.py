from ldap3 import MODIFY_REPLACE, SUBTREE
from pydantic import BaseModel, field_validator
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

class EnableComputerPayload(BaseModel):
    domain_name: str
    computer_name: str  # e.g., "DESKTOP-01" or "SERVER01$"

    @field_validator('computer_name')
    @classmethod
    def ensure_dollar_sign(cls, v: str) -> str:
        # Automatically append '$' if missing from the incoming request
        v = v.upper()
        if not v.endswith('$'):
            return f"{v}$"
        return v

class ComputerEnableResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

class DisableComputerPayload(BaseModel):
    domain_name: str
    computer_name: str  # e.g., "DESKTOP-01" or "SERVER01$"

    @field_validator('computer_name')
    @classmethod
    def ensure_dollar_sign(cls, v: str) -> str:
        # Automatically append '$' if missing from the incoming request
        v = v.upper()
        if not v.endswith('$'):
            return f"{v}$"
        return v

class ComputerDisableResponse(BaseModel):
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

def enable_computer(payload: EnableComputerPayload) -> ComputerEnableResponse:
    """
    Search for a computer account via sAMAccountName and enable it.
    Returns a standardized API response model.
    """
    try:
        # Dynamically connect to the requested domain forest
        conn, search_base = connect_to_domain(payload.domain_name)

        # 1. Target the specific computer using objectClass=computer
        search_filter = f"(&(objectClass=computer)(sAMAccountName={payload.computer_name}))"
        
        status = conn.search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['userAccountControl']
        )

        # Define a clean name without the '$' suffix for end-user visibility
        display_name = payload.computer_name.rstrip('$')

        # If empty, this prevents an IndexError from being masked as a 500 server error.
        if not status or not conn.entries:
            raise AppError(
                status_code=404,
                error="not_found",
                details=f"Computer '{display_name}' not found on domain '{payload.domain_name}' using filter '{search_filter}'."
            )

        computer_entry = conn.entries[0]
        dn = computer_entry.entry_dn
        current_uac = int(computer_entry.userAccountControl.value)

        # 2. Perform bitwise AND with NOT 2 to remove the 'ACCOUNTDISABLE' flag (0x0002)
        enabled_uac = current_uac & ~2

        # 3. Modify the attribute in LDAP
        changes = {
            'userAccountControl': [(MODIFY_REPLACE, [str(enabled_uac)])]
        }
        
        # Execute the LDAP modification
        if not conn.modify(dn, changes):
            raise AppError(
                status_code=500,
                error="ldap_modify_failed",
                details=f"Failed to modify userAccountControl for computer '{display_name}': {conn.result.get('description')}"
            )

        # Return response mapping exactly to your ComputerEnableResponse model
        return ComputerEnableResponse(
            status="success",
            message=f"Computer '{display_name}' has been successfully enabled.",
            distinguished_name=dn
        )

    except AppError:
        raise
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during computer enabling: {str(e)}"
        )


def disable_computer(payload: DisableComputerPayload) -> ComputerDisableResponse:
    """
    Search for a computer account via sAMAccountName and disable it.
    Returns a standardized API response model.
    """
    try:
        # Dynamically connect to the requested domain forest
        conn, search_base = connect_to_domain(payload.domain_name)
        
        # 1. Target the specific computer using objectClass=computer
        search_filter = f"(&(objectClass=computer)(sAMAccountName={payload.computer_name}))"
        
        status = conn.search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['userAccountControl']
        )
        
        if not status or not conn.entries:
            raise AppError(
                status_code=404,
                error="not_found",
                details=f"Computer '{payload.computer_name}' not found on domain '{payload.domain_name}'."
            )
            
        # Extract data from the search result
        computer_entry = conn.entries[0]
        dn = computer_entry.entry_dn
        current_uac = int(computer_entry.userAccountControl.value)
        
        # 2. Perform bitwise OR to append the 'ACCOUNTDISABLE' flag (2)
        disabled_uac = current_uac | 2 
        
        # 3. Modify the attribute in LDAP
        changes = {
            'userAccountControl': [(MODIFY_REPLACE, [str(disabled_uac)])]
        }
        
        if not conn.modify(dn, changes):
            raise AppError(
                status_code=400,
                error="bad_request",
                details=conn.result.get('description', 'Failed to disable computer account')
            )
            
        # Explicitly unbind to free up network resources/sockets
        conn.unbind()
        
        return ComputerDisableResponse(
            message=f"Computer account '{payload.computer_name}' disabled successfully on domain '{payload.domain_name}'.",
            distinguished_name=dn
        )
        
    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during computer disabling: {str(e)}"
        )