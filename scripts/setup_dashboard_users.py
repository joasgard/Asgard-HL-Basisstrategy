#!/usr/bin/env python3
"""
Setup script for dashboard users.
Creates bcrypt-hashed passwords for dashboard authentication.

Usage:
    # Interactive mode
    python scripts/setup_dashboard_users.py
    
    # Command line mode
    python scripts/setup_dashboard_users.py --admin mypassword --operator oppass --viewer viewpass
    
    # Save to file
    python scripts/setup_dashboard_users.py --output secrets/dashboard_users.json
"""

import argparse
import json
import getpass
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.dashboard.auth import session_manager


def create_user(username: str, password: str, role: str) -> dict:
    """Create a user dict with hashed password."""
    return {
        "hash": get_password_hash(password),
        "role": role
    }


def interactive_setup():
    """Interactive user setup."""
    print("=" * 60)
    print("Dashboard User Setup")
    print("=" * 60)
    print()
    
    users = {}
    
    # Admin user (required)
    print("Admin user (required):")
    admin_pw = getpass.getpass("Enter admin password: ")
    admin_pw_confirm = getpass.getpass("Confirm admin password: ")
    
    if admin_pw != admin_pw_confirm:
        print("ERROR: Passwords do not match!")
        sys.exit(1)
    
    if len(admin_pw) < 12:
        print("WARNING: Password is less than 12 characters. Consider using a stronger password.")
    
    users["admin"] = create_user("admin", admin_pw, "admin")
    print("✓ Admin user created")
    print()
    
    # Operator user (optional)
    print("Operator user (optional, press Enter to skip):")
    op_pw = getpass.getpass("Enter operator password: ")
    if op_pw:
        op_pw_confirm = getpass.getpass("Confirm operator password: ")
        if op_pw != op_pw_confirm:
            print("ERROR: Passwords do not match!")
            sys.exit(1)
        users["operator"] = create_user("operator", op_pw, "operator")
        print("✓ Operator user created")
    else:
        print("- Operator user skipped")
    print()
    
    # Viewer user (optional)
    print("Viewer user (optional, press Enter to skip):")
    viewer_pw = getpass.getpass("Enter viewer password: ")
    if viewer_pw:
        viewer_pw_confirm = getpass.getpass("Confirm viewer password: ")
        if viewer_pw != viewer_pw_confirm:
            print("ERROR: Passwords do not match!")
            sys.exit(1)
        users["viewer"] = create_user("viewer", viewer_pw, "viewer")
        print("✓ Viewer user created")
    else:
        print("- Viewer user skipped")
    print()
    
    return users


def main():
    parser = argparse.ArgumentParser(
        description="Setup dashboard users with secure password hashing"
    )
    parser.add_argument(
        "--admin",
        help="Admin password (use interactive mode for security)"
    )
    parser.add_argument(
        "--operator",
        help="Operator password"
    )
    parser.add_argument(
        "--viewer",
        help="Viewer password"
    )
    parser.add_argument(
        "--output", "-o",
        default="secrets/dashboard_users.json",
        help="Output file path (default: secrets/dashboard_users.json)"
    )
    parser.add_argument(
        "--env",
        action="store_true",
        help="Output as environment variable format instead of file"
    )
    
    args = parser.parse_args()
    
    # Check if any passwords provided via command line
    if args.admin or args.operator or args.viewer:
        # Command line mode
        users = {}
        if args.admin:
            users["admin"] = create_user("admin", args.admin, "admin")
        if args.operator:
            users["operator"] = create_user("operator", args.operator, "operator")
        if args.viewer:
            users["viewer"] = create_user("viewer", args.viewer, "viewer")
        
        if not users:
            print("ERROR: At least one user must be specified")
            sys.exit(1)
    else:
        # Interactive mode
        users = interactive_setup()
    
    # Output
    if args.env:
        # Output as environment variable
        users_json = json.dumps(users)
        print()
        print("=" * 60)
        print("Add this to your environment:")
        print("=" * 60)
        print(f'export DASHBOARD_USERS=\'{users_json}\'')
        print()
    else:
        # Save to file
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        with open(args.output, 'w') as f:
            json.dump(users, f, indent=2)
        
        # Set secure permissions
        os.chmod(args.output, 0o600)
        
        print()
        print("=" * 60)
        print("Users saved successfully!")
        print("=" * 60)
        print(f"File: {args.output}")
        print(f"Permissions: 600 (owner read/write only)")
        print()
        print("To use this file, set the environment variable:")
        print(f'export DASHBOARD_USERS_FILE="{args.output}"')
        print()
        print("Or add to your .env file:")
        print(f'DASHBOARD_USERS_FILE={args.output}')
        print()


if __name__ == "__main__":
    main()
