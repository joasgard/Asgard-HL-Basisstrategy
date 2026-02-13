"""Tests for Docker configuration files."""
import pytest
import yaml
from pathlib import Path


class TestDockerfile:
    """Test Dockerfile configuration."""
    
    @pytest.fixture
    def dockerfile_path(self):
        """Path to Dockerfile."""
        return Path(__file__).parent.parent.parent.parent / "docker" / "Dockerfile"
    
    @pytest.fixture
    def dockerfile_content(self, dockerfile_path):
        """Read Dockerfile content."""
        return dockerfile_path.read_text()
    
    def test_dockerfile_exists(self, dockerfile_path):
        """Test Dockerfile exists."""
        assert dockerfile_path.exists()
    
    def test_multi_stage_build(self, dockerfile_content):
        """Test Dockerfile uses multi-stage build."""
        assert "FROM" in dockerfile_content
        assert "as frontend-builder" in dockerfile_content
        assert "as python-builder" in dockerfile_content
        assert "as production" in dockerfile_content
    
    def test_production_target(self, dockerfile_content):
        """Test production stage exists."""
        assert "as production" in dockerfile_content
    
    def test_development_target(self, dockerfile_content):
        """Test development stage exists."""
        assert "as development" in dockerfile_content
    
    def test_non_root_user(self, dockerfile_content):
        """Test Dockerfile creates and uses non-root user."""
        assert "useradd" in dockerfile_content or "adduser" in dockerfile_content
        assert "USER" in dockerfile_content
    
    def test_healthcheck_defined(self, dockerfile_content):
        """Test Dockerfile includes healthcheck."""
        assert "HEALTHCHECK" in dockerfile_content
    
    def test_python_version(self, dockerfile_content):
        """Test Dockerfile uses Python 3.11."""
        assert "python:3.11" in dockerfile_content
    
    def test_pip_requirements_copied(self, dockerfile_content):
        """Test requirements.txt is copied."""
        assert "requirements.txt" in dockerfile_content
    
    def test_venv_created(self, dockerfile_content):
        """Test virtual environment is created."""
        assert "python -m venv" in dockerfile_content or "/opt/venv" in dockerfile_content
    
    def test_security_no_cache(self, dockerfile_content):
        """Test pip cache is disabled."""
        assert "PIP_NO_CACHE_DIR" in dockerfile_content


class TestDockerCompose:
    """Test docker-compose.yml configuration."""
    
    @pytest.fixture
    def compose_path(self):
        """Path to docker-compose.yml."""
        return Path(__file__).parent.parent.parent.parent / "docker" / "docker-compose.yml"
    
    @pytest.fixture
    def compose_config(self, compose_path):
        """Load docker-compose configuration."""
        if not compose_path.exists():
            pytest.skip("docker-compose.yml not found")
        
        with open(compose_path) as f:
            return yaml.safe_load(f)
    
    def test_compose_file_exists(self, compose_path):
        """Test docker-compose.yml exists."""
        assert compose_path.exists()
    
    def test_version_specified(self, compose_config):
        """Test compose file version is specified."""
        assert "version" in compose_config
    
    def test_bot_service_defined(self, compose_config):
        """Test bot service is defined."""
        assert "services" in compose_config
        assert "bot" in compose_config["services"]
    
    def test_bot_service_image(self, compose_config):
        """Test bot service has image configuration."""
        bot = compose_config["services"]["bot"]
        assert "build" in bot or "image" in bot
    
    def test_bot_restart_policy(self, compose_config):
        """Test bot has restart policy."""
        bot = compose_config["services"]["bot"]
        assert bot.get("restart") == "unless-stopped"
    
    def test_environment_variables(self, compose_config):
        """Test environment variables are configured."""
        bot = compose_config["services"]["bot"]
        assert "environment" in bot

        env = bot["environment"]
        # Check required variables are referenced
        assert any("SOLANA_RPC_URL" in str(e) for e in env)
        assert any("ARBITRUM_RPC_URL" in str(e) for e in env)
    
    def test_volumes_configured(self, compose_config):
        """Test volumes are configured."""
        bot = compose_config["services"]["bot"]
        assert "volumes" in bot
    
    def test_volumes_defined(self, compose_config):
        """Test named volumes are defined."""
        assert "volumes" in compose_config
        assert "bot-data" in compose_config["volumes"]
        assert "bot-logs" in compose_config["volumes"]
    
    def test_networks_configured(self, compose_config):
        """Test networks are configured."""
        assert "networks" in compose_config
    
    def test_healthcheck_configured(self, compose_config):
        """Test healthcheck is configured."""
        bot = compose_config["services"]["bot"]
        assert "healthcheck" in bot
        
        health = bot["healthcheck"]
        assert "test" in health
        assert "interval" in health
    
    def test_logging_configured(self, compose_config):
        """Test logging is configured."""
        bot = compose_config["services"]["bot"]
        assert "logging" in bot
        
        logging = bot["logging"]
        assert logging.get("driver") == "json-file"
    
    def test_dev_service_exists(self, compose_config):
        """Test development service exists."""
        assert "bot-dev" in compose_config["services"]
    
    def test_shadow_service_exists(self, compose_config):
        """Test shadow trading service exists."""
        assert "bot-shadow" in compose_config["services"]
    
    def test_shadow_mode_env(self, compose_config):
        """Test shadow service has SHADOW_MODE enabled."""
        shadow = compose_config["services"]["bot-shadow"]
        env = shadow.get("environment", [])
        assert any("SHADOW_MODE=true" in str(e) for e in env)


