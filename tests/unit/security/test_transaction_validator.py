"""Tests for Transaction Validator module."""
import pytest
from decimal import Decimal

from src.security.transaction_validator import (
    TransactionValidator,
    ValidationResult,
    TransactionValidation,
)


class TestTransactionValidatorInitialization:
    """Test TransactionValidator initialization."""
    
    def test_default_initialization(self):
        """Test TransactionValidator with defaults."""
        validator = TransactionValidator()
        
        # Should have default programs
        assert len(validator.allowed_solana_programs) > 0
        assert len(validator.allowed_hyperliquid_contracts) > 0
        assert validator.arbitrum_chain_id == 42161
    
    def test_custom_initialization(self):
        """Test TransactionValidator with custom values."""
        validator = TransactionValidator(
            allowed_solana_programs=["prog1", "prog2"],
            authorized_withdrawal_solana="auth_sol",
            authorized_withdrawal_hyperliquid="auth_hl",
            arbitrum_chain_id=421613,  # Arbitrum Goerli
        )
        
        assert validator.allowed_solana_programs == {"prog1", "prog2"}
        assert validator.authorized_withdrawal_solana == "auth_sol"
        assert validator.authorized_withdrawal_hyperliquid == "auth_hl"
        assert validator.arbitrum_chain_id == 421613


class TestSolanaProgramValidation:
    """Test Solana program validation."""
    
    def test_validate_allowed_program(self):
        """Test validation of allowed program."""
        validator = TransactionValidator(
            allowed_solana_programs=["AllowedProgram1111111111111111111111111111111"]
        )
        
        result = validator.validate_solana_program(
            "AllowedProgram1111111111111111111111111111111"
        )
        
        assert result is True
    
    def test_validate_unknown_program(self):
        """Test validation of unknown program."""
        validator = TransactionValidator(
            allowed_solana_programs=["AllowedProgram1111111111111111111111111111111"]
        )
        
        result = validator.validate_solana_program(
            "UnknownProgram1111111111111111111111111111111"
        )
        
        assert result is False
    
    def test_validate_multiple_programs_all_allowed(self):
        """Test validation when all programs allowed."""
        validator = TransactionValidator(
            allowed_solana_programs=["Prog1", "Prog2", "Prog3"]
        )
        
        result = validator.validate_solana_programs(["Prog1", "Prog2"])
        
        assert result.valid is True
        assert result.result == ValidationResult.VALID
    
    def test_validate_multiple_programs_some_rejected(self):
        """Test validation when some programs rejected."""
        validator = TransactionValidator(
            allowed_solana_programs=["Prog1", "Prog2"]
        )
        
        result = validator.validate_solana_programs(["Prog1", "BadProg"])
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_PROGRAM
        assert "BadProg" in result.rejected_programs


class TestSolanaWithdrawalValidation:
    """Test Solana withdrawal validation."""
    
    def test_valid_withdrawal(self):
        """Test valid withdrawal to authorized address."""
        validator = TransactionValidator(
            authorized_withdrawal_solana="AuthorizedSol1111111111111111111111111111111"
        )
        
        result = validator.validate_solana_withdrawal(
            "AuthorizedSol1111111111111111111111111111111"
        )
        
        assert result.valid is True
        assert result.result == ValidationResult.VALID
    
    def test_invalid_withdrawal_address(self):
        """Test invalid withdrawal to unauthorized address."""
        validator = TransactionValidator(
            authorized_withdrawal_solana="AuthorizedSol1111111111111111111111111111111"
        )
        
        result = validator.validate_solana_withdrawal(
            "UnauthorizedSol111111111111111111111111111111"
        )
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_WITHDRAWAL
    
    def test_withdrawal_no_auth_configured(self):
        """Test withdrawal when no auth address configured."""
        validator = TransactionValidator()
        
        result = validator.validate_solana_withdrawal(
            "SomeAddress11111111111111111111111111111111"
        )
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_WITHDRAWAL


