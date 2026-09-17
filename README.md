# 🖖 Demo for a python based LDAP / Active Directory API

Due to some reason we need a LDAP API to manage Active Directory objects from several backends like ServiceNow, Elementum, Azure, etc.
To implement this I have started to create a python based API. 

- For development and testing I'm using Docker containers to simulate fake multi forest structures.
- I tried to build all options we need for our day-to-day work, but the code structure allows to enhance the functionality with low effort.
- The security using an API key and self signed certs for development, since the final solution will be hosted in an Azure App with higher security.
- The solution has not been tested against a real Active Directory yet!
  - The account locked and password parts must be confirmed. Other functions should work since it's standard LDAP. 

**Have fun! If you find errors you can keep them 😁**
---

# Docker Infrastructure Documentation for Fake Active Directory Environments

You must have docker installed to use this API. I have successfully tested this project against MacOS and Linux only.

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
services:
  # Domain A: Source Domain (domainA.local)
  samba-ad-a:
    image: smblds/smblds:latest
    container_name: fake_ad_domain_a
    platform: linux/amd64
    restart: unless-stopped
    environment:
      INSECURE_LDAP: "true"
      REALM: "DOMAINA.LOCAL"       # Becomes DC=domainA,DC=local
      DOMAIN: "DOMAINA"             # NetBIOS short name
      ADMINPASS: "SecretA123!"     # Password for CN=Administrator
    ports:
      - "389:389"   # Standard LDAP (Maps to DOMAIN_A_SERVER)
      - "636:636"   # LDAPS
    volumes:
      - ./entrypoint_a.d:/entrypoint.d
      - ./dev-certs:/certs  # <-- Point this to your project subfolder with the certs for DOMAIN_A_SERVER

  # Domain B: Target Domain (samdom.example.com)
  samba-ad-b:
    image: smblds/smblds:latest
    container_name: fake_ad_domain_b
    platform: linux/amd64
    restart: unless-stopped
    environment:
      INSECURE_LDAP: "true"
      REALM: "SAMDOM.EXAMPLE.COM"  # Becomes DC=samdom,DC=example,DC=com
      DOMAIN: "SAMDOM"              # NetBIOS short name
      ADMINPASS: "SecretB123!"     # Password for CN=Administrator
    ports:
      - "3389:389"  # Standard LDAP (Maps to DOMAIN_B_SERVER)
      - "3636:636"  # LDAPS
    volumes:
      - ./entrypoint_b.d:/entrypoint.d
      - ./dev-certs:/certs  # <-- Point this to your project subfolder with the certs for DOMAIN_B_SERVER
  
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
      - ./dev-certs:/certs  # <-- Point this to your project subfolder with the certs for DOMAIN_C_SERVER
```

## 🛠️ Generate certificates for development (helper script)

```bash
#!/bin/sh
# generate_dev_certs.sh

# Exit immediately if any command fails
set -e

# Define paths relative to project layout
CERTS_DIR="./dev-certs"

echo "===================================================="
echo "Starting Certificate Generation for Development"
echo "===================================================="

# 1. Create the destination subfolder
mkdir -p "$CERTS_DIR"

# 2. Generate a Shared local Certificate Authority (CA)
echo "\n[1/4] Generating Local Certificate Authority (CA)..."
openssl genrsa -out "$CERTS_DIR/ca.key" 2048 2>/dev/null
openssl req -x509 -new -nodes \
  -key "$CERTS_DIR/ca.key" \
  -sha256 -days 365 \
  -out "$CERTS_DIR/ca.crt" \
  -subj "/CN=Dev-CA"

# 3. Generate Domain Server Keys & Certificates
echo "\n[2/4] Generating Domain Server Certificates..."

# --- Domain A: domaina.local ---
openssl genrsa -out "$CERTS_DIR/domaina.key" 2048 2>/dev/null
openssl req -new -key "$CERTS_DIR/domaina.key" -out "$CERTS_DIR/domaina.csr" -subj "/CN=domaina.local"
openssl x509 -req -in "$CERTS_DIR/domaina.csr" -CA "$CERTS_DIR/ca.crt" -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial -out "$CERTS_DIR/domaina.crt" -days 365 -sha256 2>/dev/null

