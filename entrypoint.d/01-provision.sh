#!/bin/sh
echo "=== Starte Provisionierung der AD Testdaten ==="

# 1. Eine neue Organisational Unit (OU) für Tests anlegen
samba-tool ou create "OU=TestingOU"

samba-tool ou create "OU=Groups,OU=TestingOU,DC=samdom,DC=example,DC=com"

# 2. Den Testbenutzer anlegen (Passwort muss Komplexitätsregeln erfüllen)
samba-tool user create max.mustermann "SecurePass123!" \
  --userou="OU=TestingOU" \
  --surname="Mustermann" \
  --given-name="Max"

# 3. Die Marketing-Gruppe anlegen
samba-tool group add Marketing-Gruppe \
  --groupou="OU=TestingOU"

echo "=== Provisionierung abgeschlossen ==="
