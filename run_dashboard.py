#!/usr/bin/env python3
"""Run the dashboard with proper configuration."""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Run uvicorn
os.system("uvicorn backend.dashboard.main:app --reload --port 8080 --host 127.0.0.1")
