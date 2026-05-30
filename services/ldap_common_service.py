import json
#import logging
from typing import Any, Dict, List
from pydantic import BaseModel
from services.ldap_service import connect_to_domain
from errors import AppError
from ldap3 import Connection, SUBTREE, MODIFY_REPLACE
from config import settings

class ModifyMultipleAttributesPayload(BaseModel):
    target_dn: str
    attributes: Dict[str, str]  # Key: Attribute name, Value: New value

class QueryObjectPayload(BaseModel):
    domain_name: str  # Added to target the correct forest
    sam_account_name: str
    object_class: str  # "user", "group" or "computer"

class DeleteObjectPayload(BaseModel):
    domain: str            # Maps to domain name, e.g., "samdom.example.com"
    sam_account_name: str  # e.g., "m.mustermann" or "GG_Marketing"

class ObjectDeletionResponse(BaseModel):
    status: str = "success"
    message: str
    distinguished_name: str

class BatchModifyAttributesPayload(BaseModel):
    domain_name: str  # Added to isolate the target forest
    sam_account_names: List[str]
    object_class: str  # e.g., "user", "group", "computer"
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

class MoveObjectPayload(BaseModel):
    target_dn: str  # Current full Distinguished Name (e.g., CN=PC01,OU=OldOU,DC=...)
    new_ou_dn: str  # Target Organizational Unit Distinguished Name (e.g., OU=NewOU,DC=...)

class MoveObjectResponse(BaseModel):
    status: str = "success"
    message: str
    old_dn: str
    new_dn: str

ALLOWED_ATTRIBUTES = {
    "user": [
        "cn", "sAMAccountName", "givenName", "sn", "mail", "description", "lockoutTime",
        "department", "title", "whenCreated", "userAccountControl", "telephoneNumber","memberOf", "comment"
    ],
    "group": [
        "cn", "sAMAccountName", "objectClass", "info", "description", 
        "member", "whenCreated", "memberOf", "comment"
    ],
    "computer": [
        "cn", "sAMAccountName", "operatingSystem", "operatingSystemVersion", "description",
        "location", "whenCreated", "memberOf", "comment"
    ]
}

# Initialize logger for debugging
#logger = logging.getLogger(__name__)

# =====================================================================
# COMMON HELPER FUNCTIONS 
# =====================================================================

def find_dn_multi_forest(conn: Connection, sam_name: str, object_class: str, domain: str) -> str:
    """Searches for an object in a specific forest based on the domain name."""
    forest_config = settings.forests.get(domain.lower())
    
    if not forest_config:
        raise AppError(
            status_code=400, 
            error="Validation Error", 
            details=f"The domain '{domain}' is not configured in this API."
        )
    
    if object_class.lower() == "computer" and not sam_name.endswith("$"):
        sam_name = f"{sam_name}$"
        
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

# =====================================================================
# CORE SERVICE LOGIC FUNCTIONS
# =====================================================================

def get_object_attributes(payload: QueryObjectPayload) -> dict:
    """Queries an object from a dynamically specified domain forest."""
    # 1. Dynamically connect to the matching domain forest
    conn, search_base = connect_to_domain(payload.domain_name)
    
    try:
        sam_name = payload.sam_account_name
        if payload.object_class.lower() == "computer" and not sam_name.endswith("$"):
            sam_name = f"{sam_name}$"
            
        search_filter = f"(&(objectClass={payload.object_class})(sAMAccountName={sam_name}))"
        requested_attrs = ALLOWED_ATTRIBUTES.get(payload.object_class.lower(), ['*'])
        
        conn.search(
            search_base=str(search_base),
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=requested_attrs
        )
        
        if not conn.entries:
            raise AppError(
                status_code=404, 
                error="Not Found", 
                details=f"Object '{payload.sam_account_name}' of type '{payload.object_class}' not found on '{payload.domain_name}'."
            )
        
        raw_json_str = conn.entries[0].entry_to_json()
        entry_dict = json.loads(raw_json_str)
        
        return {
            "status": "success",
            "dn": entry_dict.get("dn"),
            "attributes": entry_dict.get("attributes", {})
        }
    finally:
        conn.unbind()


