# 🖖 Demo for a python based LDAP / Active Directory API

Due to some reason we need a LDAP API to manage Active Directory objects from several backends like ServiceNow, Elementum, Azure, etc.
To implement this I have started to create a python based API. 

- For development and testing I'm using Docker containers to simulate fake multi forest structures.
- I tried to build all options we need for our day-to-day work, but the code structure allows to enhance the functionality with low effort.
- The security is limited to an API key for development, since the final solution will be hosted in an Azure App with higher security.
- The solution has not been tested against a real Active Directory yet!
  - The account locked and password parts must be confirmed. Other functions should work since it's standard LDAP. 

**Have fun! If you find errors you can keep them 😁**
---

# Docker Infrastructure Documentation for Fake Active Directory Environments

This documentation describes the multi-domain Active Directory test setup running inside Docker. It is designed to emulate multiple isolated forest structures (`domaina.local`, `://example.com`, and `test.forest.net`) locally for API development, cross-forest account cloning, and integration testing.

---

## 🏗️ Architecture Overview

The containerized infrastructure consists of independent Samba4 AD containers utilizing the lightweight `smblds/smblds` image. Each instance runs its own LDAP/LDAPS daemon, Kerberos realm, and dynamic seed provisioning script.

### Network Port Mappings

To prevent local interface allocation conflicts (`Port is already allocated`), host ports are strictly separated:


| Container Name | Domain / Forest Name | Internal Port | Mapped Host Port | Protocol |
| :--- | :--- | :--- | :--- | :--- |
| `fake_ad_domain_a` | `domaina.local` | `389`<br>`636` | **`389`**<br>**`636`** | LDAP (Insecure)<br>LDAPS (Secure TLS) |
| `fake_ad_domain_b` | `://example.com` | `389`<br>`636` | **`3389`**<br>**`3636`** | LDAP (Insecure)<br>LDAPS (Secure TLS) |
| `fake_ad_domain_c` | `test.forest.net` | `389`<br>`636` | **`4389`**<br>**`4636`** | LDAP (Insecure)<br>LDAPS (Secure TLS) |

---

## 🛠️ Orchestration (`docker-compose.yml`)

The infrastructure configuration uses a single orchestrator. All sensitive modifications to passwords (`unicodePwd`) and system attributes require secure `ldaps://` targets, which are exposed via host ports `636`, `3636`, and `4636`.

```yaml
version: '3.8'

services:
  # ==========================================
  # Domain A: Source Domain (domaina.local)
  # ==========================================
  samba-ad-a:
    image: smblds/smblds:latest
    container_name: fake_ad_domain_a
    platform: linux/amd64
    restart: unless-stopped
    environment:
      INSECURE_LDAP: "true"
      REALM: "DOMAINA.LOCAL"
      DOMAIN: "DOMAINA"
      ADMINPASS: "SecretA123!"
    ports:
      - "389:389"
      - "636:636"
    volumes:
      - ./entrypoint_a.d:/entrypoint.d

  # ==========================================
  # Domain B: Target/Default Domain (://example.com)
  # ==========================================
  samba-ad-b:
    image: smblds/smblds:latest
    container_name: fake_ad_domain_b
    platform: linux/amd64
    restart: unless-stopped
    environment:
      INSECURE_LDAP: "true"
      REALM: "://example.com"
      DOMAIN: "SAMDOM"
      ADMINPASS: "SecretB123!"
    ports:
      - "3389:389"
      - "3636:636"
    volumes:
      - ./entrypoint_b.d:/entrypoint.d

  # ==========================================
  # Domain C: External Test Domain (test.forest.net)
  # ==========================================
  samba-ad-c:
    image: smblds/smblds:latest
    container_name: fake_ad_domain_c
    platform: linux/amd64
    restart: unless-stopped
    environment:
      INSECURE_LDAP: "true"
      REALM: "TEST.FOREST.NET"
      DOMAIN: "TESTFOREST"
      ADMINPASS: "SecretC123!"
    ports:
      - "4389:389"
      - "4636:636"
    volumes:
      - ./entrypoint_c.d:/entrypoint.d
```

---

## 🚀 Directory Seeding Scripts (Data Provisioning)

Samba containers parse the bound `./entrypoint_*.d` directory on initial boot. Scripts inside must contain execution privileges (`chmod +x`) and use POSIX-compliant syntax.

### 📄 Domain A Setup (`./entrypoint_a.d/01-provision_a.sh`)
Populates Domain A with predictable, stable data structures for reproduction tests.

