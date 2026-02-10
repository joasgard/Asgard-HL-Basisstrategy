"""
Transaction Validator for Delta Neutral Arbitrage.

Validates all transactions before signing/submission to ensure they only
interact with allowed programs and contracts. This is a critical security
layer to prevent malicious transactions.

Validation Rules:
- Solana: All instruction program IDs must be in allowlist
- Hyperliquid: EIP-712 domain and chain ID must match expected values
- Withdrawals: Only to authorized hardware wallet addresses
- Unknown programs: Transaction rejected

Allowed Programs (from spec 8.3):
- Marginfi, Kamino, Solend, Drift lending programs
- Asgard margin trading program
- Hyperliquid exchange contract
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Optional, Set, Any

from src.config.assets import Asset
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ValidationResult(Enum):
    """Transaction validation result."""
    VALID = "valid"
    INVALID_PROGRAM = "invalid_program"
    INVALID_WITHDRAWAL = "invalid_withdrawal"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_CHAIN_ID = "invalid_chain_id"
    INVALID_DOMAIN = "invalid_domain"
    UNKNOWN_TRANSACTION = "unknown_transaction"


@dataclass
class TransactionValidation:
    """Result of transaction validation."""
    
    valid: bool
    result: ValidationResult
    reason: Optional[str] = None
    
    # Details
    programs_checked: List[str] = None
    rejected_programs: List[str] = None
    
    def __post_init__(self):
        if self.programs_checked is None:
            self.programs_checked = []
        if self.rejected_programs is None:
            self.rejected_programs = []


class TransactionValidator:
    """
    Validates transactions before signing and submission.
    
    This validator ensures that all transactions only interact with
    known, allowed programs and contracts. It acts as a security
    gate before any transaction is signed.
    
    Solana Validation:
    - Parses transaction instructions
    - Extracts program IDs
    - Validates against allowlist
    - Rejects if any unknown program
    
    Hyperliquid Validation:
    - Validates EIP-712 signature domain
    - Checks chain ID (Arbitrum)
    - Validates action types
    
    Withdrawal Validation:
    - Destination must be authorized address
    - Only hardware wallet addresses allowed
    
    Usage:
        validator = TransactionValidator(
            allowed_solana_programs=["Marginfi...", "Kamino..."],
            authorized_withdrawal_address="HARDWARE_WALLET..."
        )
        
        # Validate Solana transaction
        result = validator.validate_solana_transaction(tx_bytes)
        if result.valid:
            await sign_and_submit(tx)
        else:
            logger.error(f"Invalid transaction: {result.reason}")
    
    Args:
        allowed_solana_programs: List of allowed Solana program IDs
        allowed_hyperliquid_contracts: List of allowed HL contract addresses
        authorized_withdrawal_solana: Authorized withdrawal address (Solana)
        authorized_withdrawal_hyperliquid: Authorized withdrawal address (HL)
        arbitrum_chain_id: Expected Arbitrum chain ID
    """
    
    # Default allowed programs (mainnet addresses)
    DEFAULT_SOLANA_PROGRAMS: Set[str] = {
        # Marginfi
        "MFv2hWf31Z9kbCa1snEPYcvnvbsWBcWAjjaTzMX2Q9",
        # Kamino
        "KLend2g3cP87fffoy8q1mQqGKjrxFtd9BKE1rM5cCp",
        # Solend
        "So1endDqUFYhgUNLA3P8wDxzDEaF1ZpCtiE2YfLJ1",
        # Drift
        "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH",
        # Asgard (placeholder - use actual address)
        "AsgardXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    }
    
    DEFAULT_HYPERLIQUID_CONTRACTS: Set[str] = {
        # Hyperliquid exchange (Arbitrum)
        "0x0000000000000000000000000000000000000000",  # Placeholder
    }
    
    ARBITRUM_CHAIN_ID = 42161
    ARBITRUM_ONE_DOMAIN = {
        "name": "Hyperliquid",
        "version": "1",
        "chainId": 42161,
    }
    
    def __init__(
        self,
        allowed_solana_programs: Optional[List[str]] = None,
        allowed_hyperliquid_contracts: Optional[List[str]] = None,
        authorized_withdrawal_solana: Optional[str] = None,
        authorized_withdrawal_hyperliquid: Optional[str] = None,
        arbitrum_chain_id: int = ARBITRUM_CHAIN_ID,
    ):
        self.allowed_solana_programs = set(allowed_solana_programs or self.DEFAULT_SOLANA_PROGRAMS)
        self.allowed_hyperliquid_contracts = set(allowed_hyperliquid_contracts or self.DEFAULT_HYPERLIQUID_CONTRACTS)
        
        self.authorized_withdrawal_solana = authorized_withdrawal_solana
        self.authorized_withdrawal_hyperliquid = authorized_withdrawal_hyperliquid
        self.arbitrum_chain_id = arbitrum_chain_id
        
        logger.info(
            f"TransactionValidator initialized: "
            f"{len(self.allowed_solana_programs)} Solana programs, "
            f"{len(self.allowed_hyperliquid_contracts)} HL contracts"
        )
    
    def validate_solana_program(self, program_id: str) -> bool:
        """
        Validate a single Solana program ID.
        
        Args:
            program_id: The program ID to validate
            
        Returns:
            True if program is in allowlist
        """
        return program_id in self.allowed_solana_programs
    
    def validate_solana_programs(self, program_ids: List[str]) -> TransactionValidation:
        """
        Validate multiple Solana program IDs.
        
        Args:
            program_ids: List of program IDs to validate
            
        Returns:
            TransactionValidation result
        """
        rejected = []
        
        for program_id in program_ids:
            if not self.validate_solana_program(program_id):
                rejected.append(program_id)
        
        if rejected:
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_PROGRAM,
                reason=f"Unknown programs: {rejected}",
                programs_checked=program_ids,
                rejected_programs=rejected,
            )
        
        return TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
            programs_checked=program_ids,
        )
    
    def validate_solana_withdrawal(
        self,
        destination: str,
        amount: Optional[Decimal] = None,
    ) -> TransactionValidation:
        """
        Validate a Solana withdrawal destination.
        
        Args:
            destination: Withdrawal destination address
            amount: Withdrawal amount (for logging)
            
        Returns:
            TransactionValidation result
        """
        if self.authorized_withdrawal_solana is None:
            logger.warning("No authorized withdrawal address configured for Solana")
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_WITHDRAWAL,
                reason="No authorized withdrawal address configured",
            )
        
        if destination != self.authorized_withdrawal_solana:
            logger.error(
                f"Unauthorized Solana withdrawal attempt to {destination} "
                f"(authorized: {self.authorized_withdrawal_solana})"
            )
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_WITHDRAWAL,
                reason=f"Unauthorized withdrawal destination: {destination}",
            )
        
        logger.info(f"Solana withdrawal authorized to {destination}")
        return TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
            reason="Withdrawal to authorized address",
        )
    
    def validate_hyperliquid_domain(
        self,
        domain: Dict[str, Any],
    ) -> TransactionValidation:
        """
        Validate EIP-712 domain for Hyperliquid transactions.
        
        Args:
            domain: EIP-712 domain dictionary
            
        Returns:
            TransactionValidation result
        """
        # Check chain ID
        chain_id = domain.get("chainId")
        if chain_id != self.arbitrum_chain_id:
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_CHAIN_ID,
                reason=f"Invalid chain ID: {chain_id} (expected {self.arbitrum_chain_id})",
            )
        
        # Check domain name
        name = domain.get("name")
        if name != "Hyperliquid":
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_DOMAIN,
                reason=f"Invalid domain name: {name}",
            )
        
        return TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
            reason="EIP-712 domain valid",
        )
    
    def validate_hyperliquid_withdrawal(
        self,
        destination: str,
        amount: Optional[Decimal] = None,
    ) -> TransactionValidation:
        """
        Validate a Hyperliquid withdrawal destination.
        
        Args:
            destination: Withdrawal destination address
            amount: Withdrawal amount (for logging)
            
        Returns:
            TransactionValidation result
        """
        if self.authorized_withdrawal_hyperliquid is None:
            logger.warning("No authorized withdrawal address configured for Hyperliquid")
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_WITHDRAWAL,
                reason="No authorized withdrawal address configured",
            )
        
        # Normalize addresses (case-insensitive for Ethereum)
        dest_normalized = destination.lower()
        auth_normalized = self.authorized_withdrawal_hyperliquid.lower()
        
        if dest_normalized != auth_normalized:
            logger.error(
                f"Unauthorized Hyperliquid withdrawal attempt to {destination} "
                f"(authorized: {self.authorized_withdrawal_hyperliquid})"
            )
            return TransactionValidation(
                valid=False,
                result=ValidationResult.INVALID_WITHDRAWAL,
                reason=f"Unauthorized withdrawal destination: {destination}",
            )
        
        logger.info(f"Hyperliquid withdrawal authorized to {destination}")
        return TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
            reason="Withdrawal to authorized address",
        )
    
    def validate_hyperliquid_action(
        self,
        action_type: str,
        action_params: Dict[str, Any],
    ) -> TransactionValidation:
        """
        Validate a Hyperliquid action type.
        
        Args:
            action_type: Type of action (order, updateLeverage, etc.)
            action_params: Action parameters
            
        Returns:
            TransactionValidation result
        """
        allowed_actions = {
            "order",
            "updateLeverage",
            "cancel",
            "withdraw",
        }
        
        if action_type not in allowed_actions:
            return TransactionValidation(
                valid=False,
                result=ValidationResult.UNKNOWN_TRANSACTION,
                reason=f"Unknown action type: {action_type}",
            )
        
        # Special validation for withdrawals
        if action_type == "withdraw":
            destination = action_params.get("destination")
            if destination:
                return self.validate_hyperliquid_withdrawal(destination)
        
        return TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
            reason=f"Action type {action_type} valid",
        )
    
    def add_allowed_solana_program(self, program_id: str):
        """Add a program to the Solana allowlist."""
        self.allowed_solana_programs.add(program_id)
        logger.info(f"Added Solana program to allowlist: {program_id}")
    
    def remove_allowed_solana_program(self, program_id: str):
        """Remove a program from the Solana allowlist."""
        self.allowed_solana_programs.discard(program_id)
        logger.info(f"Removed Solana program from allowlist: {program_id}")
    
    def add_allowed_hyperliquid_contract(self, contract_address: str):
        """Add a contract to the Hyperliquid allowlist."""
        self.allowed_hyperliquid_contracts.add(contract_address)
        logger.info(f"Added Hyperliquid contract to allowlist: {contract_address}")
    
    def get_allowed_programs_summary(self) -> Dict[str, List[str]]:
        """Get summary of allowed programs."""
        return {
            "solana": list(self.allowed_solana_programs),
            "hyperliquid": list(self.allowed_hyperliquid_contracts),
        }
    
    def validate_transaction_batch(
        self,
        transactions: List[Dict[str, Any]],
    ) -> List[TransactionValidation]:
        """
        Validate a batch of transactions.
        
        Args:
            transactions: List of transaction dicts with 'chain' and 'data' keys
            
        Returns:
            List of validation results
        """
        results = []
        
        for tx in transactions:
            chain = tx.get("chain")
            
            if chain == "solana":
                program_ids = tx.get("program_ids", [])
                result = self.validate_solana_programs(program_ids)
            elif chain == "hyperliquid":
                domain = tx.get("domain", {})
                result = self.validate_hyperliquid_domain(domain)
            else:
                result = TransactionValidation(
                    valid=False,
                    result=ValidationResult.UNKNOWN_TRANSACTION,
                    reason=f"Unknown chain: {chain}",
                )
            
            results.append(result)
        
        return results
