"""
UDLMS Setup and Installation Script
Automates the setup process for the UDLMS application
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")

































def check_python_version():
    """Check if Python version is 3.8 or higher"""
    print_info("Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print_success(f"Python {version.major}.{version.minor}.{version.micro} detected")
        return True
    else:
        print_error(f"Python 3.8+ required, but {version.major}.{version.minor} found")
        return False

def create_virtual_environment():
    """Create virtual environment"""
    print_info("Creating virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print_success("Virtual environment created")
        return True
    except Exception as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False

def get_pip_command():
    """Get the correct pip command based on OS"""
    if sys.platform == "win32":
        return os.path.join("venv", "Scripts", "pip.exe")
    else:
        return os.path.join("venv", "bin", "pip")

def install_dependencies():
    """Install Python dependencies"""
    print_info("Installing Python dependencies...")
    pip_cmd = get_pip_command()
    
    try:
        # Upgrade pip
        subprocess.run([pip_cmd, "install", "--upgrade", "pip"], check=True)
        
        # Install requirements
        if os.path.exists("requirements.txt"):
            subprocess.run([pip_cmd, "install", "-r", "requirements.txt"], check=True)
            print_success("Dependencies installed successfully")
            return True
        else:
            print_error("requirements.txt not found")
            return False
    except Exception as e:
        print_error(f"Failed to install dependencies: {e}")
        return False

def create_env_file():
    """Create .env file from template"""
    print_info("Creating environment configuration...")
    
    if os.path.exists(".env"):
        print_warning(".env file already exists. Skipping.")
        return True
    
    if os.path.exists(".env.example"):
        try:
            shutil.copy(".env.example", ".env")
            print_success(".env file created from template")
            print_warning("Please edit .env file with your database credentials!")
            return True
        except Exception as e:
            print_error(f"Failed to create .env file: {e}")
            return False
    else:
        print_error(".env.example not found")
        return False

def create_directories():
    """Create necessary directories"""
    print_info("Creating necessary directories...")
    
    directories = ["logs", "uploads", "reports", "backups", "static/images"]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            print_success(f"Created {directory}/")
        except Exception as e:
            print_error(f"Failed to create {directory}/: {e}")
            return False
    
    return True

def create_placeholder_logo():
    """Create a placeholder logo if not exists"""
    logo_path = os.path.join("static", "images", "logo.jpg")
    
    if not os.path.exists(logo_path):
        print_info("Creating placeholder logo...")
        # Create an SVG placeholder
        svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
  <rect fill="#0c2a78" width="200" height="200" rx="100"/>
  <text x="50%" y="50%" font-size="80" font-weight="bold" text-anchor="middle" dy=".3em" fill="#fff">UM</text>
</svg>'''
        
        try:
            with open(logo_path.replace('.jpg', '.svg'), 'w') as f:
                f.write(svg_content)
            print_success("Placeholder logo created")
        except Exception as e:
            print_warning(f"Could not create placeholder logo: {e}")

def check_sql_server():
    """Check if SQL Server is accessible"""
    print_info("Checking SQL Server connectivity...")
    
    try:
        import pyodbc
        # This will be tested with actual connection in the app
        drivers = pyodbc.drivers()
        if 'ODBC Driver 17 for SQL Server' in drivers:
            print_success("ODBC Driver 17 for SQL Server found")
            return True
        else:
            print_warning("ODBC Driver 17 for SQL Server not found")
            print_info("Available drivers: " + ", ".join(drivers))
            print_info("Please install ODBC Driver 17 for SQL Server")
            return False
    except ImportError:
        print_warning("pyodbc not installed yet. Will be installed with dependencies.")
        return True

def print_next_steps():
    """Print next steps for the user"""
    print_header("Setup Complete! Next Steps")
    
    print(f"{Colors.BOLD}1. Configure Database:{Colors.ENDC}")
    print("   - Edit .env file with your SQL Server credentials")
    print("   - Run database initialization:")
    print(f"     {Colors.OKCYAN}sqlcmd -S localhost -d master -i database_init.sql{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}2. Activate Virtual Environment:{Colors.ENDC}")
    if sys.platform == "win32":
        print(f"     {Colors.OKCYAN}venv\\Scripts\\activate{Colors.ENDC}")
    else:
        print(f"     {Colors.OKCYAN}source venv/bin/activate{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}3. Run the Application:{Colors.ENDC}")
    print(f"     {Colors.OKCYAN}python App.py{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}4. Access the Application:{Colors.ENDC}")
    print(f"     {Colors.OKCYAN}http://127.0.0.1:5000{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}5. Default Login Credentials:{Colors.ENDC}")
    print(f"     Username: {Colors.OKGREEN}admin{Colors.ENDC}")
    print(f"     Password: {Colors.OKGREEN}admin123{Colors.ENDC}")
    print(f"     {Colors.WARNING}⚠ Change password after first login!{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}For help, see README.md{Colors.ENDC}\n")

def main():
    """Main setup function"""
    print_header("UDLMS Setup and Installation")
    
    print_info("Starting setup process...")
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Check SQL Server
    check_sql_server()
    
    # Create virtual environment
    if not os.path.exists("venv"):
        if not create_virtual_environment():
            sys.exit(1)
    else:
        print_warning("Virtual environment already exists. Skipping creation.")
    
    # Install dependencies
    if not install_dependencies():
        print_error("Setup failed during dependency installation")
        sys.exit(1)
    
    # Create .env file
    if not create_env_file():
        print_warning("Please create .env file manually")
    
    # Create directories
    if not create_directories():
        print_error("Setup failed during directory creation")
        sys.exit(1)
    
    # Create placeholder logo
    create_placeholder_logo()
    
    # Print next steps
    print_next_steps()
    
    print_success("Setup completed successfully!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Setup interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
