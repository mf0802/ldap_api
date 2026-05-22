from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from services import user, group, computer, ldap_common_service

router = APIRouter(prefix="/api")  # API routes are mounted under /api


@router.post("/object/attribute/modify", status_code=status.HTTP_200_OK)
def handle_modify_attributes(payload: ldap_common_service.ModifyMultipleAttributesPayload):
    # Modify multiple LDAP attributes for any object type using the shared service
    return ldap_common_service.modify_attributes(payload)

@router.post("/user/create", status_code=status.HTTP_201_CREATED, response_model=user.UserCreationResponse)
def handle_create_user(payload: user.CreateUserPayload):
    # Create a new user object in LDAP and return the structured response
    return user.create_user(payload)

@router.post("/user/enable", status_code=status.HTTP_200_OK, response_model=user.UserActivationResponse)
def handle_enable_user(payload: user.EnableUserPayload):
    # Set an AD-compliant password and enable the specified user account
    return user.enable_user_with_password(payload.distinguished_name)

@router.post("/computer/create", status_code=status.HTTP_201_CREATED, response_model=computer.ComputerCreationResponse)
def handle_create_computer(payload: computer.CreateComputerPayload):
    # Create a new computer object in LDAP and return the structured response
    return computer.create_computer(payload)

@router.post("/group/create", status_code=status.HTTP_201_CREATED, response_model=group.GroupCreationResponse)
def handle_create_group(payload: group.CreateGroupPayload):
    # Create a new group object in LDAP and return the structured response
    return group.create_group(payload)

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

@router.delete("/user/delete", status_code=status.HTTP_200_OK, response_model=ldap_common_service.ObjectDeletionResponse)
def handle_delete_user(payload: ldap_common_service.DeleteObjectPayload):
    # Delete a user from the correct forest based on the provided domain
    return ldap_common_service.delete_object_from_forest(payload, object_class="user")

@router.delete("/group/delete", status_code=status.HTTP_200_OK, response_model=ldap_common_service.ObjectDeletionResponse)
def handle_delete_group(payload: ldap_common_service.DeleteObjectPayload):
    # Delete a group from the correct forest based on the provided domain
    return ldap_common_service.delete_object_from_forest(payload, object_class="group")

@router.delete("/computer/delete", status_code=status.HTTP_200_OK, response_model=ldap_common_service.ObjectDeletionResponse)
def handle_delete_computer(payload: ldap_common_service.DeleteObjectPayload):
    # Delete a computer from the correct forest based on the provided domain
    return ldap_common_service.delete_object_from_forest(payload, object_class="computer")

@router.post("/user/clone", status_code=status.HTTP_201_CREATED)
def handle_clone_user(payload: user.DynamicCloneUserPayload):
    # This automatically returns the new rich JSON structure containing the password
    return user.clone_user(payload)