#!/usr/bin/env python3
"""Administrative commands for the separate owner authentication database."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web.settings')
from django.core.management import execute_from_command_line
if __name__ == '__main__':
    execute_from_command_line(sys.argv)