def search_all_forests(payload: MultiForestSearchPayload) -> MultiForestSearchResponse:
    """
    Iterates through EVERY configured domain in your config file 
    to locate a sAMAccountName profile across your infrastructure.
    """
    matches = []
    sam_name = payload.sam_account_name
    
    # Check both normal and workstation variants safely
    san_clean = sam_name.rstrip('$')
    search_filter = f"(|(sAMAccountName={san_clean})(sAMAccountName={san_clean}$))"

    # Loop dynamically through all forests configured via the .env file
    for domain_key, domain_cfg in settings.forests.items():
        conn = None
        try:
            conn, search_base = connect_to_domain(domain_key)
            
            # Request common basic attributes for categorization
            conn.search(
                search_base=str(search_base),
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'sAMAccountName', 'objectClass', 'mail', 'description']
            )
            
            for entry in conn.entries:
                raw_json = json.loads(entry.entry_to_json())
                matches.append(
                    DiscoveredObject(
                        found_in_domain=domain_key,
                        distinguished_name=raw_json.get("dn", ""),
                        attributes=raw_json.get("attributes", {})
                    )
                )
        except Exception:
            # Skip silent network errors on dead DCs during global enumeration loops
            continue
        finally:
            if conn:
                conn.unbind()

    return MultiForestSearchResponse(
        message=f"Global multi-forest lookup complete for token: {sam_name}",
        total_matches=len(matches),
        matches=matches
    )



def delete_object(payload: DeleteObjectPayload) -> ObjectDeletionResponse:
    """
    Deletes an object out of Active Directory from its specific domain, 
    enforcing legal holds on users using dynamically configured attributes.
    """
    # Fetch the pre-parsed list of attributes from global settings
    legal_hold_attrs = settings.legal_hold_attributes

    conn, _ = connect_to_domain(payload.domain)
    try:
        # Determine if it's a computer/user/group automatically by checking variants
        target_dn = None
        for o_class in ["user", "group", "computer"]:
            try:
                target_dn = find_dn_multi_forest(conn, payload.sam_account_name, o_class, payload.domain)
                break
            except AppError:
                continue
                
        if not target_dn:
            raise AppError(
                status_code=404,
                error="not_found",
                details=f"Could not find object '{payload.sam_account_name}' on domain '{payload.domain}' to delete."
            )
        
        # --- Absolute Validation Guard ---
        # Query target metadata and all dynamic legal hold fields in a single trip for user objects
        search_success = conn.search(
            search_base=target_dn,
            search_filter="(objectClass=*)",
            search_scope='BASE',
            attributes=['objectClass'] + legal_hold_attrs
        )
        
        if search_success and conn.entries:
            target_entry = conn.entries[0]
            object_classes = [str(oc).lower() for oc in target_entry.objectClass.values]
            
            # Enforce legal hold protection explicitly if the object is a user account
            if "user" in object_classes:
                user_attributes = target_entry.entry_attributes_as_dict
                normalized_attributes = {k.lower(): v for k, v in user_attributes.items()}
                
                # Iterate dynamically through all configured attributes from your .env
                for attr_name in legal_hold_attrs:
                    if attr_name in normalized_attributes:
                        hold_values = normalized_attributes[attr_name]
                        
                        if hold_values and len(hold_values) > 0:
                            non_empty_values = [str(val).strip() for val in hold_values if str(val).strip()]
                            
                            if non_empty_values:
                                #logger.error(f"Legal hold active in field '{attr_name}' for user '{payload.sam_account_name}'. Aborting deletion.")
                                raise AppError(
                                    status_code=403,
                                    error="legal_hold_active",
                                    details=f"Deletion aborted. User '{payload.sam_account_name}' is on legal hold. Attribute '{attr_name}' contains: {non_empty_values}"
                                )
        # ---------------------------------
            
        # Execute deletion if no validation guard conditions were matched
        if not conn.delete(target_dn):
            raise AppError(
                status_code=400,
                error="bad_request",
                details=conn.result.get('description', 'Failed to execute deletion operation.')
            )
            
        return ObjectDeletionResponse(
            message=f"Object successfully purged from domain '{payload.domain}'.",
            distinguished_name=target_dn
        )
        
    finally:
        conn.unbind()


