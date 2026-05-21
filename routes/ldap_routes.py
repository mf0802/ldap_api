from fastapi import APIRouter, Response, status
from services import user, group, computer, ldap_common_service

router = APIRouter(prefix="/api")  # API routes are mounted under /api

@router.post("/object/attribute/modify", status_code=status.HTTP_200_OK)
def handle_modify_attributes(payload: ldap_common_service.ModifyMultipleAttributesPayload):
    # Modify multiple LDAP attributes for any object type using the shared service
    return ldap_common_service.modify_attributes(payload)

@router.post("/user/create", status_code=status.HTTP_201_CREATED)
def handle_create_user(payload: user.CreateUserPayload):
    # Create a new user object in LDAP and return the created DN
    user_dn = user.create_user(payload)
    return f"User created successfully: {user_dn}"

@router.post("/computer/create", status_code=status.HTTP_201_CREATED)
def handle_create_computer(payload: computer.CreateComputerPayload):
    # Create a new computer object in LDAP and return the created DN
    computer_dn = computer.create_computer(payload)
    return f"Computer created successfully: {computer_dn}"

@router.post("/group/create", status_code=status.HTTP_201_CREATED)
def handle_create_group(payload: group.CreateGroupPayload):
    # Create a new group object in LDAP and return the created DN
    group_dn = group.create_group(payload)
    return f"Group created successfully: {group_dn}"

@router.post("/group/batch")
def handle_batch_group(payload: group.BatchGroupPayload):
    # Handle batch operations for group creation or update
    return group.handle_batch(payload)

@router.patch("/group/owner", status_code=status.HTTP_200_OK)
def handle_update_group_ownership(payload: group.UpdateGroupOwnershipPayload):
    # Update the group owner attribute and return the operation result
    return group.update_group_ownership(payload)

@router.post("/object/query", status_code=status.HTTP_200_OK)
def handle_query_object(payload: ldap_common_service.QueryObjectPayload):
    # Query object attributes by sAMAccountName and object class
    return ldap_common_service.get_object_attributes(payload)

@router.delete("/user/delete", status_code=status.HTTP_200_OK)
def handle_delete_user(payload: ldap_common_service.DeleteObjectPayload):
    # Delete a user from the correct forest based on the provided domain
    result = ldap_common_service.delete_object_from_forest(payload, object_class="user")
    return result

@router.delete("/group/delete", status_code=status.HTTP_200_OK)
def handle_delete_group(payload: ldap_common_service.DeleteObjectPayload):
    # Delete a group from the correct forest based on the provided domain
    result = ldap_common_service.delete_object_from_forest(payload, object_class="group")
    return result

@router.delete("/computer/delete", status_code=status.HTTP_200_OK)
def handle_delete_computer(payload: ldap_common_service.DeleteObjectPayload):
    # Delete a computer from the correct forest based on the provided domain
    result = ldap_common_service.delete_object_from_forest(payload, object_class="computer")
    return result