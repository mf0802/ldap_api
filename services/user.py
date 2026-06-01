import secrets
import string
from typing import Optional
from datetime import datetime, timedelta, timezone

from ldap3 import MODIFY_REPLACE, SUBTREE
from ldap3.core.exceptions import LDAPInvalidDnError
from pydantic import BaseModel
from services.ldap_service import connect_to_domain
from errors import AppError

class CreateUserPayload(BaseModel):
    domain_name: str  # e.g., "domaina.local", "samdom.example.com", or "test.forest.net"
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

class ResetPasswordRandomPayload(BaseModel):
    distinguished_name: str

class PasswordResetRandomResponse(BaseModel):
    message: str
    temporary_password: str

class DisableUserPayload(BaseModel):
    domain_name: str  # z.B. "domaina.local", "samdom.example.com"
    sam_account_name: str  # Der eindeutige Login-Name des Benutzers

class UserDisableResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str


def create_user(payload: CreateUserPayload) -> UserCreationResponse:
    """
    Create a new Active Directory user entry in a disabled state on the target domain.
    Returns a standardized API response model.
    """
    try:
        # Dynamically connect to the requested domain forest
        conn, search_base = connect_to_domain(payload.domain_name)
        
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
        
        # Explicitly unbind to free up network resources/sockets
        conn.unbind()
        
        return UserCreationResponse(
            message=f"User created successfully in disabled state on domain '{payload.domain_name}'.",
            distinguished_name=dn
        )

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during user creation: {str(e)}"
        )


def enable_user_with_password(dn: str) -> UserActivationResponse:
    """
    Sets a new password and enables an existing AD user account on its matching domain.
    Returns a standardized API response model.
    """
    try:
        # 1. Automatically extract the domain name from the DN
        # Example: "CN=User,DC=samdom,DC=example,DC=com" -> ["samdom", "example", "com"]
        dn_lower = dn.lower()
        dc_components = [part.split('=')[1] for part in dn_lower.split(',') if part.strip().startswith('dc=')]
        detected_domain = ".".join(dc_components)
        
        # 2. Dynamically connect to the matching domain forest
        conn, _ = connect_to_domain(detected_domain)
        
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
            
        # Explicitly unbind to free up network resources
        conn.unbind()
            
        return UserActivationResponse(
            message=f"The user account has been successfully enabled on '{detected_domain}'.",
            distinguished_name=dn,
            generated_password=password
        )

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during LDAP operation: {str(e)}"
        )