def move_object_within_domain(payload: MoveObjectPayload) -> MoveObjectResponse:
    """
    Moves an LDAP object (User, Group, Computer) into another OU within the same domain.
    The forest domain target is automatically detected from the target_dn.
    """
    try:
        # 1. Automatically extract the domain name from the target DN
        dn_lower = payload.target_dn.lower()
        dc_components = [part.split('=')[1] for part in dn_lower.split(',') if part.strip().startswith('dc=')]
        detected_domain = ".".join(dc_components)
        
        # 2. Dynamically connect to the matching domain forest
        conn, _ = connect_to_domain(detected_domain)
        
        try:
            # 3. Extract the clean Relative Distinguished Name (e.g., "CN=DESKTOP-PC01")
            # Active Directory requires the absolute RDN string component
            rdn = payload.target_dn.split(',')[0]
            
            # 4. Execute the move operation inside Active Directory
            # Fixed: Changed keyword argument 'new_rdn' to the correct 'relative_dn'
            if not conn.modify_dn(
                dn=payload.target_dn, 
                relative_dn=rdn, 
                new_superior=payload.new_ou_dn
            ):
                raise AppError(
                    status_code=400,
                    error="bad_request",
                    details=conn.result.get('description', 'Failed to move the object to the target OU.')
                )
                
            # Construct the new updated DN path string for the API response
            constructed_new_dn = f"{rdn},{payload.new_ou_dn}"
            
            return MoveObjectResponse(
                message=f"Object successfully moved to the new OU within domain '{detected_domain}'.",
                old_dn=payload.target_dn,
                new_dn=constructed_new_dn
            )
            
        finally:
            # 5. Guarantee structural socket breakdown to eliminate connection leakage
            conn.unbind()

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during object move: {str(e)}"
        )


def extract_sam_name(raw_name: str) -> str:
    """
    Extracts the sAMAccountName, safely removing any NetBIOS 'DOMAIN\\username' prefix.
    """
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


def find_dn(conn: Connection, raw_name: str, object_class: str, search_base: str) -> str:
    """
    Searches for an LDAP object by sAMAccountName within the explicitly targeted domain base.
    Returns the exact Distinguished Name (DN).
    """
    sam_name = extract_sam_name(raw_name)
    
    # Active Directory computer object names strictly require a trailing dollar sign
    if object_class.lower() == "computer" and not sam_name.endswith("$"):
        sam_name = f"{sam_name}$"
        
    search_filter = f"(&(objectClass={object_class})(sAMAccountName={sam_name}))"
    
    # Fixed: Use the dynamic search_base argument instead of the hardcoded global default
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
            details=f"Object '{raw_name}' (Type: {object_class}) not found in search base '{search_base}'."
        )
        
    return conn.entries[0].entry_dn


def modify_attributes(payload: ModifyMultipleAttributesPayload) -> dict:
    """
    Modifies multiple attributes on an object dynamically, auto-detecting the target domain from the DN.
    """
    try:
        # 1. Automatically extract the domain name from the target DN
        dn_lower = payload.target_dn.lower()
        dc_components = [part.split('=')[1] for part in dn_lower.split(',') if part.strip().startswith('dc=')]
        detected_domain = ".".join(dc_components)
        
        # 2. Dynamically connect to the matching domain forest
        conn, _ = connect_to_domain(detected_domain)
        
        try:
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
                "message": f"Attributes updated successfully on domain '{detected_domain}'",
                "dn": payload.target_dn,
                "updated": payload.attributes
            }
        finally:
            conn.unbind()

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during attribute modification: {str(e)}"
        )


