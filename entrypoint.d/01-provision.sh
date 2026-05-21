#!/bin/sh
echo "=== Starting provisioning of AD test data ==="

# 1. Create a new Organizational Unit (OU) for tests
samba-tool ou create "OU=TestingOU"

# Create a nested OU for groups under the testing OU
samba-tool ou create "OU=Groups,OU=TestingOU,DC=samdom,DC=example,DC=com"
samba-tool ou create "OU=Computers,OU=TestingOU,DC=samdom,DC=example,DC=com"

# 2. Create the test user (password must meet complexity requirements)
samba-tool user create max.mustermann "SecurePass123!" \
  --userou="OU=TestingOU" \
  --surname="Mustermann" \
  --given-name="Max"

# 3. Create the Marketing group
samba-tool group add Marketing-Gruppe \
  --groupou="OU=TestingOU"

echo "=== Provisioning completed ==="
