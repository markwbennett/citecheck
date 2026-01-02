"""
Database initialization script.
Creates the PostgreSQL database and user.

NOTE: The setup.sh script handles this automatically.
      This script is for manual database setup only.
"""
import subprocess
import sys


def create_database():
    """Create the citecheck database and user using sudo."""

    DB_NAME = "citecheck"
    DB_USER = "citecheck_user"
    DB_PASSWORD = "citecheck_password"

    sql_commands = f"""
-- Create user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{DB_USER}') THEN
        CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';
    END IF;
END
$$;

-- Create database if not exists
SELECT 'CREATE DATABASE {DB_NAME} OWNER {DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{DB_NAME}')\\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};
"""

    print("Setting up PostgreSQL database...")
    print("(This uses sudo to run as the postgres user)")
    print("")

    try:
        # Run psql as postgres user via sudo
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql'],
            input=sql_commands,
            text=True,
            capture_output=True
        )

        if result.returncode == 0:
            print("✓ Database setup completed successfully!")
            print(f"")
            print(f"  Database: {DB_NAME}")
            print(f"  User: {DB_USER}")
            print(f"  Password: {DB_PASSWORD}")
            print(f"")
            print("You can now run the FastAPI application.")
        else:
            print(f"⚠ Database setup encountered issues:")
            print(result.stderr)
            print("")
            print("Try running these commands manually:")
            print("  sudo -u postgres psql")
            print(f"  CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';")
            print(f"  CREATE DATABASE {DB_NAME} OWNER {DB_USER};")
            print(f"  GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};")
            print("  \\q")

    except FileNotFoundError:
        print("Error: sudo or psql not found.")
        print("Make sure PostgreSQL is installed:")
        print("  sudo apt update && sudo apt install postgresql postgresql-contrib")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    create_database()
