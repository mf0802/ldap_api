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
