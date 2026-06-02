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
