from fastapi import APIRouter, Response, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services import user, group, computer, ldap_common_service
from errors import AppError

router = APIRouter(prefix="/api")  # API routes are mounted under /api


# =====================================================================
# ATTRIBUTE MODIFICATION & GENERIC UTILITY ENDPOINTS
# =====================================================================
@router.post("/object/attribute/modify", status_code=status.HTTP_200_OK)
def handle_modify_attributes(payload: ldap_common_service.ModifyMultipleAttributesPayload):
    """
    Modifies multiple LDAP attributes for any object type (Domain auto-detected from DN)
    """
    return ldap_common_service.modify_attributes(payload)

@router.post("/object/query", status_code=status.HTTP_200_OK)
def handle_query_object(payload: ldap_common_service.QueryObjectPayload):
    """
    Query object attributes by sAMAccountName, object class, and domain_name
    """
    return ldap_common_service.get_object_attributes(payload)

@router.post("/object/batch/modify", status_code=status.HTTP_200_OK, response_model=ldap_common_service.GenericBatchResponse)
def handle_batch_modify_attributes(payload: ldap_common_service.BatchModifyAttributesPayload):
    """
    Batch modify specified attributes for any LDAP object type on a target domain
    """
    return ldap_common_service.handle_generic_batch_modify(payload)

@router.post("/object/search/multi-forest", status_code=status.HTTP_200_OK, response_model=ldap_common_service.MultiForestSearchResponse)
def handle_multi_forest_search(payload: ldap_common_service.MultiForestSearchPayload):
    """
    Search for an object across ALL configured AD forests simultaneously
    """
    return ldap_common_service.search_object_across_forests(payload)

@router.post("/object/move", status_code=status.HTTP_200_OK, response_model=ldap_common_service.MoveObjectResponse)
def handle_move_object(payload: ldap_common_service.MoveObjectPayload):
    """
    Moves any existing LDAP object (Computer, User, Group) into a different Organizational Unit (OU).
    """
    return ldap_common_service.move_object_within_domain(payload)

# =====================================================================
# ACCOUNT LIFECYCLE MANAGEMENT ENDPOINTS (USER, GROUP, COMPUTER)
# =====================================================================
@router.post("/user/create", status_code=status.HTTP_201_CREATED, response_model=user.UserCreationResponse)
def handle_create_user(payload: user.CreateUserPayload):
    """
    Creates a new user object on the specified target domain
    """
    return user.create_user(payload)

@router.post("/user/enable", status_code=status.HTTP_200_OK, response_model=user.UserActivationResponse)
def handle_enable_user(payload: user.EnableUserPayload):
    """
    Sets an AD-compliant password and enables the user account (Domain auto-detected from DN)
    """
    return user.enable_user_with_password(payload.distinguished_name)

@router.post("/user/clone", status_code=status.HTTP_201_CREATED)
def handle_clone_user(payload: user.DynamicCloneUserPayload):
    """
    Clones a user profile cross-forest from a source domain to a target domain
    """
    return user.clone_user(payload)

@router.post("/computer/create", status_code=status.HTTP_201_CREATED, response_model=computer.ComputerCreationResponse)
def handle_create_computer(payload: computer.CreateComputerPayload):
    """
    Creates a new workstation computer object on the specified target domain
    """
    return computer.create_computer(payload)

@router.post("/group/create", status_code=status.HTTP_201_CREATED, response_model=group.GroupCreationResponse)
def handle_create_group(payload: group.CreateGroupPayload):
    """
    Creates a new group object on the specified target domain
    """
    return group.create_group(payload)


# =====================================================================
# GROUP MEMBERSHIP & OWNERSHIP ENDPOINTS
# =====================================================================
@router.post("/group/batch", status_code=status.HTTP_200_OK, response_model=group.BatchGroupResponse)
def handle_batch_group(payload: group.BatchGroupPayload):
    """
    Batch add or remove users to/from groups on a targeted forest domain
    """
    return group.handle_batch(payload)

@router.patch("/group/owner", status_code=status.HTTP_200_OK, response_model=group.GroupOwnershipResponse)
def handle_update_group_ownership(payload: group.UpdateGroupOwnershipPayload):
    """
    Updates the owner metadata for a targeted group object
    """
    return group.update_group_ownership(payload)


# =====================================================================
# DELETION OPERATIONS (Refactored to match centralized service logic)
# =====================================================================
@router.delete("/user/delete", status_code=status.HTTP_200_OK, response_model=ldap_common_service.ObjectDeletionResponse)
def handle_delete_user(payload: ldap_common_service.DeleteObjectPayload):
    """
    Deletes a user object from the specified target domain
    """
    # Unified handler: Resolves identity cross-type and deletes it safely
    return ldap_common_service.delete_object(payload)

@router.delete("/group/delete", status_code=status.HTTP_200_OK, response_model=ldap_common_service.ObjectDeletionResponse)
def handle_delete_group(payload: ldap_common_service.DeleteObjectPayload):
    """
    Deletes a group object from the specified target domain
    """
    # Unified handler: Resolves identity cross-type and deletes it safely
    return ldap_common_service.delete_object(payload)

@router.delete("/computer/delete", status_code=status.HTTP_200_OK, response_model=ldap_common_service.ObjectDeletionResponse)
def handle_delete_computer(payload: ldap_common_service.DeleteObjectPayload):
    """
    Deletes a computer object from the specified target domain
    """
    # Unified handler: Resolves identity cross-type and deletes it safely
    return ldap_common_service.delete_object(payload)


# =====================================================================
# SECURITY & POLICIES SECURITY (LOCKOUTS, PASSWORDS)
# =====================================================================
@router.post("/user/lockout/check", status_code=status.HTTP_200_OK, response_model=user.UserLockoutStatusResponse)
def handle_check_user_lockout(payload: user.CheckLockoutPayload):
    """
    Check if user account is locked out (Domain auto-detected from DN)
    """
    return user.check_user_lockout(payload.distinguished_name)

@router.post("/user/unlock", status_code=status.HTTP_200_OK, response_model=user.UserUnlockResponse)
def handle_unlock_user(payload: user.CheckLockoutPayload):
    """
    Manually unlock a locked user account (Domain auto-detected from DN)
    """
    return user.unlock_user(payload.distinguished_name)

@router.post("/user/password/reset-temporary", status_code=status.HTTP_200_OK, response_model=user.PasswordResetRandomResponse)
def handle_user_password_reset_random(payload: user.ResetPasswordRandomPayload):
    """
    Resets an account password to a secure random variant (Domain auto-detected from DN)
    """
    return user.reset_user_password_random(payload)