```bash
#!/bin/sh
echo "=== Starting provisioning of Domain A (Source) ==="

samba-tool ou create "OU=TestingOU"

samba-tool user create john.doe "SourcePass123!" \
  --userou="OU=TestingOU" \
  --surname="Doe" \
  --given-name="John" \
  --mail="john.doe@domainA.local" \
  --job-title="DevOps Engineer" \
  --department="IT-Infrastructure" \
  --telephone-number="+49 123 456789"

samba-tool user create jane.smith "SourcePass456!" \
  --userou="OU=TestingOU" \
  --surname="Smith" \
  --given-name="Jane" \
  --mail="jane.smith@domainA.local" \
  --job-title="Frontend Developer" \
  --department="Software-Engineering"

echo "=== Domain A Provisioning completed ==="
```

### 📄 Domain B Setup (`./entrypoint_b.d/01-provision_b.sh`)
Populates Domain B using an automated randomization pattern to simulate dynamic user growth. Scripts inside must contain execution privileges (`chmod +x`) and use POSIX-compliant syntax.

```bash
#!/bin/sh
echo "=== Starting provisioning of dynamic AD test data ==="

samba-tool ou create "OU=TestingOU"
samba-tool ou create "OU=Groups,OU=TestingOU,DC=samdom,DC=example,DC=com"

# Generate 3 randomized groups
for i in 1 2 3; do
  RAND_ID=$(awk 'BEGIN{srand();print int(rand()*9000)+1000}')
  samba-tool group add "Group-${RAND_ID}" --groupou="OU=Groups,OU=TestingOU"
done

# Generate 5 randomized users matching complexity constraints
FIRST_NAMES="John Jane Alex Emily Michael Sarah"
LAST_NAMES="Smith Doe Taylor Brown Wilson Miller"

for i in 1 2 3 4 5; do
  F_NAME=$(echo "$FIRST_NAMES" | awk -v r=$(( (RANDOM % 6) + 1 )) '{print $r}')
  L_NAME=$(echo "$LAST_NAMES" | awk -v r=$(( (RANDOM % 6) + 1 )) '{print $r}')
  RAND_NUM=$(awk 'BEGIN{srand();print int(rand()*90)+10}')
  USERNAME=$(echo "${F_NAME}.${L_NAME}${RAND_NUM}" | tr '[:upper:]' '[:lower:]')
  
  samba-tool user create "${USERNAME}" "SecurePass${RAND_NUM}!" \
    --userou="OU=TestingOU" \
    --surname="${L_NAME}" \
    --given-name="${F_NAME}"
done

echo "=== Provisioning completed ==="
```

### 📄 Domain C Setup (`./entrypoint_c.d/01-provision_c.sh`)
Populates Domain C with predictable, stable data structures for reproduction tests. Scripts inside must contain execution privileges (`chmod +x`) and use POSIX-compliant syntax.

```bash
#!/bin/sh
echo "=== Starting provisioning of Domain C (External Test Domain) ==="

# 1. Create a base Organizational Unit (OU) for source accounts
samba-tool ou create "OU=TestingOU"

# 2. Create standard test users with fixed data for reproduction
# User 1: John Doe
echo "Creating source user: john.doe"
samba-tool user create john.doe "SourcePass123!" \
  --userou="OU=TestingOU" \
  --surname="Doe" \
  --given-name="Jane" \
  --mail="jane.doe@domainC.local" \
  --job-title="Support Engineer" \
  --department="IT-Infrastructure" \
  --telephone-number="+49 123 34567"

# User 2: Jane Smith
echo "Creating source user: blake.smith"
samba-tool user create blake.smith "SourcePass456!" \
  --userou="OU=TestingOU" \
  --surname="Smith" \
  --given-name="Blake" \
  --mail="blake.smith@domainC.local" \
  --job-title="Backend Developer" \
  --department="Software-Engineering"

echo "=== Domain A Provisioning completed ==="
```

---

## 🪵 Operational Runbooks

### Initial Start & Infrastructure Rebuild
When altering `.env` variables or resetting state, database shards inside volume stores must be purged completely before structural properties can re-bind.

```bash
# 1. Stop all runtime instances and scrub underlying persistence blocks
docker compose down --volumes --remove-orphans

# 2. Hard purge potential lingering platform caches
docker rm -f fake_active_directory fake_ad_domain_a fake_ad_domain_b fake_ad_domain_c 2>/dev/null

# 3. Fire up fresh containers asynchronously
docker compose up -d

# 4. Monitor provisioning progress (Wait approx 15 seconds until daemons loop out "ready")
docker compose logs -f
```

