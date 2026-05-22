import json
import os
import string
from typing import Any, Dict, List
from pydantic import BaseModel
from services.ldap_service import connect_ldap
from errors import AppError
from ldap3 import SIMPLE, Connection, SUBTREE, MODIFY_REPLACE, NONE, Server
from config import settings

class ModifyMultipleAttributesPayload(BaseModel):
    target_dn: str
    attributes: Dict[str, str]  # Key: Attributname, Value: Neuer Wert

class QueryObjectPayload(BaseModel):
    sam_account_name: str
    object_class: str  # "user", "group" or "computer"

class DeleteObjectPayload(BaseModel):
    domain: str            # e.g. "://example.com"
    sam_account_name: str  # e.g. "m.mustermann" or "GG_Marketing"

class ObjectDeletionResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

class BatchModifyAttributesPayload(BaseModel):
    sam_account_names: List[str]
    object_class: str  # e.g., "user", "group", "computer"
    # Example for attributes: {"description": "Updated via API", "title": "Engineer"}
    attributes: Dict[str, Any]

class GenericBatchResponse(BaseModel):
    status: str = "success"
    message: str
    successful: List[str]
    failed: List[str]

class MultiForestSearchPayload(BaseModel):
    sam_account_name: str

class DiscoveredObject(BaseModel):
    found_in_domain: str
    distinguished_name: str
    attributes: Dict[str, Any]

class MultiForestSearchResponse(BaseModel):
    status: str = "success"
    message: str
    total_matches: int
    matches: List[DiscoveredObject]

ALLOWED_ATTRIBUTES = {
    "user": [
        "cn", "sAMAccountName", "givenName", "sn", "mail", "description", "lockoutTime",
        "department", "title", "whenCreated", "userAccountControl", "telephoneNumber","memberOf"
    ],
    "group": [
        "cn", "sAMAccountName", "objectClass", "info", "description", 
        "member", "whenCreated", "memberOf"
    ],
    "computer": [
        "cn", "sAMAccountName", "operatingSystem", "operatingSystemVersion", "description",
        "location", "whenCreated", "memberOf"
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

def delete_object_from_forest(payload: DeleteObjectPayload, object_class: str) -> ObjectDeletionResponse:
    """
    Deletes any LDAP object from a specific forest based on the provided domain.
    Returns a standardized API response model.
    """
    try:
        conn = connect_ldap()
        
        # 1. Find the DN in the correct forest
        target_dn = find_dn_multi_forest(conn, payload.sam_account_name, object_class, payload.domain)
        
        # 2. Delete the object
        if not conn.delete(target_dn):
            raise AppError(
                status_code=400, 
                error="bad_request", 
                details=conn.result.get('description', f"Could not delete {object_class} in domain {payload.domain}.")
            )
        
        # Return structured data that automatically serializes to clean JSON
        return ObjectDeletionResponse(
            message=f"{object_class.capitalize()} '{payload.sam_account_name}' successfully deleted from domain '{payload.domain}'.",
            distinguished_name=target_dn
        )

    except AppError as ae:
        # Re-raise expected application errors
        raise ae
    except Exception as e:
        # Catch unexpected connection, forest lookup, or network errors
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during {object_class} deletion: {str(e)}"
        )

def modify_attributes(payload: ModifyMultipleAttributesPayload) -> dict:
    conn = connect_ldap()
    
    # Dynamic construction of the changes dictionary for multiple attributes
    changes = {
        attr_name: [(MODIFY_REPLACE, [attr_value])] 
        for attr_name, attr_value in payload.attributes.items()
    }
    
    if not conn.modify(payload.target_dn, changes):
        raise AppError(
            status_code=400, 
            error="LDAP Operation Failed", 
            details=conn.result.get('description', 'Modification failed')
        )
        
    return {
        "status": "success",
        "message": "Attributes updated successfully",
        "dn": payload.target_dn,
        "updated": payload.attributes
    }

def handle_generic_batch_modify(payload: BatchModifyAttributesPayload) -> GenericBatchResponse:
    """
    Batch update specified attributes for any type of LDAP object.
    Returns a standardized API response model with detailed success/failure states.
    """
    try:
        conn = connect_ldap()
        successful = []
        failed = []
        
        if not payload.attributes:
            raise AppError(
                status_code=400,
                error="bad_request",
                details="No attributes provided for modification."
            )
            
        # Build the dynamic changes dictionary for the ldap3 modify operation
        # We use MODIFY_REPLACE as the standard action for attribute updates
        changes = {}
        for attr_name, attr_value in payload.attributes.items():
            # Ensure the value is wrapped in a list as required by ldap3 changes format
            value_list = attr_value if isinstance(attr_value, list) else [attr_value]
            changes[attr_name] = [(MODIFY_REPLACE, value_list)]
            
        # Iterate over all provided objects
        for sam_name in payload.sam_account_names:
            try:
                # Resolve the DN dynamically based on sAMAccountName and objectClass
                object_dn = find_dn(conn, sam_name, payload.object_class)
                
                # Execute the modification for the current object
                if conn.modify(object_dn, changes):
                    successful.append(f"Successfully updated {payload.object_class} '{sam_name}'")
                else:
                    error_desc = conn.result.get('description', 'Modification failed')
                    failed.append(f"LDAP Error on '{sam_name}': {error_desc}")
                    
            except AppError as e:
                failed.append(f"Lookup failed for '{sam_name}' ({payload.object_class}): {e.details}")
                
        # Determine the final summary message
        if not successful and failed:
            message = f"All batch modifications for {payload.object_class} objects failed."
        elif successful and failed:
            message = f"Batch modifications for {payload.object_class} objects completed with some errors."
        else:
            message = f"All batch modifications for {payload.object_class} objects completed successfully."
            
        return GenericBatchResponse(
            message=message,
            successful=successful,
            failed=failed
        )

    except AppError as ae:
        # Re-raise expected validation errors
        raise ae
    except Exception as e:
        # Catch unexpected connection, forest lookup, or network errors
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during generic batch modification: {str(e)}"
        )