def handle_generic_batch_modify(payload: BatchModifyAttributesPayload) -> GenericBatchResponse:
    """
    Batch update specified attributes for any type of LDAP object on a targeted forest domain.
    Returns a standardized API response model with detailed success/failure states.
    """
    try:
        if not payload.attributes:
            raise AppError(
                status_code=400,
                error="bad_request",
                details="No attributes provided for modification."
            )

        # 1. Dynamically connect to the requested forest domain
        conn, search_base = connect_to_domain(payload.domain_name)
        successful = []
        failed = []
        
        try:
            # Build the dynamic changes dictionary for the ldap3 modify operation
            changes = {}
            for attr_name, attr_value in payload.attributes.items():
                value_list = attr_value if isinstance(attr_value, list) else [attr_value]
                changes[attr_name] = [(MODIFY_REPLACE, value_list)]
                
            # Iterate over all provided objects
            for sam_name in payload.sam_account_names:
                try:
                    # Fixed: Pass the correct search_base into find_dn for multi-forest safety
                    object_dn = find_dn(conn, sam_name, payload.object_class, search_base)
                    
                    # Execute the modification for the current object
                    if conn.modify(object_dn, changes):
                        successful.append(f"Successfully updated {payload.object_class} '{sam_name}'")
                    else:
                        error_desc = conn.result.get('description', 'Modification failed')
                        failed.append(f"LDAP Error on '{sam_name}': {error_desc}")
                        
                except AppError as e:
                    failed.append(f"Lookup failed for '{sam_name}' ({payload.object_class}): {e.details}")
        finally:
            # 2. Guarantee structural socket breakdown after the loops complete
            conn.unbind()
                
        # Determine the final summary message
        if not successful and failed:
            message = f"All batch modifications for {payload.object_class} objects failed on domain '{payload.domain_name}'."
        elif successful and failed:
            message = f"Batch modifications for {payload.object_class} objects completed with some errors on domain '{payload.domain_name}'."
        else:
            message = f"All batch modifications for {payload.object_class} objects completed successfully on domain '{payload.domain_name}'."
            
        return GenericBatchResponse(
            message=message,
            successful=successful,
            failed=failed
        )

    except AppError as ae:
        raise ae
    except Exception as e:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details=f"An unexpected error occurred during generic batch modification: {str(e)}"
        )


def search_object_across_forests(payload: MultiForestSearchPayload) -> MultiForestSearchResponse:
    """
    Searches for all LDAP objects matching the sAMAccountName across all 
    dynamically configured domains loaded into the application settings.
    Returns a list of all matches found across all forests.
    """
    # 1. Fallback validation check against your parsed configurations
    if not settings.forests:
        raise AppError(
            status_code=500,
            error="internal_server_error",
            details="No AD domains were detected or configured in the environment settings."
        )

    # Active Directory handles sAMAccountNames case-insensitively
    sam_name = payload.sam_account_name
    
    # Computer accounts must be queryable via their workstation variant name token
    san_clean = sam_name.rstrip('$')
    search_filter = f"(|(sAMAccountName={san_clean})(sAMAccountName={san_clean}$))"
    requested_attributes = ['objectClass', 'sAMAccountName', 'displayName', 'description', 'mail', 'userAccountControl']
    
    matches = []

    # 2. Iterate dynamically through all configurations registered in config.py
    for domain_name, forest_cfg in settings.forests.items():
        conn = None
        try:
            # Leverage your central connection wrapper (reuses retry delays and TLS parameters)
            conn, search_base = connect_to_domain(domain_name)
            
            conn.search(
                search_base=str(search_base),
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=requested_attributes
            )
            
            if conn.entries:
                for entry in conn.entries:
                    attributes_dict = {}
                    for attr_name in entry.entry_attributes:
                        val = entry[attr_name].value
                        # Flatten list elements if they only contain a single structural value
                        if isinstance(val, list) and len(val) == 1:
                            attributes_dict[attr_name] = val[0]
                        else:
                            attributes_dict[attr_name] = val

                    matches.append(
                        DiscoveredObject(
                            found_in_domain=domain_name,
                            distinguished_name=entry.entry_dn,
                            attributes=attributes_dict
                        )
                    )
                    
        except Exception as e:
            # Gracefully log and skip dead or unreachable Domain Controllers during global lookups
            print(f"Skipping domain '{domain_name}' during cross-forest search due to exception: {str(e)}")
            continue
        finally:
            # Crucial: Safely unbind the specific forest connection if it was initialized
            if conn:
                conn.unbind()

    # 3. Enforce the required 404 response if no assets match anywhere
    if not matches:
        raise AppError(
            status_code=404,
            error="not_found",
            details=f"Object with sAMAccountName '{sam_name}' could not be found in any configured forest."
        )
        
    return MultiForestSearchResponse(
        message=f"Search completed. Found {len(matches)} matching object(s) across forests.",
        total_matches=len(matches),
        matches=matches
    )