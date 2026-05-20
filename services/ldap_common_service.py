import json
import os
from pydantic import BaseModel
from services.ldap_service import connect_ldap
from errors import AppError
from ldap3 import Connection, SUBTREE, MODIFY_REPLACE
from config import settings

class ModifyAttributePayload(BaseModel):
    target_dn: str
    attribute: str
    value: str

class QueryObjectPayload(BaseModel):
    sam_account_name: str
    object_class: str  # "user", "group" or "computer"

class DeleteObjectPayload(BaseModel):
    domain: str            # e.g. "://example.com"
    sam_account_name: str  # e.g. "m.mustermann" or "GG_Marketing"

ALLOWED_ATTRIBUTES = {
    "user": [
        "cn", "sAMAccountName", "givenName", "sn", "mail", 
        "department", "title", "whenCreated", "userAccountControl"
    ],
    "group": [
        "cn", "sAMAccountName", "objectClass", "info", "description", 
        "member", "whenCreated"
    ],
    "computer": [
        "cn", "sAMAccountName", "operatingSystem", "operatingSystemVersion", 
        "location", "whenCreated"
    ]
}
# =====================================================================
# COMMON HELPER FUNCTIONS (Now centrally located here)
# =====================================================================
def find_dn_multi_forest(conn: Connection, sam_name: str, object_class: str, domain: str) -> str:
    """Searches for an object in a specific forest based on the domain."""
    
    # 1. Get the configuration for the desired domain from the settings
    forest_config = settings.forests.get(domain.lower())
    
    if not forest_config:
        raise AppError(
            status_code=400, 
            error="Validation Error", 
            details=f"The domain '{domain}' is not configured in this API."
        )
    
    if object_class.lower() == "computer" and not sam_name.endswith("$"):
        sam_name = f"{sam_name}$"
        
    # 2. Extract the search base from the forest configuration
    search_base = forest_config["search_base"]
    search_filter = f"(&(objectClass={object_class})(sAMAccountName={sam_name}))"
    
    conn.search(
        search_base=str(search_base), 
        search_filter=search_filter, 
        search_scope=SUBTREE, 
        attributes=['distinguishedName']
    )
    
    if not conn.entries:
        raise AppError(
            status_code=404, 
            error="Not Found", 
            details=f"Object '{sam_name}' ({object_class}) not found in domain '{domain}'."
        )
        
    return conn.entries[0].entry_dn

def get_object_attributes(payload: QueryObjectPayload) -> dict:
    conn = connect_ldap()
    
    sam_name = extract_sam_name(payload.sam_account_name)
    search_filter = f"(&(objectClass={payload.object_class})(sAMAccountName={sam_name}))"
    
    # Determine the appropriate whitelist for the object type
    # If the type is unknown, request only standard attributes '*'
    requested_attrs = ALLOWED_ATTRIBUTES.get(payload.object_class.lower(), ['*'])
    
    conn.search(
        search_base=str(settings.search_base),
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=requested_attrs  # Request only the safe attributes from AD
    )
    
    if not conn.entries:
        raise AppError(
            status_code=404, 
            error="Not Found", 
            details=f"Object '{payload.sam_account_name}' of type '{payload.object_class}' not found."
        )
    
    # Convert to a clean Python dict
    raw_json_str = conn.entries[0].entry_to_json()
    entry_dict = json.loads(raw_json_str)
    
    return {
        "status": "success",
        "dn": entry_dict.get("dn"),
        "attributes": entry_dict.get("attributes", {})
    }


def extract_sam_name(raw_name: str) -> str:
    """Extracts the sAMAccountName, whether with or without a domain prefix."""
    if '\\' not in raw_name:
        return raw_name
        
    parts = raw_name.split('\\')
    if len(parts) != 2:
        raise AppError(
            status_code=400, 
            error="Validation Error", 
            details=f"Invalid format for '{raw_name}'. Expected 'domain\\name'."
        )
    return parts[1]

def find_dn(conn: Connection, raw_name: str, object_class: str) -> str:
    """Searches for an LDAP object by sAMAccountName and returns the DN."""
    sam_name = extract_sam_name(raw_name)
    search_filter = f"(&(objectClass={object_class})(sAMAccountName={sam_name}))"
    
    # Using str(...) ensures VS Code knows that None cannot be passed here
    conn.search(
        search_base=str(settings.search_base), 
        search_filter=search_filter, 
        search_scope=SUBTREE, 
        attributes=['distinguishedName']
    ) # type: ignore
    
    if not conn.entries:
        raise AppError(
            status_code=404, 
            error="Not Found", 
            details=f"Object '{raw_name}' (Type: {object_class}) not found."
        )
        
    return conn.entries[0].entry_dn

def delete_object_from_forest(payload: DeleteObjectPayload, object_class: str) -> str:
    """Deletes any LDAP object from a specific forest."""
    conn = connect_ldap()
    
    # 1. Find the DN in the correct forest
    target_dn = find_dn_multi_forest(conn, payload.sam_account_name, object_class, payload.domain)
    
    # 2. Delete the object
    if not conn.delete(target_dn):
        raise AppError(
            status_code=400, 
            error="LDAP Operation Failed", 
            details=conn.result.get('description', f"Could not delete {object_class} in domain {payload.domain}.")
        )
    
    return f"{object_class.capitalize()} '{payload.sam_account_name}' successfully deleted from domain '{payload.domain}'."
    
# =====================================================================
# UNIVERSAL ROUTE LOGIC
# =====================================================================

def modify_attribute(payload: ModifyAttributePayload) -> dict:
    conn = connect_ldap()
    changes = {payload.attribute: [(MODIFY_REPLACE, [payload.value])]}
    
    if not conn.modify(payload.target_dn, changes):
        raise AppError(
            status_code=400, 
            error="LDAP Operation Failed", 
            details=conn.result.get('description', 'Modification failed')
        )
        
    return {
        "status": "success",
        "message": "Attribute updated successfully",
        "dn": payload.target_dn,
        "updated": {payload.attribute: payload.value}
    }
