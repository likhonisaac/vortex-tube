#!/usr/bin/env python3

import os
import subprocess
import socket
import json
from contextlib import contextmanager

# Constants
DOMAIN = "likhown.dev"
API_PORT = 5000
LOCAL_PORT = 8080
DEBUGGER_PORT = 4300
TUNNEL_PORT = 4300
APACHE_DOC_ROOT = "/var/www/html"
AVAILABLE_REGIONS = ["USA", "Europe", "Asia"]

# Helper functions
@contextmanager
def temp_chdir(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)

def run_command(command):
    return subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

def get_public_ip():
    try:
        return socket.gethostbyname(socket.getfqdn())
    except socket.gaierror:
        return "Unable to determine public IP"

def setup_apache():
    with open(APACHE_DOC_ROOT + "/index.html", "w") as f:
        f.write("<h1>Welcome to Likhown Tunnel!</h1>")
    run_command(f"chown -R www-data:www-data {APACHE_DOC_ROOT}")
    run_command("systemctl enable apache2 && systemctl start apache2")

def setup_nginx():
    nginx_conf = f"""
server {{
    listen 80;
    server_name {DOMAIN};

    location / {{
        proxy_pass http://localhost:{LOCAL_PORT};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    with open("/etc/nginx/conf.d/likhown.conf", "w") as f:
        f.write(nginx_conf)
    run_command("systemctl enable nginx && systemctl start nginx")

def setup_subdomain_api():
    api_script = f"""
#!/bin/bash
API_PORT={API_PORT}
DOMAIN="{DOMAIN}"

while true; do
  echo -e "HTTP/1.1 200 OK\\nContent-Type: application/json\\n" | nc -l -p $API_PORT -q 1 | (
    read request
    if [[ "$request" == *"GET /create"* ]]; then
      subdomain=$(echo "$request" | grep -oP '(?<=subdomain=)[^& ]+')
      screen -dmS tunnel_$subdomain ssh -R {TUNNEL_PORT}:localhost:{LOCAL_PORT} localhost
      echo {{'"message": "Subdomain $subdomain created successfully", "subdomain_url": "http://$subdomain.$DOMAIN"'}}
    elif [[ "$request" == *"GET /delete"* ]]; then
      subdomain=$(echo "$request" | grep -oP '(?<=subdomain=)[^& ]+')
      screen -S tunnel_$subdomain -X quit
      echo {{'"message": "Subdomain $subdomain deleted successfully"'}}
    else
      echo {{'"error": "Invalid endpoint. Use /create or /delete"'}}
    fi
  )
done
"""
    with open("/usr/local/bin/subdomain_api.sh", "w") as f:
        f.write(api_script)
    run_command("chmod +x /usr/local/bin/subdomain_api.sh")
    run_command("screen -dmS subdomain_api /usr/local/bin/subdomain_api.sh")

def setup_tunnel_options():
    print("\nAdvanced Tunnel Configuration Options:")
    print("1. HTTP(S)")
    print("2. TCP")
    print("3. TLS")
    print("4. UDP")
    tunnel_type = input("Choose a tunnel type (default is HTTP): ") or "HTTP"
    region = input("Choose region (USA/Europe/Asia, default is USA): ") or "USA"
    password_protect = input("Enable password protection (y/n, default is n): ").lower() == 'y'
    keep_alive = input("Enable keep-alive (y/n, default is y): ").lower() != 'n'
    auto_reconnect = input("Enable auto-reconnect (y/n, default is y): ").lower() != 'n'

    config = {
        "tunnel_type": tunnel_type,
        "region": region if region in AVAILABLE_REGIONS else "USA",
        "password_protect": password_protect,
        "keep_alive": keep_alive,
        "auto_reconnect": auto_reconnect
    }
    with open("/usr/local/bin/tunnel_config.json", "w") as f:
        json.dump(config, f, indent=4)

def setup_ssh_tunnels():
    run_command(f"screen -dmS main_tunnel ssh -R {TUNNEL_PORT}:localhost:{LOCAL_PORT} localhost")
    run_command(f"screen -dmS debugger_tunnel ssh -R {DEBUGGER_PORT}:localhost:{DEBUGGER_PORT} localhost")

def print_setup_info():
    public_ip = get_public_ip()
    print("\n===================================")
    print("Likhown Tunnel Setup Completed!")
    print(f"Access server via URLs:")
    print(f" - Local URL: http://localhost:{LOCAL_PORT}")
    print(f" - Public URL: http://{DOMAIN}")
    print(f" - API: http://localhost:{API_PORT}")
    print(f" - Web Debugger: http://localhost:{DEBUGGER_PORT}")
    print("\nConfigure Cloudflare DNS:")
    print("  Type: A")
    print("  Name:", DOMAIN)
    print("  Content:", public_ip)
    print("===================================")

def main():
    if os.geteuid() != 0:
        print("Please run as root.")
        exit(1)
    run_command("apt update -y")
    run_command("apt install -y apache2 nginx openssh-server screen netcat")

    setup_apache()
    setup_nginx()
    setup_subdomain_api()
    setup_tunnel_options()
    setup_ssh_tunnels()
    print_setup_info()

if __name__ == "__main__":
    main()