def disable_user(payload: DisableUserPayload) -> UserDisableResponse:
    """
    Sucht einen Active Directory Benutzer via sAMAccountName und deaktiviert ihn.
    Gibt ein standardisiertes API-Response-Modell zurück.
    """
    try:
        # Dynamische Verbindung zur angeforderten Domain herstellen
        conn, search_base = connect_to_domain(payload.domain_name)
        
        # 1. Benutzer über sAMAccountName suchen, um korrekten DN und UAC zu finden
        search_filter = f"(&(objectClass=user)(sAMAccountName={payload.sam_account_name}))"
        
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
                details=f"User with sAMAccountName '{payload.sam_account_name}' not found on domain '{payload.domain_name}'."
            )
            
        # DN und aktuellen UAC-Wert aus dem Suchergebnis extrahieren
        user_entry = conn.entries[0]
        dn = user_entry.entry_dn
        current_uac = int(user_entry.userAccountControl.value)
        
        # 2. Bitweises OR, um das Flag 'ACCOUNTDISABLE' (2) zu setzen
        disabled_uac = current_uac | 2 
        
        # 3. Das Attribut im LDAP ändern
        changes = {
            'userAccountControl': [(MODIFY_REPLACE, [str(disabled_uac)])]
        }
        
        if not conn.modify(dn, changes):
            raise AppError(
                status_code=400,
                error="bad_request",
                details=conn.result.get('description', 'Failed to disable user')
            )
            
        # Verbindung explizit trennen
        conn.unbind()
        
        return UserDisableResponse(
            message=f"User '{payload.sam_account_name}' disabled successfully on domain '{payload.domain_name}'.",
            distinguished_name=dn
        )
        
    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during user disabling: {str(e)}"
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
    generated_pass = False
    password_to_use = payload.temporary_password
    
    if not password_to_use:
        password_to_use = generate_ad_compliant_password()
        generated_pass = True

    # Fixed: Unpack the tuple because connect_to_domain returns (Connection, search_base)
    conn_source, source_base = connect_to_domain(payload.source_domain)
    conn_target, target_base = connect_to_domain(payload.target_domain)
    
    try:
        try:
            # Use the exact payload DN as the base since we are targeting a specific user object
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
                details=f"The syntax for 'source_user_dn' ({payload.source_user_dn}) is malformed."
            )
            
        source_entry = conn_source.entries[0]
        
        # Build standard name attributes cleanly, safely handling potential missing first/last names
        given_name = getattr(source_entry, 'givenName').value or ""
        sn_name = getattr(source_entry, 'sn').value or ""
        cn_value = f"{given_name} {sn_name}".strip() or source_entry.sAMAccountName.value
        
        target_dn = f"cn={cn_value},{payload.target_ou_dn}"
        
        # 512 = NORMAL_ACCOUNT (Enabled)
        target_attrs = {
            'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
            'cn': cn_value,
            'sAMAccountName': source_entry.sAMAccountName.value,
            'userAccountControl': '512' 
        }
        
        # Conditional additions to keep standard fields from breaking on empty strings
        if given_name: target_attrs['givenName'] = given_name
        if sn_name: target_attrs['sn'] = sn_name
        if getattr(source_entry, 'displayName').value:
            target_attrs['displayName'] = source_entry.displayName.value
        
        # Dynamically copy remaining optional attributes if they exist in the source account
        optional_attrs = ['mail', 'title', 'department', 'telephoneNumber']
        for attr in optional_attrs:
            if hasattr(source_entry, attr) and getattr(source_entry, attr).value:
                target_attrs[attr] = getattr(source_entry, attr).value

        # Create initial account structure in the target domain
        if not conn_target.add(target_dn, attributes=target_attrs):
            raise AppError(
                status_code=400, 
                error="Clone Operation Failed", 
                details=conn_target.result.get('description', 'Failed to create user structure.')
            )
            
        # Set temporary password via secure LDAPS connection
        try:
            encoded_password = f'"{password_to_use}"'.encode('utf-16-le')
            password_changes = {'unicodePwd': [(MODIFY_REPLACE, [encoded_password])]}
            
            conn_target.modify(target_dn, password_changes)
            
            # Rollback entry if password policy blocks it
            if conn_target.result.get('result', 0) != 0:
                conn_target.delete(target_dn)
                raise AppError(
                    status_code=400, 
                    error="Password Setup Failed", 
                    details=conn_target.result.get('description', 'Password policy violation.')
                )
                
        except Exception as e:
            conn_target.delete(target_dn)
            if isinstance(e, AppError):
                raise e
            raise AppError(
                status_code=400, 
                error="Password Operation Exception", 
                details=str(e)
            )
            
        # Enforce "User must change password at next logon"
        pwd_expiry_changes = {'pwdLastSet': [(MODIFY_REPLACE, [0])]}
        if not conn_target.modify(target_dn, pwd_expiry_changes):
            raise AppError(
                status_code=400, 
                error="Force Password Change Failed", 
                details=conn_target.result.get('description', 'Could not set pwdLastSet to 0')
            )
            
        return {
            "status": "success",
            "message": f"User cloned successfully to '{payload.target_domain}'",
            "dn": target_dn,
            "temporary_password": password_to_use,
            "auto_generated": generated_pass
        }

    finally:
        # Guaranteed clean breakdown of network sockets across forests
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
        # 1. Automatically extract the domain name from the DN
        dn_lower = dn.lower()
        dc_components = [part.split('=')[1] for part in dn_lower.split(',') if part.strip().startswith('dc=')]
        detected_domain = ".".join(dc_components)
        
        # 2. Dynamically connect to the matching domain forest
        conn, _ = connect_to_domain(detected_domain)
        
        try:
            # 3. Fetch user's lockoutTime attribute
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

            # 4. Convert lockoutTime to a standard timezone-aware datetime object
            if isinstance(lockout_time_val, datetime):
                if lockout_time_val.tzinfo is None:
                    lockout_datetime = lockout_time_val.replace(tzinfo=timezone.utc)
                else:
                    lockout_datetime = lockout_time_val.astimezone(timezone.utc)
            else:
                # Fallback: Process raw Win32 Epoch integer (100-nanosecond intervals since Jan 1, 1601)
                lockout_timestamp = (int(lockout_time_val) - 116444736000000000) / 10000000
                lockout_datetime = datetime.fromtimestamp(lockout_timestamp, tz=timezone.utc)

            # 5. Fetch the Domain's Lockout Duration Policy
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

            # 6. Calculate if the lockout has expired
            seconds_since_lock = (datetime.now(timezone.utc) - lockout_datetime).total_seconds()
            is_currently_locked = seconds_since_lock < lockout_duration_seconds
            
            message = "The user account is currently locked out." if is_currently_locked else "The user lockout has expired (account is automatically unlocked)."

            return UserLockoutStatusResponse(
                message=message,
                distinguished_name=dn,
                is_locked=is_currently_locked
            )
            
        finally:
            # Guarantees the network socket unbinds even if data extraction errors out
            conn.unbind()

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
        # 1. Automatically extract the domain name from the DN
        dn_lower = dn.lower()
        dc_components = [part.split('=')[1] for part in dn_lower.split(',') if part.strip().startswith('dc=')]
        detected_domain = ".".join(dc_components)
        
        # 2. Dynamically connect to the matching domain forest
        conn, _ = connect_to_domain(detected_domain)
        
        try:
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
                message=f"The user account has been successfully unlocked on '{detected_domain}'.",
                distinguished_name=dn
            )
        finally:
            conn.unbind()

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during user unlock: {str(e)}"
        )

