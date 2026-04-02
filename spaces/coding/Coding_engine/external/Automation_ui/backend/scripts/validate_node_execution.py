#!/usr/bin/env python3
"""
Node Execution Validation Script
Tests all node templates to ensure they have proper execution functions
"""

import os
import sys
from pathlib import Path

# Add the backend directory to Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from services.comprehensive_node_templates import node_template_validator
from services.graph_execution_service import GraphExecutionService


def validate_comprehensive_templates():
    """Validate the comprehensive node templates"""
    print("🔍 Validating Comprehensive Node Templates...")
    print("=" * 60)

    validation_results = node_template_validator.validate_all_templates()

    # Print summary
    summary = validation_results["summary"]
    print(f"📊 SUMMARY:")
    print(
        f"   Total Templates: {summary.get('total_templates', summary.get('total', 0))}"
    )
    print(f"   ✅ Valid: {summary.get('valid_templates', summary.get('valid', 0))}")
    print(
        f"   ❌ Invalid: {summary.get('invalid_templates', summary.get('invalid', 0))}"
    )
    print(f"   Success Rate: {summary.get('success_rate', 0):.1f}%")
    print()

    # Print detailed results
    print("📋 DETAILED RESULTS:")
    results_key = (
        "template_results" if "template_results" in validation_results else "results"
    )
    for template_id, result in validation_results[results_key].items():
        status = "✅" if result["valid"] else "❌"
        has_exec = "📝" if result.get("has_execution", False) else "🚫"
        print(f"   {status} {has_exec} {template_id}")
        if not result["valid"] and result.get("error"):
            print(f"      Error: {result['error']}")

    return validation_results


def validate_graph_execution_templates():
    """Validate the graph execution service templates"""
    print("\n🔍 Validating Graph Execution Service Templates...")
    print("=" * 60)

    try:
        graph_service = GraphExecutionService()
        templates = graph_service.get_node_templates()

        print(f"📊 SUMMARY:")
        print(f"   Total Templates: {len(templates)}")
        print()

        print("📋 AVAILABLE TEMPLATES:")
        for template in templates:
            print(f"   • {template['id']} ({template['category']})")
            print(f"     Description: {template['description']}")

        return {"total": len(templates), "templates": templates}

    except Exception as e:
        print(f"❌ Error validating graph execution templates: {e}")
        return {"error": str(e)}


def validate_service_dependencies():
    """Validate that all required services are available"""
    print("\n🔍 Validating Service Dependencies...")
    print("=" * 60)

    required_services = [
        "live_desktop_service",
        "ocr_service",
        "click_automation_service",
        "file_watcher_service",
        "websocket_service",
        "graph_execution_service",
        "node_service",
    ]

    available_services = []
    missing_services = []

    for service_name in required_services:
        try:
            if service_name == "live_desktop_service":
                from services.live_desktop_service import LiveDesktopService

                available_services.append(service_name)
            elif service_name == "ocr_service":
                from services.ocr_service import OCRService

                available_services.append(service_name)
            elif service_name == "click_automation_service":
                from services.click_automation_service import \
                    ClickAutomationService

                available_services.append(service_name)
            elif service_name == "file_watcher_service":
                from services.file_watcher_service import FileWatcherService

                available_services.append(service_name)
            elif service_name == "websocket_service":
                from services.websocket_service import WebSocketService

                available_services.append(service_name)
            elif service_name == "graph_execution_service":
                from services.graph_execution_service import \
                    GraphExecutionService

                available_services.append(service_name)
            elif service_name == "node_service":
                from services.node_service import NodeService

                available_services.append(service_name)
        except ImportError as e:
            missing_services.append(service_name)

    print(f"📊 SERVICE STATUS:")
    print(f"   Required: {len(required_services)}")
    print(f"   ✅ Available: {len(available_services)}")
    print(f"   ❌ Missing: {len(missing_services)}")
    print()

    if available_services:
        print("✅ AVAILABLE SERVICES:")
        for service in available_services:
            print(f"   • {service}")

    if missing_services:
        print("\n❌ MISSING SERVICES:")
        for service in missing_services:
            print(f"   • {service}")

    return {
        "required": required_services,
        "available": available_services,
        "missing": missing_services,
    }


def validate_template_execution_syntax():
    """Validate the syntax of all template execution code"""
    print("\n🔍 Validating Template Execution Code Syntax...")
    print("=" * 60)

    validator = node_template_validator
    syntax_results = {}

    for template_id, template in validator.templates.items():
        execution_code = template.get("execution_code", "")

        if execution_code:
            try:
                compile(execution_code, f"<template_{template_id}>", "exec")
                syntax_results[template_id] = {"valid": True}
            except SyntaxError as e:
                syntax_results[template_id] = {"valid": False, "error": str(e)}
        else:
            syntax_results[template_id] = {"valid": False, "error": "No execution code"}

    valid_count = sum(1 for result in syntax_results.values() if result["valid"])
    total_count = len(syntax_results)

    print(f"📊 SYNTAX VALIDATION:")
    print(f"   Total Templates: {total_count}")
    print(f"   ✅ Valid Syntax: {valid_count}")
    print(f"   ❌ Invalid Syntax: {total_count - valid_count}")
    print()

    # Show errors
    errors = {
        tid: result for tid, result in syntax_results.items() if not result["valid"]
    }
    if errors:
        print("❌ SYNTAX ERRORS:")
        for template_id, result in errors.items():
            print(f"   • {template_id}: {result['error']}")

    return syntax_results


def create_validation_report():
    """Create a comprehensive validation report"""
    print("🚀 TRAE Node Execution Validation")
    print("=" * 60)
    print()

    # Run all validations
    comprehensive_results = validate_comprehensive_templates()
    graph_results = validate_graph_execution_templates()
    service_results = validate_service_dependencies()
    syntax_results = validate_template_execution_syntax()

    # Overall summary
    print("\n📈 OVERALL VALIDATION SUMMARY")
    print("=" * 60)

    comprehensive_success = (
        comprehensive_results["summary"]["valid"]
        == comprehensive_results["summary"]["total"]
    )
    services_success = len(service_results["missing"]) == 0
    syntax_success = all(result["valid"] for result in syntax_results.values())

    overall_success = comprehensive_success and services_success and syntax_success

    print(f"🎯 Overall Status: {'✅ PASS' if overall_success else '❌ FAIL'}")
    print(
        f"   📝 Template Validation: {'✅ PASS' if comprehensive_success else '❌ FAIL'}"
    )
    print(f"   🔧 Service Dependencies: {'✅ PASS' if services_success else '❌ FAIL'}")
    print(f"   💻 Syntax Validation: {'✅ PASS' if syntax_success else '❌ FAIL'}")

    if overall_success:
        print("\n🎉 All node templates have valid execution functions!")
        print("   Ready for graph execution.")
    else:
        print("\n⚠️  Some issues need to be resolved:")
        if not comprehensive_success:
            invalid_count = comprehensive_results["summary"]["invalid"]
            print(f"   • {invalid_count} templates missing or invalid execution code")
        if not services_success:
            missing_count = len(service_results["missing"])
            print(f"   • {missing_count} required services are missing")
        if not syntax_success:
            error_count = sum(
                1 for result in syntax_results.values() if not result["valid"]
            )
            print(f"   • {error_count} templates have syntax errors")

    return {
        "overall_success": overall_success,
        "comprehensive_results": comprehensive_results,
        "graph_results": graph_results,
        "service_results": service_results,
        "syntax_results": syntax_results,
    }


def main():
    """Main validation function"""
    try:
        report = create_validation_report()

        # Exit with appropriate code
        if report["overall_success"]:
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