class TestDeployScript:
    """Test deploy.sh script."""
    
    @pytest.fixture
    def script_path(self):
        """Path to deploy.sh."""
        return Path(__file__).parent.parent.parent.parent / "scripts" / "deploy.sh"
    
    @pytest.fixture
    def script_content(self, script_path):
        """Read deploy.sh content."""
        return script_path.read_text()
    
    def test_script_exists(self, script_path):
        """Test deploy.sh exists."""
        assert script_path.exists()
    
    def test_script_executable(self, script_path):
        """Test deploy.sh is executable."""
        import os
        assert os.access(script_path, os.X_OK)
    
    def test_shebang_present(self, script_content):
        """Test shebang is present."""
        assert script_content.startswith("#!/bin/bash")
    
    def test_strict_mode(self, script_content):
        """Test script uses strict mode."""
        assert "set -euo pipefail" in script_content
    
    def test_help_option(self, script_content):
        """Test help option is implemented."""
        assert "--help" in script_content
    
    def test_docker_check(self, script_content):
        """Test Docker dependency check exists."""
        assert "docker" in script_content
        assert "check_dependencies" in script_content
    
    def test_environment_handling(self, script_content):
        """Test environment variable handling."""
        assert "ENVIRONMENT" in script_content
    
    def test_build_function(self, script_content):
        """Test build function exists."""
        assert "build_image" in script_content
    
    def test_deploy_function(self, script_content):
        """Test deploy function exists."""
        assert "deploy" in script_content
    
    def test_health_check(self, script_content):
        """Test health check function exists."""
        assert "health_check" in script_content


class TestSetupScript:
    """Test setup.sh script."""
    
    @pytest.fixture
    def script_path(self):
        """Path to setup.sh."""
        return Path(__file__).parent.parent.parent.parent / "scripts" / "setup.sh"
    
    @pytest.fixture
    def script_content(self, script_path):
        """Read setup.sh content."""
        return script_path.read_text()
    
    def test_script_exists(self, script_path):
        """Test setup.sh exists."""
        assert script_path.exists()
    
    def test_script_executable(self, script_path):
        """Test setup.sh is executable."""
        import os
        assert os.access(script_path, os.X_OK)
    
    def test_python_check(self, script_content):
        """Test Python version check exists."""
        assert "python3" in script_content
        assert "PYTHON_VERSION" in script_content
    
    def test_venv_setup(self, script_content):
        """Test virtual environment setup."""
        assert "python3 -m venv" in script_content
    
    def test_pip_install(self, script_content):
        """Test pip install commands."""
        assert "pip install" in script_content
    
    def test_secrets_setup(self, script_content):
        """Test secrets directory setup."""
        assert "secrets" in script_content
    
    def test_env_file_setup(self, script_content):
        """Test .env file setup."""
        assert ".env" in script_content


class TestHealthCheckScript:
    """Test health_check.sh script."""
    
    @pytest.fixture
    def script_path(self):
        """Path to health_check.sh."""
        return Path(__file__).parent.parent.parent.parent / "scripts" / "health_check.sh"
    
    @pytest.fixture
    def script_content(self, script_path):
        """Read health_check.sh content."""
        return script_path.read_text()
    
    def test_script_exists(self, script_path):
        """Test health_check.sh exists."""
        assert script_path.exists()
    
    def test_script_executable(self, script_path):
        """Test health_check.sh is executable."""
        import os
        assert os.access(script_path, os.X_OK)
    
    def test_docker_compose_check(self, script_content):
        """Test Docker Compose health check."""
        assert "docker-compose" in script_content
    
    def test_disk_space_check(self, script_content):
        """Test disk space check exists."""
        assert "disk" in script_content.lower()
    
    def test_memory_check(self, script_content):
        """Test memory check exists."""
        assert "memory" in script_content.lower()
    
    def test_alert_function(self, script_content):
        """Test alert function exists."""
        assert "send_alert" in script_content
    
    def test_monitor_mode(self, script_content):
        """Test monitor mode exists."""
        assert "monitor" in script_content
    
    def test_logging_function(self, script_content):
        """Test logging functions exist."""
        assert "log_info" in script_content
        assert "log_error" in script_content


class TestProjectStructure:
    """Test overall project structure for deployment."""
    
    @pytest.fixture
    def project_root(self):
        """Get project root directory."""
        return Path(__file__).parent.parent.parent.parent
    
    def test_docker_directory_exists(self, project_root):
        """Test docker directory exists."""
        docker_dir = project_root / "docker"
        assert docker_dir.exists()
        assert docker_dir.is_dir()
    
    def test_scripts_directory_exists(self, project_root):
        """Test scripts directory exists."""
        scripts_dir = project_root / "scripts"
        assert scripts_dir.exists()
        assert scripts_dir.is_dir()
    
    def test_requirements_txt_exists(self, project_root):
        """Test requirements.txt exists."""
        req_file = project_root / "requirements.txt"
        assert req_file.exists()
    
    def test_dockerfile_in_docker_dir(self, project_root):
        """Test Dockerfile is in docker directory."""
        dockerfile = project_root / "docker" / "Dockerfile"
        assert dockerfile.exists()
    
    def test_compose_in_docker_dir(self, project_root):
        """Test docker-compose.yml is in docker directory."""
        compose_file = project_root / "docker" / "docker-compose.yml"
        assert compose_file.exists()
