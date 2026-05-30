#!/bin/sh
echo "=== Starting provisioning of Domain A (Source) ==="

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
