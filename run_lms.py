# run_lms.py - UDLMS Launcher for EXE
# This file launches the Flask application when running as EXE

import os
import sys
from pathlib import Path

# Determine if running as EXE or script
if getattr(sys, 'frozen', False):
    # Running as compiled EXE
    BASE_DIR = Path(sys._MEIPASS)
    print("🚀 Running as executable")
else:
    # Running as Python script
    BASE_DIR = Path(__file__).parent
    print("🐍 Running as Python script")

# Set Flask template and static folders
os.environ['FLASK_TEMPLATE_FOLDER'] = str(BASE_DIR / 'templates')
os.environ['FLASK_STATIC_FOLDER'] = str(BASE_DIR / 'static')

# Import the Flask app
try:
    from App import app
except ImportError as e:
    print(f"❌ Error importing App.py: {e}")
    print("\n💡 Make sure App.py exists in the same directory")
    input("Press Enter to exit...")
    sys.exit(1)

def open_browser():
    """Open browser automatically after Flask starts"""
    import webbrowser
    import time
    time.sleep(2)  # Wait for Flask to start
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    # Configuration
    HOST = '127.0.0.1'
    PORT = 5000
    VERSION = '1.0.0'
    
    print("\n" + "=" * 70)
    print("  🎓 UDLMS - University Department Loan Management System")
    print("=" * 70)
    print(f"  📌 Version: {VERSION}")
    print(f"  🌐 Server: http://{HOST}:{PORT}")
    print(f"  📂 Base Directory: {BASE_DIR}")
    print("=" * 70)
    print("  🔄 Starting server...")
    print("  🌐 Browser will open automatically...")
    print("  ⚠️  Press Ctrl+C to stop the server")
    print("=" * 70 + "\n")
    
    # Open browser in separate thread
    import threading
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Run Flask application
    try:
        app.run(
            host=HOST,
            port=PORT,
            debug=False,
            use_reloader=False
        )
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        print("\n💡 Common issues:")
        print("   1. Port 5000 already in use")
        print("   2. Database connection failed")
        print("   3. Missing dependencies")
        input("\nPress Enter to exit...")
        sys.exit(1)
