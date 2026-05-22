## Installation setup

# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Check if it's running
sudo systemctl status postgresql

# Enable it to start on boot
sudo systemctl enable postgresql


# setting up the venv
cd /path/to/your/project

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt


## Database Migration

# Create the user with a password
sudo -u postgres psql -c "CREATE USER pharmacy_user WITH PASSWORD 'password';"

# Verify user was created
sudo -u postgres psql -c "\du"

# Drop database if it exists (clean slate)
sudo -u postgres psql -c "DROP DATABASE IF EXISTS pharmacy_db;"

# Create database with pharmacy_user as owner
sudo -u postgres psql -c "CREATE DATABASE pharmacy_db OWNER pharmacy_user;"

# Grant all privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pharmacy_db TO pharmacy_user;"

# Verify database was created
sudo -u postgres psql -c "\l" | grep pharmacy

# Navigate to your project or backup location
cd /path/to/eapts_backend

# Restore the backup (as postgres user)
sudo -u postgres psql -d pharmacy_db < /path/to/pharmacy_backup_20250407.sql


# Check if tables are there
sudo -u postgres psql -d pharmacy_db -c "\dt"

# Check migration history
sudo -u postgres psql -d pharmacy_db -c "SELECT * FROM django_migrations;" | head -15

# Check if data exists (example with users)
sudo -u postgres psql -d pharmacy_db -c "SELECT COUNT(*) FROM person_user;"



# Activate venv
source venv/bin/activate

# Run migrations (only new ones)
python manage.py migrate

# Verify all migrations are applied
python manage.py showmigrations
# All should show [X]