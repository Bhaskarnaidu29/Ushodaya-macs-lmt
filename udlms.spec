# -*- mode: python ; coding: utf-8 -*-
# =============================================================
#  UDLMS - PyInstaller Spec File
#  Ushodaya MACS Ltd Loan Management System
#  Generated for PyInstaller 6.x
#
#  Place this file in the SAME folder as App.py and run_lms.py
#  Then build with:  pyinstaller udlms.spec --clean --noconfirm
#  Or just run:      build_exe.bat
# =============================================================

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# ------------------------------------------------------------------
# PROJECT ROOT — resolved from the spec file's own location.
# SPECPATH is set automatically by PyInstaller to the folder
# containing this .spec file, so paths always work regardless
# of what drive or folder name you use.
# ------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(SPECPATH)

TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')
STATIC_DIR    = os.path.join(PROJECT_ROOT, 'static')
ENV_FILE      = os.path.join(PROJECT_ROOT, '.env')
SQL_FILE      = os.path.join(PROJECT_ROOT, 'udlms.sql')

# ------------------------------------------------------------------
# Hidden imports — Flask internals + every UDLMS blueprint
# ------------------------------------------------------------------
hidden_imports = [
    # Flask & extensions
    'flask', 'flask.cli', 'flask.json',
    'jinja2', 'jinja2.ext',
    'werkzeug', 'werkzeug.security', 'werkzeug.routing',
    'werkzeug.middleware.proxy_fix',
    'click', 'itsdangerous',
    'dotenv', 'python_dotenv',

    # Database
    'pyodbc',

    # Data processing
    'pandas', 'pandas.io.formats.style',
    'numpy',
    'openpyxl', 'openpyxl.styles',

    # PDF generation
    'reportlab',
    'reportlab.lib', 'reportlab.lib.pagesizes',
    'reportlab.lib.styles', 'reportlab.lib.units',
    'reportlab.platypus',
    'reportlab.pdfgen', 'reportlab.pdfgen.canvas',

    # Standard library (occasionally missed by PyInstaller)
    'logging', 'logging.handlers',
    'datetime', 'decimal', 'json',
    'os', 'sys', 'threading', 'webbrowser', 'pathlib',

    # UDLMS application modules (all blueprints)
    'App', 'db', 'login', 'permissions',
    'center', 'members', 'employee', 'product',
    'loans', 'savings', 'loanapplication',
    'recposting', 'rec_posting_memberwise',
    'recurringdeposit', 'rdcollections',
    'settings', 'dayend',
    'fixeddeposit', 'fdcollections',
    'reports', 'advance', 'loanrec',
    'security_deposit', 'help',
    'collection_reports', 'user_management',
    'prepaid_types_route', 'your_pdf_generators',
]

hidden_imports += collect_submodules('flask')
hidden_imports += collect_submodules('jinja2')
hidden_imports += collect_submodules('werkzeug')
hidden_imports += collect_submodules('reportlab')

# ------------------------------------------------------------------
# Data files — templates, static, optional .env and SQL schema
# ------------------------------------------------------------------
datas = []

# templates\ folder (HTML files)
if os.path.isdir(TEMPLATES_DIR):
    datas.append((TEMPLATES_DIR, 'templates'))
else:
    print(f"[WARN] templates folder not found at: {TEMPLATES_DIR}")
    print("       The build will continue but the app will not render pages.")

# static\ folder (CSS, JS, images)
if os.path.isdir(STATIC_DIR):
    datas.append((STATIC_DIR, 'static'))
else:
    print(f"[WARN] static folder not found at: {STATIC_DIR}")

# .env file (database credentials)
if os.path.isfile(ENV_FILE):
    datas.append((ENV_FILE, '.'))

# SQL schema file
if os.path.isfile(SQL_FILE):
    datas.append((SQL_FILE, '.'))

# Jinja2 and ReportLab internal data files (fonts, etc.)
datas += collect_data_files('jinja2')
datas += collect_data_files('reportlab')

# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------
a = Analysis(
    [os.path.join(PROJECT_ROOT, 'run_lms.py')],   # entry point
    pathex=[PROJECT_ROOT],                          # so all .py modules are found
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'sklearn',
        'tkinter', 'PyQt5', 'PyQt6', 'wx',
        'notebook', 'IPython', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ------------------------------------------------------------------
# PYZ archive
# ------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ------------------------------------------------------------------
# EXE  (single-file, no console window)
# ------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='UDLMS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # windowed — no black CMD window on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Uncomment the line below and point to a .ico file to set the EXE icon:
    # icon=os.path.join(PROJECT_ROOT, 'static', 'images', 'logo.ico'),
)