def search_object_across_forests(payload: MultiForestSearchPayload) -> MultiForestSearchResponse:
    """
    Searches for all LDAP objects matching the sAMAccountName across all 
    dynamically configured domains in the .env file.
    Returns a list of all matches found across all forests.
    """
    domains = []
    matches = []
    
    # 1. Dynamically discover all configured domains from .env
    for letter in string.ascii_uppercase:
        prefix = f"DOMAIN_{letter}_"
        domain_name = os.getenv(f"{prefix}NAME")
        
        if not domain_name:
            break
            
        domains.append({
            "name": domain_name,
            "server": os.getenv(f"{prefix}SERVER"),
            "user": os.getenv(f"{prefix}USER"),
            "password": os.getenv(f"{prefix}PASSWORD"),
            "search_base": os.getenv(f"{prefix}SEARCH_BASE")
        })

    if not domains:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details="No AD domains were detected or configured in the environment."
        )

    search_filter = f"(sAMAccountName={payload.sam_account_name})"
    requested_attributes = ['objectClass', 'sAMAccountName', 'displayName', 'description', 'mail', 'userAccountControl']

    # 2. Iterate through all domains and collect ALL matches
    for domain in domains:
        if not domain["server"] or not domain["search_base"]:
            continue
            
        try:
            # Fixed Pylance warning by using NONE constant instead of None
            server = Server(domain["server"], get_info=NONE)
            conn = Connection(
                server, 
                user=domain["user"], 
                password=domain["password"], 
                authentication=SIMPLE,
                auto_bind=True
            )
            
            conn.search(
                search_base=domain["search_base"],
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=requested_attributes
            )
            
            # If matches are found in this domain, append them to our list
            if conn.entries:
                for entry in conn.entries:
                    attributes_dict = {}
                    for attr_name in entry.entry_attributes:
                        val = entry[attr_name].value
                        if isinstance(val, list) and len(val) == 1:
                            attributes_dict[attr_name] = val
                        else:
                            attributes_dict[attr_name] = val

                    matches.append(
                        DiscoveredObject(
                            found_in_domain=domain["name"],
                            distinguished_name=entry.entry_dn,
                            attributes=attributes_dict
                        )
                    )
                
            conn.unbind()
            
        except Exception as e:
            print(f"Failed to query forest {domain['name']}: {str(e)}")
            continue

    # 3. Check if we found at least one match across all forests
    if not matches:
        raise AppError(
            status_code=404,
            error="not_found",
            details=f"Object with sAMAccountName '{payload.sam_account_name}' could not be found in any configured forest."
        )
        
    return MultiForestSearchResponse(
        message=f"Search completed. Found {len(matches)} matching object(s) across forests.",
        total_matches=len(matches),
        matches=matches
    )