### Local Network Connection Troubleshooting
If a container loops out port mapping exceptions, identify host bindings occupying the LDAP parameters:

* **Unix/macOS Toolchain:**
  ```bash
  sudo lsof -i :389
  ```
* **Windows (PowerShell Core):**
  ```powershell
  Get-NetTCPConnection -LocalPort 389
  ```

# 📖 LDAP API – cURL Reference Guide

This guide provides a comprehensive list of cURL commands to interact with the LDAP API endpoints.

## 🔒 Authentication
All requests must include the API key in the HTTP header:
* **Header Name:** `X-API-Key`
* **Value:** `your_api_key_here`


## ⚙️ Fake `.env` example

```bash
API_PORT=3000
X_API_KEY=your_api_key_here

# LDAP Retry Configuration
LDAP_MAX_RETRIES=3
LDAP_RETRY_DELAY_SECS=2

# === DOMAIN A ===
DOMAIN_A_NAME=domaina.local
DOMAIN_A_SERVER=ldaps://localhost:636
DOMAIN_A_USER=CN=Administrator,CN=Users,DC=domainA,DC=local
DOMAIN_A_PASSWORD=P@ssW0rd123
DOMAIN_A_SEARCH_BASE=DC=domainA,DC=local

# === DOMAIN B ===
DOMAIN_B_NAME=samdom.example.com
DOMAIN_B_SERVER=ldaps://localhost:3636
DOMAIN_B_USER=CN=Administrator,CN=Users,DC=samdom,DC=example,DC=com
DOMAIN_B_PASSWORD=P@ssW0rd123
DOMAIN_B_SEARCH_BASE=DC=samdom,DC=example,DC=com

# === DOMAIN C ===
DOMAIN_C_NAME=test.forest.net
DOMAIN_C_SERVER=ldaps://localhost:4636
DOMAIN_C_USER=CN=Administrator,CN=Users,DC=test,DC=forest,DC=net
DOMAIN_C_PASSWORD=P@ssW0rd123
DOMAIN_C_SEARCH_BASE=DC=test,DC=forest,DC=net
```
---

## 🛠 General Object Operations/Routes

```text
+----------------------------------------+------------------------------------------------------------------------+
| ROUTE                                  | DESCRIPTION                                                            |
+----------------------------------------+------------------------------------------------------------------------+
GENERAL HELPERS
| POST   /object/attribute/modify        | Modifies multiple LDAP attributes for any object type.                 |
| POST   /object/query                   | Queries object attributes by sAMAccountName and object class.          |
| POST   /object/batch/modify            | Batch modifies specified attributes for any LDAP object type.          |
| POST   /object/search/multi-forest     | Searches for an object by sAMAccountName across all configured forests.|
| POST   /object/move                    | Move an object by DN between domains.                                  |
+----------------------------------------+------------------------------------------------------------------------+
USER
| POST   /user/create                    | Creates a new user object in LDAP.                                     |
| POST   /user/enable                    | Sets an AD-compliant password and enables the user account.            |
| POST   /user/clone                     | Clones a user and returns a rich JSON structure including password.    |
| POST   /user/lockout/check             | Checks if the specified user account is currently locked out.          |
| POST   /user/unlock                    | Manually unlocks a locked Active Directory user account.               |
| DELETE /user/delete                    | Deletes a user from the correct forest based on the provided domain.   |
| POST   /user/password/reset-temporary  | Resets a user password with a newly generated temporary one.           |
+----------------------------------------+------------------------------------------------------------------------+
GROUP
| POST   /group/create                   | Creates a new group object in LDAP.                                    |
| POST   /group/batch                    | Handles batch operations for group creation or update.                 |
| PATCH  /group/owner                    | Updates the group owner attribute.                                     |
| DELETE /group/delete                   | Deletes a group from the correct forest based on the provided domain.  |
+----------------------------------------+------------------------------------------------------------------------+
COMPUTER
| POST   /computer/create                | Creates a new computer object in LDAP.                                 |
| DELETE /computer/delete                | Deletes a computer from the correct forest based on the domain.        |
+----------------------------------------+------------------------------------------------------------------------+
```

### 1. Universally Modify Attribute
Modifies a specific attribute of any existing LDAP object (User, Group, or Computer) using `MODIFY_REPLACE`.

```bash
curl -X POST http://localhost:3000/api/object/attribute/modify \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "target_dn": "cn=John Doe,OU=TestingOU,DC=samdom,DC=example,DC=com",
    "attributes": {
      "displayName": "John R. Doe",
      "telephoneNumber": "+49 123 456789",
      "title": "DevOps Engineer",
      "department": "IT-Infrastructure"
    }
  }'
```