# --- Domain B: example.com ---
openssl genrsa -out "$CERTS_DIR/domainb.key" 2048 2>/dev/null
openssl req -new -key "$CERTS_DIR/domainb.key" -out "$CERTS_DIR/domainb.csr" -subj "/CN=example.com"
openssl x509 -req -in "$CERTS_DIR/domainb.csr" -CA "$CERTS_DIR/ca.crt" -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial -out "$CERTS_DIR/domainb.crt" -days 365 -sha256 2>/dev/null

# --- Domain C: test.forest.net ---
openssl genrsa -out "$CERTS_DIR/domainc.key" 2048 2>/dev/null
openssl req -new -key "$CERTS_DIR/domainc.key" -out "$CERTS_DIR/domainc.csr" -subj "/CN=test.forest.net"
openssl x509 -req -in "$CERTS_DIR/domainc.csr" -CA "$CERTS_DIR/ca.crt" -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial -out "$CERTS_DIR/domainc.crt" -days 365 -sha256 2>/dev/null

# 4. Generate the Shared Client Certificate (CN=Administrator)
echo "\n[3/4] Generating Shared Client Certificate..."
openssl genrsa -out "$CERTS_DIR/client.key" 2048 2>/dev/null
openssl req -new -key "$CERTS_DIR/client.key" -out "$CERTS_DIR/client.csr" -subj "/CN=Administrator"
openssl x509 -req -in "$CERTS_DIR/client.csr" -CA "$CERTS_DIR/ca.crt" -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial -out "$CERTS_DIR/client.crt" -days 365 -sha256 2>/dev/null

