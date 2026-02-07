"""
Setup wizard for initial bot configuration.

7-step wizard:
1. Password creation
2. Privy configuration
3. Wallet creation
4. Funding verification
5. Exchange configuration
6. Strategy configuration
7. Backup & launch
"""

from src.dashboard.setup.jobs import SetupJobManager, JobStatus, JobType
from src.dashboard.setup.steps import SetupSteps
from src.dashboard.setup.validators import SetupValidator, ValidationResult

__all__ = [
    "SetupJobManager",
    "JobStatus", 
    "JobType",
    "SetupSteps",
    "SetupValidator",
    "ValidationResult",
]
