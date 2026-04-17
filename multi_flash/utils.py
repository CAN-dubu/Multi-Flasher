import sys
import subprocess
import re

def ensure_package(pkg, import_name=None):
    try:
        __import__(import_name or pkg)
    except ImportError:
        print(f"[INFO] {pkg} not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        print(f"[OK] {pkg} installed.")
        __import__(import_name or pkg)

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def clean_ansi(text):
    return ANSI_ESCAPE.sub('', text)