class TestHyperliquidDomainValidation:
    """Test Hyperliquid EIP-712 domain validation."""
    
    def test_valid_domain(self):
        """Test valid EIP-712 domain."""
        validator = TransactionValidator()
        
        domain = {
            "name": "Hyperliquid",
            "version": "1",
            "chainId": 42161,
        }
        
        result = validator.validate_hyperliquid_domain(domain)
        
        assert result.valid is True
        assert result.result == ValidationResult.VALID
    
    def test_invalid_chain_id(self):
        """Test invalid chain ID."""
        validator = TransactionValidator()
        
        domain = {
            "name": "Hyperliquid",
            "version": "1",
            "chainId": 1,  # Mainnet instead of Arbitrum
        }
        
        result = validator.validate_hyperliquid_domain(domain)
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_CHAIN_ID
    
    def test_invalid_domain_name(self):
        """Test invalid domain name."""
        validator = TransactionValidator()
        
        domain = {
            "name": "FakeExchange",
            "version": "1",
            "chainId": 42161,
        }
        
        result = validator.validate_hyperliquid_domain(domain)
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_DOMAIN


class TestHyperliquidWithdrawalValidation:
    """Test Hyperliquid withdrawal validation."""
    
    def test_valid_withdrawal(self):
        """Test valid withdrawal to authorized address."""
        validator = TransactionValidator(
            authorized_withdrawal_hyperliquid="0xAuthorizedAddress1234567890123456789012"
        )
        
        result = validator.validate_hyperliquid_withdrawal(
            "0xAuthorizedAddress1234567890123456789012"
        )
        
        assert result.valid is True
    
    def test_valid_withdrawal_case_insensitive(self):
        """Test that Ethereum addresses are case-insensitive."""
        validator = TransactionValidator(
            authorized_withdrawal_hyperliquid="0xAUTHORIZEDADDRESS1234567890123456789012"
        )
        
        result = validator.validate_hyperliquid_withdrawal(
            "0xauthorizedaddress1234567890123456789012"
        )
        
        assert result.valid is True
    
    def test_invalid_withdrawal(self):
        """Test invalid withdrawal address."""
        validator = TransactionValidator(
            authorized_withdrawal_hyperliquid="0xAuthorizedAddress1234567890123456789012"
        )
        
        result = validator.validate_hyperliquid_withdrawal(
            "0xBadAddress123456789012345678901234567890"
        )
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_WITHDRAWAL


class TestHyperliquidActionValidation:
    """Test Hyperliquid action validation."""
    
    def test_valid_order_action(self):
        """Test valid order action."""
        validator = TransactionValidator()
        
        result = validator.validate_hyperliquid_action(
            "order",
            {"coin": "SOL", "is_buy": False, "sz": "1.5"}
        )
        
        assert result.valid is True
    
    def test_valid_update_leverage_action(self):
        """Test valid update leverage action."""
        validator = TransactionValidator()
        
        result = validator.validate_hyperliquid_action(
            "updateLeverage",
            {"coin": "SOL", "leverage": 3}
        )
        
        assert result.valid is True
    
    def test_invalid_action_type(self):
        """Test invalid action type."""
        validator = TransactionValidator()
        
        result = validator.validate_hyperliquid_action(
            "maliciousAction",
            {"data": "evil"}
        )
        
        assert result.valid is False
        assert result.result == ValidationResult.UNKNOWN_TRANSACTION
    
    def test_withdrawal_action_validates_destination(self):
        """Test that withdrawal action validates destination."""
        validator = TransactionValidator(
            authorized_withdrawal_hyperliquid="0xAuthorizedAddress1234567890123456789012"
        )
        
        result = validator.validate_hyperliquid_action(
            "withdraw",
            {"destination": "0xBadAddress123456789012345678901234567890"}
        )
        
        assert result.valid is False
        assert result.result == ValidationResult.INVALID_WITHDRAWAL


