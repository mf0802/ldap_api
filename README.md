# 📖 LDAP API – cURL Reference Guide

This guide provides a comprehensive list of cURL commands to interact with the LDAP API endpoints.

## 🔒 Authentication
All requests must include the API key in the HTTP header:
* **Header Name:** `X-API-Key`
* **Value:** `your_api_key_here`

---

## 🛠 General Object Operations

### 1. Universally Modify Attribute
Modifies a specific attribute of any existing LDAP object (User, Group, or Computer) using `MODIFY_REPLACE`.

```bash
curl -X POST http://localhost:3000/api/object/attribute/modify \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "target_dn": "CN=Max Mustermann,OU=TestingOU,DC=samdom,DC=example,DC=com",
    "attribute": "department",
    "value": "IT-Operations"
  }'
```

### 2. Query Object Attributes
Retrieves all whitelisted attributes of an object based on its `sAMAccountName`.

```bash
curl -X POST http://localhost:3000/api/object/query \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "sam_account_name": "GG_Marketing",
    "object_class": "group"
  }'
```

---

## 👤 User Management

### 1. Create User
Creates a new user in the specified OU path. The user is created in a *Disabled* state (`514`) by default.

```bash
curl -X POST http://localhost:3000/api/user/create \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "sam_account_name": "m.mustermann",
    "first_name": "Max",
    "last_name": "Mustermann",
    "ou_dn": "OU=TestingOU,DC=samdom,DC=example,DC=com"
  }'
```

### 2. Delete Group from Specific Forest
```bash
curl -X DELETE http://localhost:3000/api/group/delete \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "prod.firma.local",
    "sam_account_name": "GG_Marketing"
  }'
```

---

## 👥 Group Management

### 1. Create Group
Creates a new security group inside a specific Organizational Unit (OU).

```bash
curl -X POST http://localhost:3000/api/group/create \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "GG_Marketing",
    "ou_dn": "OU=TestingOU,DC=samdom,DC=example,DC=com"
  }'
```

### 2. Delete Group from Specific Forest
```bash
curl -X DELETE http://localhost:3000/api/group/delete \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "prod.firma.local",
    "sam_account_name": "GG_Marketing"
  }'
```

### 3. Batch Manage Group Members
Adds or removes multiple users to/from multiple groups simultaneously.

```bash
curl -X POST http://localhost:3000/api/group/batch \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "add",
    "group_names": ["domain\\GG_Marketing", "domain\\GG_Sales"],
    "user_names": ["domain\\m.mustermann", "domain\\l.schmidt"]
  }'
```

### 4. Manage Group Ownership
Updates owner email addresses inside the `info` field (Notes) of the group. Preserves existing non-owner free text within the field.

```bash
curl -X PATCH http://localhost:3000/api/group/owner \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "GG_Marketing",
    "add_owners": "owner1@example.com,owner2@example.com",
    "delete_owners": "old_owner@example.com"
  }'
```

---

## 💻 Computer Management

### 1. Create Computer
Creates a new computer account inside the directory.

```bash
curl -X POST http://localhost:3000/api/computer/create \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "computer_name": "DESKTOP-PC01",
    "ou_dn": "OU=Computers,DC=samdom,DC=example,DC=com"
  }'
```

### 2. Delete Computer from Specific Forest
```bash
curl -X DELETE http://localhost:3000/api/computer/delete \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "test.forest.net",
    "sam_account_name": "DESKTOP-PC01"
  }'
```