# 5. Clean up temporary CSR and Serial tracking files
echo "\n[4/4] Cleaning up intermediate CSR configuration artifacts..."
rm -f "$CERTS_DIR"/*.csr
rm -f "$CERTS_DIR"/*.srl

echo "===================================================="
echo "SUCCESS: All certificates generated in $CERTS_DIR/"
echo "===================================================="
```

---

## 🚀 Directory Seeding Scripts (Data Provisioning)

Samba containers parse the bound ./entrypoint_*.d directory on initial boot. Scripts inside must contain execution privileges (chmod +x) and use POSIX-compliant syntax.

📄 Domain A Setup (./entrypoint_a.d/01-provision_a.sh)

Populates Domain A with predictable, stable data structures for reproduction tests.

```bash
#!/bin/sh
echo "=== Starting provisioning of Domain A (Source) ==="

# entrypoint_a.d/setup_certs.sh
mkdir -p /etc/samba/tls

# Docker mirrors your host's ./dev-certs folder into the container's /certs folder
cp /certs/ca.crt /etc/samba/tls/ca.crt
cp /certs/domaina.crt /etc/samba/tls/domaina.crt
cp /certs/domaina.key /etc/samba/tls/domaina.key

chmod 600 /etc/samba/tls/domaina.key

# Step 1: Create base testing Organizational Unit
echo "Creating base structures..."
samba-tool ou create "OU=TestingOU"

# Step 2: Create standard test users
echo "Creating source user: john.doe"
samba-tool user create john.doe "SourcePass123!" \
  --userou="OU=TestingOU" \
  --surname="Doe" \
  --given-name="John" \
  --mail="john.doe@domainA.local" \
  --job-title="DevOps Engineer" \
  --department="IT-Infrastructure" \
  --telephone-number="+49 123 456789"

# User 2: Jane Smith (Populating the comment attribute via description parameter)
echo "Creating source user: jane.smith"
samba-tool user create jane.smith "SourcePass456!" \
  --userou="OU=TestingOU" \
  --surname="Smith" \
  --given-name="Jane" \
  --mail="jane.smith@domainA.local" \
  --job-title="Frontend Developer" \
  --department="Software-Engineering" \
  --description="TRUE_LITIGATION_HOLD_2026"

echo "=== Domain A Provisioning completed ==="
```

📄 Domain A Setup (./entrypoint_a.d/setup_certs.sh)

```bash
#!/bin/sh
# entrypoint_a.d/setup_certs.sh

mkdir -p /etc/samba/tls

# Copy generated certificates from the mounted project subfolder
cp /certs/ca.crt /etc/samba/tls/ca.crt
cp /certs/domaina.crt /etc/samba/tls/domaina.crt
cp /certs/domaina.key /etc/samba/tls/domaina.key
chmod 600 /etc/samba/tls/domaina.key

# Append configuration to smb.conf securely
cat <<EOF >> /etc/samba/smb.conf
[global]
    tls enabled = yes
    tls keyfile = /etc/samba/tls/domaina.key
    tls certfile = /etc/samba/tls/domaina.crt
    tls cafile = /etc/samba/tls/ca.crt
    tls verify peer = ca_and_name
EOF
echo "Samba container TLS parameters written successfully."
```

📄 Domain B Setup (./entrypoint_b.d/01-provision_b.sh)

Populates Domain B using an automated randomization pattern to simulate dynamic user growth.

```bash
#!/bin/sh
echo "=== Starting provisioning of dynamic AD test data ==="

# entrypoint_a.d/setup_certs.sh
mkdir -p /etc/samba/tls

# Docker mirrors your host's ./dev-certs folder into the container's /certs folder
cp /certs/ca.crt /etc/samba/tls/ca.crt
cp /certs/domaina.crt /etc/samba/tls/domaina.crt
cp /certs/domaina.key /etc/samba/tls/domaina.key

chmod 600 /etc/samba/tls/domaina.key

# 1. Create base structures
samba-tool ou create "OU=TestingOU"
samba-tool ou create "OU=Groups,OU=TestingOU,DC=samdom,DC=example,DC=com"

# 2. Generate random groups
# We loop 3 times to create 3 random groups
for i in 1 2 3; do
  # Generate a random 4-digit number for uniqueness
  RAND_ID=$(awk 'BEGIN{srand();print int(rand()*9000)+1000}')
  GROUP_NAME="Group-${RAND_ID}"
  
  echo "Creating random group: ${GROUP_NAME}"
  samba-tool group add "${GROUP_NAME}" --groupou="OU=Groups,OU=TestingOU"
done

# 3. Generate random users
# Array simulation for standard shell (POSIX compliant)
FIRST_NAMES="John Jane Alex Emily Michael Sarah"
LAST_NAMES="Smith Doe Taylor Brown Wilson Miller"

# We create 5 random users
for i in 1 2 3 4 5; do
  # Pick a random first name and last name using awk
  F_NAME=$(echo "$FIRST_NAMES" | awk -v r=$(( (RANDOM % 6) + 1 )) '{print $r}')
  L_NAME=$(echo "$LAST_NAMES" | awk -v r=$(( (RANDOM % 6) + 1 )) '{print $r}')
  
  # Generate a unique username and a random number
  RAND_NUM=$(awk 'BEGIN{srand();print int(rand()*90)+10}')
  
  # Convert names to lowercase for the sAMAccountName
  USERNAME=$(echo "${F_NAME}.${L_NAME}${RAND_NUM}" | tr '[:upper:]' '[:lower:]')
  
  echo "Creating random user: ${USERNAME} (${F_NAME} ${L_NAME})"
  
  samba-tool user create "${USERNAME}" "SecurePass${RAND_NUM}!" \
    --userou="OU=TestingOU" \
    --surname="${L_NAME}" \
    --given-name="${F_NAME}"
done

echo "=== Provisioning completed ==="
```

📄 Domain B Setup (./entrypoint_b.d/setup_certs.sh)

```bash
#!/bin/sh
# entrypoint_b.d/setup_certs.sh

mkdir -p /etc/samba/tls

# Copy generated certificates from the mounted project subfolder
cp /certs/ca.crt /etc/samba/tls/ca.crt
cp /certs/domainb.crt /etc/samba/tls/domainb.crt
cp /certs/domainb.key /etc/samba/tls/domainb.key
chmod 600 /etc/samba/tls/domainb.key

# Append configuration to smb.conf securely
cat <<EOF >> /etc/samba/smb.conf
[global]
    tls enabled = yes
    tls keyfile = /etc/samba/tls/domainb.key
    tls certfile = /etc/samba/tls/domainb.crt
    tls cafile = /etc/samba/tls/ca.crt
    tls verify peer = ca_and_name
EOF
echo "Samba container TLS parameters written successfully."
```

📄 Domain C Setup (./entrypoint_c.d/01-provision_c.sh)

Populates Domain C with predictable, stable data structures for reproduction tests.

```bash
#!/bin/sh
echo "=== Starting provisioning of Domain C (External Test Domain) ==="

# entrypoint_a.d/setup_certs.sh
mkdir -p /etc/samba/tls

# Docker mirrors your host's ./dev-certs folder into the container's /certs folder
cp /certs/ca.crt /etc/samba/tls/ca.crt
cp /certs/domaina.crt /etc/samba/tls/domaina.crt
cp /certs/domaina.key /etc/samba/tls/domaina.key

chmod 600 /etc/samba/tls/domaina.key

# 1. Create a base Organizational Unit (OU) for source accounts
samba-tool ou create "OU=TestingOU"

# 2. Create standard test users with fixed data for reproduction
# User 1: John Doe
echo "Creating source user: john.doe"
samba-tool user create john.doe "SourcePass123!" \
  --userou="OU=TestingOU" \
  --surname="Doe" \
  --given-name="John" \
  --mail="john.doe@domainC.local" \
  --job-title="DevOps Engineer" \
  --department="IT-Infrastructure" \
  --telephone-number="+49 123 456789"

# User 2: Jane Smith
echo "Creating source user: jane.smith"
samba-tool user create jane.smith "SourcePass456!" \
  --userou="OU=TestingOU" \
  --surname="Smith" \
  --given-name="Jane" \
  --mail="jane.smith@domainC.local" \
  --job-title="Frontend Developer" \
  --department="Software-Engineering"
```

📄 Domain C Setup (./entrypoint_c.d/setup_certs.sh)

```bash
#!/bin/sh
# entrypoint_c.d/setup_certs.sh

mkdir -p /etc/samba/tls

# Copy generated certificates from the mounted project subfolder
cp /certs/ca.crt /etc/samba/tls/ca.crt
cp /certs/domainc.crt /etc/samba/tls/domainc.crt
cp /certs/domainc.key /etc/samba/tls/domainc.key
chmod 600 /etc/samba/tls/domainc.key

# Append configuration to smb.conf securely
cat <<EOF >> /etc/samba/smb.conf
[global]
    tls enabled = yes
    tls keyfile = /etc/samba/tls/domainc.key
    tls certfile = /etc/samba/tls/domainc.crt
    tls cafile = /etc/samba/tls/ca.crt
    tls verify peer = ca_and_name
EOF
echo "Samba container TLS parameters written successfully."
```

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

# 5. some helpers to check the AD content
docker exec -it fake_ad_domain_a samba-tool group list
docker exec -it fake_ad_domain_a samba-tool user list
docker exec -it fake_ad_domain_a samba-tool computer list
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
ENVIRONMENT=development

# this is for legal hold testing - we will use a custom attribute to mark accounts that are on legal hold, and then ensure that our API correctly identifies and handles these accounts.
# Those accounts should be excluded from deletion, and the API should return appropriate information when queried about them.
# This is limited to user objects, and we will use a custom attributes to indicate legal hold status.
# This is a comma-separated list of attributes that we will check for legal hold status. In this case, we will check both "description" and "comment" attributes, as well as "extensionAttribute5" (only exists in a real Active Directory environment but not samba) for flexibility in testing.
LEGAL_HOLD_ATTRIBUTE_NAME="description,comment,extensionAttribute5" 

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

# === PROD DOMAIN EXAMPLE ===
DOMAIN_P_NAME=prod.example.com
DOMAIN_P_SERVER=ldaps://localhost:4636
DOMAIN_P_USER=CN=Administrator,CN=Users,DC=prod,DC=example,DC=com
DOMAIN_P_PASSWORD=SecretC123!
DOMAIN_P_SEARCH_BASE=DC=prod,DC=example,DC=com
DOMAIN_P_CA_CERT_PATH=/path/to/ca_cert.crt
DOMAIN_P_CLIENT_CERT_PATH=/path/to/client_cert.crt
DOMAIN_P_CLIENT_KEY_PATH=/path/to/client_key.key
# === ...
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
| POST   /user/disable                   | Disables a user account                                                |
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
| POST   /computer/enable                | Enables a new computer object in LDAP.                                 |
| POST   /computer/disable               | Disables a new computer object in LDAP.                                |
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

### 8. Disable User account
```bash
curl -X POST http://localhost:3000/api/user/disable \
     -H "X-API-Key: your_api_key_here" \
     -H "Content-Type: application/json" \
     -d '{
        "domain_name": "samdom.example.com",
        "sam_account_name": "m.mustermann"
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
    "ou_dn": "OU=TestingOU,DC=samdom,DC=example,DC=com",
    "scope": "global"
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

### 3. Disable Computer from Specific Forest
```bash
curl -X POST http://localhost:3000/api/computer/disable \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "://example.com",
    "computer_name": "DESKTOP-01"
  }'
```

### 4. Enable Computer from Specific Forest
```bash
curl -X POST http://localhost:3000/api/computer/enable \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "://example.com",
    "computer_name": "DESKTOP-01"
  }'
```