class TestAllowlistManagement:
    """Test allowlist management."""
    
    def test_add_allowed_solana_program(self):
        """Test adding program to allowlist."""
        validator = TransactionValidator(allowed_solana_programs=["Prog1"])
        
        validator.add_allowed_solana_program("NewProg")
        
        assert "NewProg" in validator.allowed_solana_programs
    
    def test_remove_allowed_solana_program(self):
        """Test removing program from allowlist."""
        validator = TransactionValidator(allowed_solana_programs=["Prog1", "Prog2"])
        
        validator.remove_allowed_solana_program("Prog1")
        
        assert "Prog1" not in validator.allowed_solana_programs
        assert "Prog2" in validator.allowed_solana_programs
    
    def test_add_allowed_hyperliquid_contract(self):
        """Test adding contract to allowlist."""
        validator = TransactionValidator()
        
        validator.add_allowed_hyperliquid_contract("0xNewContract")
        
        assert "0xNewContract" in validator.allowed_hyperliquid_contracts
    
    def test_get_allowed_programs_summary(self):
        """Test getting allowlist summary."""
        validator = TransactionValidator(
            allowed_solana_programs=["Prog1", "Prog2"],
            allowed_hyperliquid_contracts=["0xContract1"],
        )
        
        summary = validator.get_allowed_programs_summary()
        
        assert "solana" in summary
        assert "hyperliquid" in summary
        assert len(summary["solana"]) == 2
        assert len(summary["hyperliquid"]) == 1


class TestTransactionBatchValidation:
    """Test batch transaction validation."""
    
    def test_validate_batch_all_valid(self):
        """Test batch validation when all valid."""
        validator = TransactionValidator(
            allowed_solana_programs=["Prog1", "Prog2"]
        )
        
        transactions = [
            {"chain": "solana", "program_ids": ["Prog1"]},
            {"chain": "solana", "program_ids": ["Prog2"]},
        ]
        
        results = validator.validate_transaction_batch(transactions)
        
        assert len(results) == 2
        assert all(r.valid for r in results)
    
    def test_validate_batch_some_invalid(self):
        """Test batch validation when some invalid."""
        validator = TransactionValidator(
            allowed_solana_programs=["Prog1"]
        )
        
        transactions = [
            {"chain": "solana", "program_ids": ["Prog1"]},
            {"chain": "solana", "program_ids": ["BadProg"]},
        ]
        
        results = validator.validate_transaction_batch(transactions)
        
        assert results[0].valid is True
        assert results[1].valid is False
    
    def test_validate_batch_unknown_chain(self):
        """Test batch validation with unknown chain."""
        validator = TransactionValidator()
        
        transactions = [
            {"chain": "unknown", "data": {}},
        ]
        
        results = validator.validate_transaction_batch(transactions)
        
        assert results[0].valid is False
        assert results[0].result == ValidationResult.UNKNOWN_TRANSACTION


class TestTransactionValidationDataclass:
    """Test TransactionValidation dataclass."""
    
    def test_validation_creation(self):
        """Test TransactionValidation creation."""
        validation = TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
            reason="All good",
            programs_checked=["Prog1", "Prog2"],
        )
        
        assert validation.valid is True
        assert validation.result == ValidationResult.VALID
        assert validation.reason == "All good"
        assert validation.programs_checked == ["Prog1", "Prog2"]
    
    def test_validation_default_lists(self):
        """Test TransactionValidation default empty lists."""
        validation = TransactionValidation(
            valid=True,
            result=ValidationResult.VALID,
        )
        
        assert validation.programs_checked == []
        assert validation.rejected_programs == []


class TestDefaultPrograms:
    """Test default program allowlists."""
    
    def test_default_solana_programs_include_major_lending(self):
        """Test that default programs include major lending protocols."""
        validator = TransactionValidator()
        
        # Check for Marginfi, Kamino, Solend, Drift
        programs = validator.allowed_solana_programs
        
        # Should have the placeholder addresses
        assert len(programs) >= 4  # At least the 4 main lending protocols
    
    def test_arbitrum_chain_id(self):
        """Test Arbitrum chain ID constant."""
        assert TransactionValidator.ARBITRUM_CHAIN_ID == 42161
