#!/bin/bash

# CiteCheck Setup Script
# Automates the initial setup process

set -e  # Exit on any error

echo "========================================="
echo "CiteCheck Setup Script"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version
echo ""

# Create virtual environment
echo "Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Check PostgreSQL
echo "Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "✓ PostgreSQL is installed"
    psql --version
else
    echo "⚠ PostgreSQL is not installed"
    echo "Please install PostgreSQL:"
    echo "  sudo apt update && sudo apt install postgresql postgresql-contrib"
    exit 1
fi
echo ""

# Database setup
echo "========================================="
echo "Database Setup"
echo "========================================="
echo ""

# Check if database already exists
if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw citecheck; then
    echo "✓ Database 'citecheck' already exists"
    echo ""
else
    echo "Would you like to set up the database now? (y/n)"
    read -r setup_db

    if [ "$setup_db" = "y" ] || [ "$setup_db" = "Y" ]; then
        echo ""
        echo "Setting up PostgreSQL database..."
        echo "(This uses sudo to run as the postgres user)"
        echo ""

        # Create user and database using sudo (works on fresh installs)
        sudo -u postgres psql <<EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'citecheck_user') THEN
        CREATE USER citecheck_user WITH PASSWORD 'citecheck_password';
    END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE citecheck OWNER citecheck_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'citecheck')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE citecheck TO citecheck_user;
EOF

        if [ $? -eq 0 ]; then
            echo ""
            echo "✓ Database 'citecheck' created successfully"
            echo "✓ User 'citecheck_user' created with password 'citecheck_password'"
        else
            echo ""
            echo "⚠ Database setup failed. You may need to set it up manually:"
            echo "   sudo -u postgres psql"
            echo "   CREATE USER citecheck_user WITH PASSWORD 'citecheck_password';"
            echo "   CREATE DATABASE citecheck OWNER citecheck_user;"
            echo "   GRANT ALL PRIVILEGES ON DATABASE citecheck TO citecheck_user;"
            echo "   \\q"
        fi
        echo ""
    fi
fi

# Configure .env file
echo "========================================="
echo "Environment Configuration"
echo "========================================="
echo ""

if [ -f ".env" ]; then
    echo "⚠ .env file already exists"
    echo "Would you like to reconfigure it? (y/n)"
    read -r reconfigure
    if [ "$reconfigure" != "y" ] && [ "$reconfigure" != "Y" ]; then
        echo "✓ Keeping existing .env file"
        echo ""
    else
        rm .env
    fi
fi

if [ ! -f ".env" ]; then
    echo "Let's configure your environment..."
    echo ""

    # Generate secure SECRET_KEY
    echo "Generating secure SECRET_KEY..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "✓ SECRET_KEY generated"
    echo ""

    # Prompt for Fastmail app password
    echo "Fastmail Configuration"
    echo "----------------------"
    echo "To get a Fastmail app password:"
    echo "  1. Login to Fastmail"
    echo "  2. Go to Settings → Password & Security"
    echo "  3. Click 'New App Password'"
    echo "  4. Name it 'CiteCheck' and copy the password"
    echo ""
    echo "Enter your Fastmail app password (or press Enter to skip for now):"
    read -r -s SMTP_PASSWORD
    echo ""

    if [ -z "$SMTP_PASSWORD" ]; then
        SMTP_PASSWORD="your-fastmail-app-password-here"
        echo "⚠ You'll need to add the password to .env later"
    else
        echo "✓ Password saved"
    fi
    echo ""

    # Optional: Frontend URL
    echo "Frontend URL (press Enter for default: https://iacls.org/citecheck):"
    read -r FRONTEND_URL
    if [ -z "$FRONTEND_URL" ]; then
        FRONTEND_URL="https://iacls.org/citecheck"
    fi
    echo ""

    # Create .env file with configured values
    echo "Creating .env file..."
    cat > .env << EOF
DATABASE_URL=postgresql://citecheck_user:citecheck_password@localhost:5432/citecheck
SECRET_KEY=${SECRET_KEY}
SMTP_HOST=smtp.fastmail.com
SMTP_PORT=587
SMTP_USER=markwbennett@fastmail.com
SMTP_PASSWORD=${SMTP_PASSWORD}
FROM_EMAIL=citecheck@iacls.org
FRONTEND_URL=${FRONTEND_URL}
EOF
    echo "✓ .env file created with your configuration"
    echo ""
fi

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""

# Check if password was set
if grep -q "your-fastmail-app-password-here" .env 2>/dev/null; then
    echo "⚠ REMINDER: Add your Fastmail app password to .env before using email features"
    echo ""
fi

echo "Next steps:"
echo ""
echo "1. Test the core functionality (no email needed):"
echo "   source venv/bin/activate"
echo "   python test_processor.py 'Sample_Briefs/Cause No. 01-24-00757-CR; Appellant'\''s Opening Brief FILED.pdf'"
echo ""
echo "2. Run the API server:"
echo "   source venv/bin/activate"
echo "   cd backend"
echo "   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "3. Access the API documentation:"
echo "   http://localhost:8000/docs"
echo ""
echo "4. View your configuration:"
echo "   cat .env"
echo ""
echo "Happy analyzing!"
echo ""