def reset_user_password_random(payload: ResetPasswordRandomPayload) -> PasswordResetRandomResponse:
    """
    Resets an Active Directory user's password to a newly generated, 
    AD-compliant temporary password. Requires an LDAPS connection.
    """
    try:
        # 1. Automatically extract the domain name from the payload DN
        dn_lower = payload.distinguished_name.lower()
        dc_components = [part.split('=')[1] for part in dn_lower.split(',') if part.strip().startswith('dc=')]
        detected_domain = ".".join(dc_components)
        
        # 2. Dynamically connect to the matching domain forest
        conn, _ = connect_to_domain(detected_domain)
        
        try:
            # 3. Generate the AD-compliant temporary password
            temp_password = generate_ad_compliant_password()
            quoted_password = f'"{temp_password}"'
            encoded_password = quoted_password.encode('utf-16-le')
            
            # 4. Prepare the modification (Fixed: Using the proper constant instead of a string)
            changes = {
                'unicodePwd': [(MODIFY_REPLACE, [encoded_password])]
            }
            
            # 5. Apply the modification in AD
            if not conn.modify(payload.distinguished_name, changes):
                raise AppError(
                    status_code=400,
                    error="bad_request",
                    details=conn.result.get('description', 'Failed to reset user password')
                )
                
            return PasswordResetRandomResponse(
                message=f"User password has been reset successfully on '{detected_domain}'.",
                temporary_password=temp_password
            )
        finally:
            conn.unbind()
        
    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during password reset: {str(e)}"
        )