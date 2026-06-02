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
