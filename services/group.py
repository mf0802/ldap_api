import re

from ldap3 import SUBTREE, MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE
from pydantic import BaseModel
from typing import List, Optional
from services.ldap_service import connect_ldap
from config import settings
from errors import AppError
from services.ldap_common_service import find_dn

# Service for LDAP group operations:
# - create a new group
# - update group owner metadata in the info attribute
# - batch add/remove user membership from groups

class CreateGroupPayload(BaseModel):
    group_name: str
    ou_dn: str
    info: Optional[str] = None  # Optional initial info text for the group object

class GroupCreationResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

class UpdateGroupOwnershipPayload(BaseModel):
    group_name: str
    add_owners: Optional[str] = None     # Comma-separated emails to add as owners
    delete_owners: Optional[str] = None  # Comma-separated emails to remove from owners

class BatchGroupPayload(BaseModel):
    action: str  # "add" or "remove"
    group_names: List[str]
    user_names: List[str]

# =====================================================================
# REGEX HELPERS FOR OWNER METADATA IN THE INFO ATTRIBUTE
# =====================================================================

def extract_owner_line(multiline_string: str):
    """Extract the Owners line from arbitrary text and return it plus the remaining text."""
    pattern = r'(Owner[s]?:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:;[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})*)(;?)'
    match = re.search(pattern, multiline_string, re.MULTILINE)

    if match:
        owner_line = re.sub(r'^Owner:', 'Owners:', match.group(1))
        owner_line += ";" if not match.group(2) else ""
        remaining_text = multiline_string.replace(match.group(0), "", 1).strip()
        return owner_line, remaining_text

    return None, multiline_string

def modify_owners(current_owners_string: str, add_owners: Optional[str], delete_owners: Optional[str]) -> str:
    """Add or remove owner emails while preserving case-insensitive uniqueness."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    owners = set(re.findall(pattern, current_owners_string.lower()))

    if add_owners:
        owners.update(email.strip() for email in add_owners.lower().split(",") if email.strip())

    if delete_owners:
        owners.difference_update(email.strip() for email in delete_owners.lower().split(",") if email.strip())

    if not owners:
        return ""
        
    return "Owners:" + ";".join(sorted(owners)) + ";"

def create_group(payload: CreateGroupPayload) -> GroupCreationResponse:
    """
    Create a new AD group object in the provided OU.
    Returns a standardized API response model.
    """
    try:
        conn = connect_ldap()
        dn = f"CN={payload.group_name},{payload.ou_dn}"
        
        attrs = {
            'objectClass': ['top', 'group'],
            'sAMAccountName': payload.group_name
        }
        
        # Set optional info text if provided at creation time
        if payload.info:
            attrs['info'] = payload.info

        # Try to create the group object in LDAP
        if not conn.add(dn, attributes=attrs):
            raise AppError(
                status_code=400, 
                error="bad_request", 
                details=conn.result.get('description', 'Unknown error')
            )
        
        # Return structured data that automatically serializes to clean JSON
        return GroupCreationResponse(
            message="Group created successfully.",
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
            details=f"An unexpected error occurred during group creation: {str(e)}"
        )

def update_group_ownership(payload: UpdateGroupOwnershipPayload) -> dict:
    """Update the Owners list inside the group's info attribute."""
    conn = connect_ldap()
    group_dn = find_dn(conn, payload.group_name, "group")
    
    # 1. Read the current info attribute from the group
    conn.search(search_base=group_dn, search_filter="(objectClass=group)", search_scope=SUBTREE, attributes=['info']) # type: ignore
    if not conn.entries:
        raise AppError(status_code=404, error="Not Found", details=f"Group '{payload.group_name}' not found during read.")
    
    raw_info = conn.entries[0].info.value if conn.entries[0].info else ""
    current_info_text = str(raw_info) if raw_info else ""

    # 2. Extract existing owner line and any remaining text
    owner_line, remaining_text = extract_owner_line(current_info_text)
    if not owner_line:
        owner_line = "Owners:"

    new_owner_line = modify_owners(owner_line, payload.add_owners, payload.delete_owners)

    # 3. Reassemble info text while preserving additional notes
    if remaining_text:
        final_info_string = f"{new_owner_line}\n{remaining_text}" if new_owner_line else remaining_text
    else:
        final_info_string = new_owner_line

    # 4. Write the updated info back to Active Directory
    changes = {
        'info': [(MODIFY_REPLACE, [final_info_string.strip()])]
    }
    
    if not conn.modify(group_dn, changes):
        raise AppError(status_code=400, error="LDAP Operation Failed", details=conn.result.get('description', 'Could not update group ownership.'))
        
    return {"status": "success", "updated_info": final_info_string}

def handle_batch(payload: BatchGroupPayload) -> dict:
    """Batch add or remove user members to/from groups."""
    conn = connect_ldap()
    successful = []
    failed = []
    
    for group_raw in payload.group_names:
        try:
            group_dn = find_dn(conn, group_raw, "group")
        except AppError as e:
            failed.append(f"{group_raw}: {e.details}")
            continue
            
        for user_raw in payload.user_names:
            try:
                user_dn = find_dn(conn, user_raw, "user")
                
                if payload.action == "add":
                    changes = {'member': [(MODIFY_ADD, [user_dn])]}
                elif payload.action == "remove":
                    changes = {'member': [(MODIFY_DELETE, [user_dn])]}
                else:
                    return {"successful": successful, "failed": failed + ["Invalid action provided"]}
                
                if conn.modify(group_dn, changes):
                    successful.append(f"{user_raw} -> {group_raw}")
                else:
                    failed.append(f"Error {user_raw} -> {group_raw}: {conn.result.get('description', 'Modification failed')}")
            except AppError as e:
                failed.append(f"{user_raw}: {e.details}")
                
    return {"successful": successful, "failed": failed}
