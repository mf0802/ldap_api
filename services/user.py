import secrets
import string
from typing import Optional
from datetime import datetime, timedelta, timezone

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

class EnableUserPayload(BaseModel):
    distinguished_name: str

class UserCreationResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

class DynamicCloneUserPayload(BaseModel):
    source_domain: str       # e.g., "domaina.local" or "test.forest.net"
    source_user_dn: str      # Full source Distinguished Name (DN)
    target_domain: str       # e.g., "://example.com"
    target_ou_dn: str        # Target OU where the user should be cloned into
    temporary_password: Optional[str] = None  # Optional, will be auto-generated if omitted

class UserActivationResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str
    generated_password: str

class UserLockoutStatusResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str
    is_locked: bool

class CheckLockoutPayload(BaseModel):
    distinguished_name: str

class UserUnlockResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

def create_user(payload: CreateUserPayload) -> UserCreationResponse:
    """
    Create a new Active Directory user entry in a disabled state.
    Returns a standardized API response model.
    """
    try:
        conn = connect_ldap()
        dn = f"CN={payload.first_name} {payload.last_name},{payload.ou_dn}"
        
        attrs = {
            'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
            'sAMAccountName': payload.sam_account_name,
            'givenName': payload.first_name,
            'sn': payload.last_name,
            'userAccountControl': '514'  # Disabled account status, password must be set later
        }
        
        # Try to create the user object in LDAP
        if not conn.add(dn, attributes=attrs):
            raise AppError(
                status_code=400, 
                error="bad_request", 
                details=conn.result.get('description', 'Failed to create user')
            )
        
        # Return structured data that automatically serializes to clean JSON
        return UserCreationResponse(
            message="User created successfully in disabled state.",
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
            details=f"An unexpected error occurred during user creation: {str(e)}"
        )

def enable_user_with_password(dn: str) -> UserActivationResponse:
    """
    Sets a new password and enables an existing AD user account.
    Returns a standardized API response model.
    """
    try:
        # Establish connection - Must be secure LDAPS (Port 636) to modify passwords
        conn = connect_ldap()  
        
        # Generate the password and format it for Active Directory (UTF-16-LE with quotes)
        password = generate_ad_compliant_password()
        encoded_password = f'"{password}"'.encode('utf-16-le')
        
        # Bundle operations: Set unicodePwd and change userAccountControl to 512 (Normal Account / Enabled)
        modifications = {
            'unicodePwd': [(MODIFY_REPLACE, [encoded_password])],
            'userAccountControl': [(MODIFY_REPLACE, ['512'])]
        }
        
        # Execute the changes in Active Directory (Returns False on AD policy violation)
        if not conn.modify(dn, changes=modifications):
            raise AppError(
                status_code=400,
                error="bad_request",
                details=conn.result.get('description', 'Failed to enable account or set password')
            )
            
        # Return structured data that automatically serializes to clean JSON
        return UserActivationResponse(
            message="The user account has been successfully enabled and the password has been set.",
            distinguished_name=dn,
            generated_password=password
        )

    except AppError as ae:
        # Re-raise expected application errors so FastAPI can handle them properly
        raise ae
    except Exception as e:
        # Catch unexpected connection, network, or library errors
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during LDAP operation: {str(e)}"
        )

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

def check_user_lockout(dn: str) -> UserLockoutStatusResponse:
    """
    Check if a user account is currently locked out in Active Directory or Samba.
    Handles both raw Win32 formats and pre-parsed ldap3 datetime/timedelta objects safely.
    """
    try:
        conn = connect_ldap()
        
        # 1. Fetch user's lockoutTime attribute
        if not conn.search(search_base=dn, search_filter="(objectClass=user)", attributes=['lockoutTime']):
            raise AppError(
                status_code=404,
                error="not_found",
                details=f"User object '{dn}' could not be found."
            )
            
        user_entry = conn.entries[0]
        lockout_time_val = user_entry.lockoutTime.value if 'lockoutTime' in user_entry else None

        # If lockoutTime is missing, None, or 0, the account is absolutely not locked
        if not lockout_time_val or lockout_time_val == 0:
            return UserLockoutStatusResponse(
                message="The user account is not locked out.",
                distinguished_name=dn,
                is_locked=False
            )

        # 2. Convert lockoutTime to a standard timezone-aware datetime object
        if isinstance(lockout_time_val, datetime):
            # ldap3 already parsed it into a datetime object
            # Ensure it is timezone-aware (AD/Samba operate in UTC)
            if lockout_time_val.tzinfo is None:
                lockout_datetime = lockout_time_val.replace(tzinfo=timezone.utc)
            else:
                lockout_datetime = lockout_time_val.astimezone(timezone.utc)
        else:
            # Fallback: Process raw Win32 Epoch integer (100-nanosecond intervals since Jan 1, 1601)
            lockout_timestamp = (int(lockout_time_val) - 116444736000000000) / 10000000
            lockout_datetime = datetime.fromtimestamp(lockout_timestamp, tz=timezone.utc)

        # 3. Fetch the Domain's Lockout Duration Policy
        dc_index = dn.upper().find("DC=")
        domain_root_dn = dn[dc_index:] if dc_index != -1 else dn

        if not conn.search(search_base=domain_root_dn, search_filter="(objectClass=domain)", attributes=['lockoutDuration']):
            raise AppError(
                status_code=500,
                error="internal_server_error",
                details="Failed to read the domain lockout policy duration."
            )

        lockout_duration_val = conn.entries[0].lockoutDuration.value

        # Robust Type-Handling for Lockout Duration
        if isinstance(lockout_duration_val, timedelta):
            lockout_duration_seconds = abs(lockout_duration_val.total_seconds())
        else:
            # Fallback for raw negative 64-bit intervals (100-nanosecond steps)
            lockout_duration_seconds = abs(int(lockout_duration_val)) / 10000000

        # 4. Calculate if the lockout has expired
        # Calculate time passed since the lockout occurred
        seconds_since_lock = (datetime.now(timezone.utc) - lockout_datetime).total_seconds()
        
        # The user is only locked if the elapsed time is LESS than the policy duration
        is_currently_locked = seconds_since_lock < lockout_duration_seconds
        
        message = "The user account is currently locked out." if is_currently_locked else "The user lockout has expired (account is automatically unlocked)."

        return UserLockoutStatusResponse(
            message=message,
            distinguished_name=dn,
            is_locked=is_currently_locked
        )

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An error occurred while checking lockout status: {str(e)}"
        )
    
def unlock_user(dn: str) -> UserUnlockResponse:
    """
    Manually unlocks a locked Active Directory or Samba user account
    by resetting the lockoutTime attribute to 0.
    """
    try:
        conn = connect_ldap()
        
        # Define modification to clear the lockout timestamp (0 = Unlocked)
        modifications = {
            'lockoutTime': [(MODIFY_REPLACE, ['0'])]
        }
        
        # Execute the unlock operation in Active Directory
        if not conn.modify(dn, changes=modifications):
            raise AppError(
                status_code=400,
                error="bad_request",
                details=conn.result.get('description', 'Failed to unlock the user account.')
            )
            
        return UserUnlockResponse(
            message="The user account has been successfully unlocked.",
            distinguished_name=dn
        )

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during user unlock: {str(e)}"
        )
