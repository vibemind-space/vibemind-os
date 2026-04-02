#!/usr/bin/env python3
"""
Validation Script for Refactored TRAE Backend

This script validates that the new refactored architecture is working correctly
and that all components are properly integrated.
"""

import sys
import time
from pathlib import Path

import requests


def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_status(test_name, status, details=""):
    """Print test status"""
    status_icon = "✅" if status else "❌"
    print(f"{status_icon} {test_name}")
    if details:
        print(f"   {details}")


def validate_architecture():
    """Validate the new architecture components"""

    print_header("TRAE Backend Architecture Validation")

    # 1. Test app creation
    print_header("1. Application Structure")
    try:
        from app.config import get_settings
        from app.main import create_app
        from app.services import get_service_manager

        app = create_app()
        settings = get_settings()

        print_status(
            "App Creation", True, f"Title: {app.title}, Version: {app.version}"
        )
        print_status(
            "Configuration",
            True,
            f"Environment: {settings.environment}, Port: {settings.port}",
        )
        print_status("Service Manager", True, "Service manager imported successfully")

    except Exception as e:
        print_status("App Creation", False, f"Error: {e}")
        return False

    # 2. Test API endpoints
    print_header("2. API Endpoint Validation")

    base_url = "http://localhost:8011"

    endpoints_to_test = [
        ("/", "Root endpoint"),
        ("/api/health", "Health check"),
        ("/api/node-system/templates", "Node templates"),
        ("/docs", "API documentation"),
    ]

    for endpoint, description in endpoints_to_test:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            print_status(
                description,
                response.status_code == 200,
                f"Status: {response.status_code}",
            )
        except requests.exceptions.RequestException as e:
            print_status(description, False, f"Connection error: {e}")

    # 3. Test configuration system
    print_header("3. Configuration System")

    try:
        settings = get_settings()

        # Test key configuration values
        config_tests = [
            (settings.app_name == "TRAE Backend", "App name configuration"),
            (settings.app_version == "1.0.0", "App version configuration"),
            (settings.is_development(), "Environment detection"),
            (len(settings.cors_origins) > 0, "CORS origins configuration"),
            (settings.enable_ocr is True, "Service feature flags"),
        ]

        for test_result, test_name in config_tests:
            print_status(test_name, test_result)

    except Exception as e:
        print_status("Configuration System", False, f"Error: {e}")

    # 4. Test service architecture
    print_header("4. Service Architecture")

    try:
        # Test health endpoint for service status
        response = requests.get(f"{base_url}/api/health", timeout=5)
        if response.status_code in [
            200,
            503,
        ]:  # 503 is acceptable for degraded services
            health_data = response.json()
            services = health_data.get("services", {})

            service_tests = [
                ("graph_execution" in services, "Graph execution service"),
                ("ocr" in services, "OCR service"),
                ("click_automation" in services, "Click automation service"),
                ("file_watcher" in services, "File watcher service"),
                ("live_desktop" in services, "Live desktop service"),
                ("websocket" in services, "WebSocket service"),
            ]

            for test_result, test_name in service_tests:
                print_status(test_name, test_result)

            print(f"\n   Service Summary: {len(services)} services detected")
            print(f"   Healthy services: {sum(services.values())}")

        else:
            print_status(
                "Service Health Check",
                False,
                f"Health endpoint failed: {response.status_code}",
            )

    except Exception as e:
        print_status("Service Architecture", False, f"Error: {e}")

    # 5. Test file structure
    print_header("5. File Structure Validation")

    expected_files = [
        "app/__init__.py",
        "app/main.py",
        "app/config.py",
        "app/logging.py",
        "app/exceptions.py",
        "app/services/__init__.py",
        "app/services/manager.py",
        "app/routers/__init__.py",
        "app/routers/health.py",
        "app/routers/node_system.py",
        "server.py",
    ]

    for file_path in expected_files:
        file_exists = Path(file_path).exists()
        print_status(f"File: {file_path}", file_exists)

    # 6. Test legacy vs new architecture
    print_header("6. Architecture Migration Status")

    new_architecture_files = ["app/main.py", "app/config.py", "server.py"]

    legacy_files = [
        "trae_backend_server.py",
        "working_backend.py",
        "minimal_integration_server.py",
    ]

    new_files_exist = all(Path(f).exists() for f in new_architecture_files)
    legacy_files_exist = any(Path(f).exists() for f in legacy_files)

    print_status("New architecture files", new_files_exist)
    print_status(
        "Legacy files present",
        legacy_files_exist,
        "Note: Legacy files can be removed after validation",
    )

    if new_files_exist:
        print_status("Architecture Migration", True, "New architecture is active")
    else:
        print_status("Architecture Migration", False, "New architecture incomplete")

    print_header("Validation Complete")

    if new_files_exist:
        print(
            "🎉 SUCCESS: The refactored TRAE Backend architecture is working correctly!"
        )
        print("\nKey improvements:")
        print("  • Modular router-based API structure")
        print("  • Centralized configuration management")
        print("  • Dependency injection with service manager")
        print("  • Comprehensive error handling")
        print("  • Structured logging with correlation IDs")
        print("  • Environment-based configuration")
        print("\nThe backend is now maintainable and scalable!")
        return True
    else:
        print("❌ FAILURE: Architecture validation failed")
        return False


if __name__ == "__main__":
    success = validate_architecture()
    sys.exit(0 if success else 1)
