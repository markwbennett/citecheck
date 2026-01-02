#!/bin/bash

# CiteCheck Server Setup Script
# Run this once to set up the production server

set -e

echo "========================================="
echo "CiteCheck Server Setup"
echo "========================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo ./setup-server.sh"
    exit 1
fi

PROJECT_DIR="/home/mb/github/citecheck"
SCRIPTS_DIR="$PROJECT_DIR/scripts"

# Create log directory
echo "Creating log directory..."
mkdir -p /var/log/citecheck
chown mb:mb /var/log/citecheck
echo "✓ Log directory created"

# Create uploads directory
echo "Creating uploads directory..."
mkdir -p "$PROJECT_DIR/uploads/annotated"
chown -R mb:mb "$PROJECT_DIR/uploads"
echo "✓ Uploads directory created"

# Install nginx if not present
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt update
    apt install -y nginx
    echo "✓ nginx installed"
else
    echo "✓ nginx already installed"
fi

# Install certbot for SSL
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    apt install -y certbot python3-certbot-nginx
    echo "✓ certbot installed"
else
    echo "✓ certbot already installed"
fi

# Copy systemd service
echo "Installing systemd service..."
cp "$SCRIPTS_DIR/citecheck.service" /etc/systemd/system/
systemctl daemon-reload
echo "✓ systemd service installed"

# Copy nginx config
echo "Installing nginx configuration..."
cp "$SCRIPTS_DIR/citecheck.nginx.conf" /etc/nginx/sites-available/citecheck

# Create symlink if it doesn't exist
if [ ! -L /etc/nginx/sites-enabled/citecheck ]; then
    ln -s /etc/nginx/sites-available/citecheck /etc/nginx/sites-enabled/
fi
echo "✓ nginx configuration installed"

# Test nginx configuration
echo "Testing nginx configuration..."
nginx -t
echo "✓ nginx configuration valid"

# Set up SSL with certbot
echo ""
echo "Setting up SSL certificate..."
echo "Note: DNS for citecheck.iacls.org must point to this server"
echo ""

# Check if certificate already exists
if [ -d "/etc/letsencrypt/live/citecheck.iacls.org" ]; then
    echo "✓ SSL certificate already exists"
else
    certbot --nginx -d citecheck.iacls.org --non-interactive --agree-tos --email markwbennett@fastmail.com --redirect
    if [ $? -eq 0 ]; then
        echo "✓ SSL certificate installed"
    else
        echo "⚠ SSL setup failed. You can retry manually:"
        echo "   sudo certbot --nginx -d citecheck.iacls.org"
    fi
fi

# Enable and start services
echo ""
echo "Starting services..."
systemctl enable citecheck
systemctl start citecheck
systemctl reload nginx
echo "✓ Services started"

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "CiteCheck is now running at: https://citecheck.iacls.org"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status citecheck    # Check API status"
echo "  sudo systemctl restart citecheck   # Restart API"
echo "  tail -f /var/log/citecheck/error.log      # API logs"
echo "  tail -f /var/log/nginx/citecheck.error.log # nginx logs"
echo ""
