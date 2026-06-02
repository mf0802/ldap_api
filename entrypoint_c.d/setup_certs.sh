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