### 2. Query single Object Attributes
Retrieves all whitelisted attributes of an object based on its `sAMAccountName`.

```bash
curl -X POST http://localhost:3000/api/object/query \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "samdom.example.com",
    "sam_account_name": "GG_Marketing",
    "object_class": "group"
  }'

```

### 3. Batch modify attributes
Batch based modification of AD attributes by object type (user, computer, group)

```bash
curl -X POST http://localhost:3000/api/object/batch/modify \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "samdom.example.com",
    "sam_account_names": ["mmustermann", "jdoe"],
    "object_class": "user",
    "attributes": {
      "description": "Updated via API Batch Operations",
      "title": "Senior IT Engineer"
    }
  }'

```

### 4. Multi-Forest query option
This uses the domain information hostet in the `.env` file to go through each domain to query by sAMAccountName.

```bash
curl -X POST http://localhost:3000/api/object/search/multi-forest \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "sam_account_name": "awilson"
  }'
```

### 5. Move Object to another OU
Moves any existing LDAP object (User, Group, or Computer) into a different Organizational Unit (OU) within the same domain forest.

```bash
curl -X POST http://localhost:3000/api/object/move \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "target_dn": "CN=DESKTOP-PC01,CN=Computers,DC=samdom,DC=example,DC=com",
    "new_ou_dn": "OU=Staging,OU=Workstations,DC=samdom,DC=example,DC=com"
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
    "domain_name": "samdom.example.com",
    "sam_account_name": "m.mustermann",
    "first_name": "Max",
    "last_name": "Mustermann",
    "ou_dn": "OU=TestingOU,DC=samdom,DC=example,DC=com"
  }'
```

### 2. Delete User from Specific Forest
```bash
curl -X DELETE http://localhost:3000/api/user/delete \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "samdom.example.com",
    "sam_account_name": "m.mustermann"
  }'
```

### 3. Clone User from domain B to domain A and share new password
You can specify the users temporary password using optional argument: `temporary_password`

```bash
curl -X POST http://localhost:3000/api/user/clone \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "source_domain": "samdom.example.com",
    "source_user_dn": "CN=Sarah Wilson,OU=TestingOU,DC=samdom,DC=example,DC=com",
    "target_domain": "domaina.local",
    "target_ou_dn": "OU=TestingOU,DC=domainA,DC=local"
  }'
```

### 4. Enable User with password
```bash
curl -X POST http://localhost:3000/api/user/enable \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "distinguished_name": "CN=Max Mustermann,OU=TestingOU,DC=samdom,DC=example,DC=com"
  }'
```

### 5. Check User account locked state
```bash
curl -X POST http://localhost:3000/api/user/lockout/check \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "distinguished_name": "CN=Alex Wilson,OU=TestingOU,DC=samdom,DC=example,DC=com"
  }'
```

### 6. Unlock User account
```bash
curl -X POST http://localhost:3000/api/user/unlock \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "distinguished_name": "CN=Alex Wilson,OU=TestingOU,DC=samdom,DC=example,DC=com"
  }'
```

### 7. Reset User password
```bash
curl -X POST http://localhost:3000/api/user/password/reset-temporary \
     -H "X-API-Key: your_api_key_here" \
     -H "Content-Type: application/json" \
     -d '{
       "distinguished_name": "cn=John Doe,OU=TestingOU,DC=samdom,DC=example,DC=com"
     }'
```

---

## 👥 Group Management

### 1. Create Group
Creates a new security group inside a specific Organizational Unit (OU).
Use the optional argument `"info":"Owners:test1@samdom.com;"` if you want to set the owners during creation.

```bash
curl -X POST http://localhost:3000/api/group/create \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "samdom.example.com",
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
    "domain": "samdom.example.com",
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
    "domain_name": "samdom.example.com",
    "action": "add",
    "group_names": ["GG_Marketing", "GG_Sales"],
    "user_names": ["m.mustermann", "l.schmidt"]
  }'
```

### 4. Manage Group Ownership
Updates owner email addresses inside the `info` field (Notes) of the group. Preserves existing non-owner free text within the field.
**Note:** that's a custom company based option how we manage multiple owners for an AD group.

```bash
curl -X PATCH http://localhost:3000/api/group/owner \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "samdom.example.com",
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
    "domain_name": "://example.com",
    "computer_name": "DESKTOP-PC01",
    "ou_dn": "CN=Computers,DC=samdom,DC=example,DC=com"
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