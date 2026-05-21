#!/bin/sh
echo "=== Starting provisioning of Domain A (Source) ==="

# 1. Create a base Organizational Unit (OU) for source accounts
samba-tool ou create "OU=TestingOU"

# 2. Create standard test users with fixed data for reproduction
# User 1: John Doe
echo "Creating source user: john.doe"
samba-tool user create john.doe "SourcePass123!" \
  --userou="OU=TestingOU" \
  --surname="Doe" \
  --given-name="John" \
  --mail="john.doe@domainA.local" \
  --job-title="DevOps Engineer" \
  --department="IT-Infrastructure" \
  --telephone-number="+49 123 456789"

# User 2: Jane Smith
echo "Creating source user: jane.smith"
samba-tool user create jane.smith "SourcePass456!" \
  --userou="OU=TestingOU" \
  --surname="Smith" \
  --given-name="Jane" \
  --mail="jane.smith@domainA.local" \
  --job-title="Frontend Developer" \
  --department="Software-Engineering"

echo "=== Domain A Provisioning completed ==="
