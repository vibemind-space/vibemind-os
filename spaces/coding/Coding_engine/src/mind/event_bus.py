"""
Event Bus - Pub/Sub system for agent communication.

Enables agents to:
- Publish events about their actions and discoveries
- Subscribe to events they care about
- React autonomously to events from other agents
"""

import asyncio
import contextvars
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Any, Union
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)


class EventType(str, Enum):
    """Types of events in the system."""
    # File events
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"

    # Code events
    CODE_GENERATED = "code_generated"
    CODE_FIXED = "code_fixed"
    CODE_FIX_NEEDED = "code_fix_needed"
    GENERATION_REQUESTED = "generation_requested"
    RECOVERY_ATTEMPTED = "recovery_attempted"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    RECOVERY_FAILED = "recovery_failed"

    # Test events
    TEST_STARTED = "test_started"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    TEST_SUITE_COMPLETE = "test_suite_complete"
    TESTS_COMPLETED = "tests_completed"

    # Build events
    BUILD_STARTED = "build_started"
    BUILD_SUCCEEDED = "build_succeeded"
    BUILD_FAILED = "build_failed"
    BUILD_COMPLETED = "build_completed"

    # Deploy events
    DEPLOY_STARTED = "deploy_started"
    DEPLOY_SUCCEEDED = "deploy_succeeded"
    DEPLOY_FAILED = "deploy_failed"
    DEPLOY_LOGS_COLLECTED = "deploy_logs_collected"

    # Sandbox testing events (Docker-based)
    SANDBOX_TEST_STARTED = "sandbox_test_started"
    SANDBOX_TEST_PASSED = "sandbox_test_passed"
    SANDBOX_TEST_FAILED = "sandbox_test_failed"
    SANDBOX_LOGS_COLLECTED = "sandbox_logs_collected"

    # Container Log Seeding events (automatic log capture)
    CONTAINER_LOGS_SEEDED = "container_logs_seeded"
    CONTAINER_LOG_SEARCH_COMPLETE = "container_log_search_complete"

    # VNC Screen streaming events (for GUI apps in Docker)
    SCREEN_STREAM_STARTED = "screen_stream_started"
    SCREEN_STREAM_READY = "screen_stream_ready"
    SCREEN_STREAM_STOPPED = "screen_stream_stopped"

    # Cloud testing events (GitHub Actions)
    CLOUD_TEST_STARTED = "cloud_test_started"
    CLOUD_TEST_PASSED = "cloud_test_passed"
    CLOUD_TEST_FAILED = "cloud_test_failed"
    CLOUD_TEST_SKIPPED = "cloud_test_skipped"

    # Packaging events (electron-builder, npm pack)
    PACKAGE_STARTED = "package_started"
    PACKAGE_SUCCEEDED = "package_succeeded"
    PACKAGE_FAILED = "package_failed"

    # Release events (GitHub Releases)
    RELEASE_STARTED = "release_started"
    RELEASE_SUCCEEDED = "release_succeeded"
    RELEASE_FAILED = "release_failed"
    RELEASE_SKIPPED = "release_skipped"

    # Validation events
    VALIDATION_STARTED = "validation_started"
    VALIDATION_ERROR = "validation_error"
    VALIDATION_WARNING = "validation_warning"
    VALIDATION_PASSED = "validation_passed"

    # Requirements verification events (LLM-guided E2E testing)
    REQUIREMENTS_VERIFIED = "requirements_verified"
    REQUIREMENTS_FAILED = "requirements_failed"

    # Type checking events
    TYPE_ERROR = "type_error"
    TYPE_ERROR_FIXED = "type_error_fixed"
    TYPE_CHECK_PASSED = "type_check_passed"

    # Agent lifecycle events
    AGENT_STARTED = "agent_started"
    AGENT_ACTING = "agent_acting"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"

    # System events
    CONVERGENCE_UPDATE = "convergence_update"
    CONVERGENCE_UPDATE_PUSH = "convergence_update_push"  # Push-based convergence notification
    PREVIEW_READY = "preview_ready"
    SERVER_PORT_DETECTED = "server_port_detected"  # Auto-detected server port from output
    SYSTEM_READY = "system_ready"
    SYSTEM_ERROR = "system_error"

    # Review Gate Events (Pause/Resume for User Review)
    REVIEW_PAUSE_REQUESTED = "review_pause_requested"
    REVIEW_PAUSED = "review_paused"
    REVIEW_FEEDBACK_SUBMITTED = "review_feedback_submitted"
    REVIEW_RESUME_REQUESTED = "review_resume_requested"
    REVIEW_RESUMED = "review_resumed"

    # Escalation Events (Progressive Fix Strategies)
    ESCALATION_STARTED = "escalation_started"
    ESCALATION_LEVEL_CHANGED = "escalation_level_changed"
    ESCALATION_EXHAUSTED = "escalation_exhausted"
    CONFIDENCE_LOW = "confidence_low"
    CONFIDENCE_UPDATED = "confidence_updated"

    # Clarification Events (Ambiguity Resolution)
    CLARIFICATION_NEEDED = "clarification_needed"
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_CHOICE_SUBMITTED = "clarification_choice_submitted"
    CLARIFICATION_RESOLVED = "clarification_resolved"
    CLARIFICATION_TIMEOUT = "clarification_timeout"

    # CLI Monitoring events
    CLI_PROMPT_SENT = "cli_prompt_sent"
    CLI_RESPONSE_RECEIVED = "cli_response_received"
    CLI_CALL_ERROR = "cli_call_error"
    CLI_STATS_UPDATED = "cli_stats_updated"

    # Asset events
    ASSET_GENERATED = "asset_generated"
    ICON_CREATED = "icon_created"

    # E2E Testing events
    E2E_TEST_STARTED = "e2e_test_started"
    E2E_TEST_PASSED = "e2e_test_passed"
    E2E_TEST_FAILED = "e2e_test_failed"
    E2E_SCREENSHOT_TAKEN = "e2e_screenshot_taken"
    APP_LAUNCHED = "app_launched"
    APP_CRASHED = "app_crashed"

    # =========================================================================
    # CRUD Integration Events (E2E Database Verification)
    # =========================================================================
    CRUD_TEST_STARTED = "crud_test_started"
    CRUD_TEST_PASSED = "crud_test_passed"
    CRUD_TEST_FAILED = "crud_test_failed"
    CRUD_CREATE_VERIFIED = "crud_create_verified"
    CRUD_READ_VERIFIED = "crud_read_verified"
    CRUD_UPDATE_VERIFIED = "crud_update_verified"
    CRUD_DELETE_VERIFIED = "crud_delete_verified"
    CRUD_CYCLE_COMPLETE = "crud_cycle_complete"
    INTEGRATION_ERROR = "integration_error"

    # Browser error events (detected via Playwright console monitoring)
    BROWSER_ERROR = "browser_error"
    BROWSER_CONSOLE_ERROR = "browser_console_error"
    BROWSER_NETWORK_ERROR = "browser_network_error"

    # Runtime Debug events
    RUNTIME_TEST_STARTED = "runtime_test_started"
    RUNTIME_TEST_PASSED = "runtime_test_passed"
    RUNTIME_TEST_FAILED = "runtime_test_failed"
    RUNTIME_FIX_APPLIED = "runtime_fix_applied"

    # Continuous Debug events (real-time debugging during generation)
    DEBUG_STARTED = "debug_started"
    DEBUG_COMPLETE = "debug_complete"
    DEBUG_CONVERGED = "debug_converged"
    DEBUG_CYCLE_FAILED = "debug_cycle_failed"

    # Test execution events
    TESTS_RUNNING = "tests_running"
    TESTS_PASSED = "tests_passed"
    TESTS_FAILED = "tests_failed"
    GENERATION_COMPLETE = "generation_complete"

    # UX Review events
    UX_REVIEW_STARTED = "ux_review_started"
    UX_REVIEW_COMPLETE = "ux_review_complete"
    UX_ISSUE_FOUND = "ux_issue_found"
    UX_RECOMMENDATION = "ux_recommendation"

    # Documentation events
    DOCS_GENERATION_STARTED = "docs_generation_started"
    DOCS_GENERATED = "docs_generated"
    DOCS_UPDATED = "docs_updated"

    # Playwright E2E visual testing events
    PLAYWRIGHT_E2E_STARTED = "playwright_e2e_started"
    PLAYWRIGHT_E2E_PASSED = "playwright_e2e_passed"
    PLAYWRIGHT_E2E_FAILED = "playwright_e2e_failed"
    PLAYWRIGHT_SCREENSHOT_ANALYZED = "playwright_screenshot_analyzed"
    PLAYWRIGHT_DEBUG_PLAN_CREATED = "playwright_debug_plan_created"

    # Document Registry events
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_CONSUMED = "document_consumed"
    DEBUG_REPORT_CREATED = "debug_report_created"
    IMPLEMENTATION_PLAN_CREATED = "implementation_plan_created"
    TEST_SPEC_CREATED = "test_spec_created"
    QUALITY_REPORT_CREATED = "quality_report_created"

    # Docker Swarm Events
    SWARM_INIT_REQUESTED = "swarm_init_requested"
    SWARM_INITIALIZED = "swarm_initialized"
    SWARM_INIT_FAILED = "swarm_init_failed"
    SECRET_CREATE_REQUESTED = "secret_create_requested"
    SECRET_CREATED = "secret_created"
    SECRET_CREATE_FAILED = "secret_create_failed"
    SERVICE_DEPLOY_REQUESTED = "service_deploy_requested"
    SERVICE_DEPLOYED = "service_deployed"
    SERVICE_DEPLOY_FAILED = "service_deploy_failed"

    # Environment Report Events (API keys, secrets validation)
    ENV_REPORT_REQUESTED = "env_report_requested"
    ENV_REPORT_COMPLETE = "env_report_complete"
    ENV_MISSING_REQUIRED = "env_missing_required"

    # Docker Build Events (for GordonBuildAgent)
    DOCKER_BUILD_REQUESTED = "docker_build_requested"
    DOCKER_BUILD_STARTED = "docker_build_started"
    DOCKER_BUILD_SUCCEEDED = "docker_build_succeeded"
    DOCKER_BUILD_FAILED = "docker_build_failed"
    DOCKER_BUILD_FIX_APPLIED = "docker_build_fix_applied"

    # Convergence and Persistent Deployment Events
    CONVERGENCE_ACHIEVED = "convergence_achieved"  # All criteria met
    PERSISTENT_DEPLOY_STARTED = "persistent_deploy_started"
    PERSISTENT_DEPLOY_READY = "persistent_deploy_ready"
    PERSISTENT_DEPLOY_FAILED = "persistent_deploy_failed"

    # Development Container Events (live VNC during generation)
    SCAFFOLDING_COMPLETE = "scaffolding_complete"
    DEV_CONTAINER_STARTED = "dev_container_started"
    DEV_CONTAINER_READY = "dev_container_ready"
    DEV_SERVER_STARTED = "dev_server_started"
    DEV_CONTAINER_STOPPED = "dev_container_stopped"

    # Verification Events (Multi-Agent Debate for Completeness Check)
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"

    # =========================================================================
    # Fullstack Verification Events (Continuous Feedback Loop)
    # =========================================================================
    FULLSTACK_CHECK_STARTED = "fullstack_check_started"
    FULLSTACK_INCOMPLETE = "fullstack_incomplete"  # Missing components → Architect refines
    FULLSTACK_VERIFIED = "fullstack_verified"  # TERMINATION CONDITION: All components working
    CONTRACTS_REFINEMENT_NEEDED = "contracts_refinement_needed"  # Explicit request to Architect
    FUNGUS_CONTEXT_READY = "fungus_context_ready"  # FungusWorker found good context

    # Async Service Events (E2E/UX run continuously parallel to Phase 3)
    ASYNC_E2E_STARTED = "async_e2e_started"
    ASYNC_E2E_CYCLE_COMPLETE = "async_e2e_cycle_complete"
    ASYNC_UX_STARTED = "async_ux_started"
    ASYNC_UX_CYCLE_COMPLETE = "async_ux_cycle_complete"
    UX_REVIEW_PASSED = "ux_review_passed"

    # Handoff Events (Event Interpreter Pattern - AutoGen Handoffs)
    # Used by EventInterpreterAgent to delegate tasks to specialist agents
    HANDOFF_TO_GENERATOR = "handoff_to_generator"
    HANDOFF_TO_TESTER = "handoff_to_tester"
    HANDOFF_TO_VALIDATOR = "handoff_to_validator"
    HANDOFF_TO_DEPLOYER = "handoff_to_deployer"
    HANDOFF_TO_DEBUGGER = "handoff_to_debugger"
    HANDOFF_TO_UX_REVIEWER = "handoff_to_ux_reviewer"
    HANDOFF_COMPLETE = "handoff_complete"
    HANDOFF_FAILED = "handoff_failed"
    ESCALATE_TO_HUMAN = "escalate_to_human"

    # Event Interpreter Events (Triage Agent lifecycle)
    TRIAGE_STARTED = "triage_started"
    TRIAGE_ROUTING_DECISION = "triage_routing_decision"
    TRIAGE_QUEUE_EMPTY = "triage_queue_empty"

    # =========================================================================
    # Full-Stack Autonomy Events (Database, API, Auth, Infrastructure)
    # =========================================================================

    # Database Schema Events (Prisma, SQLAlchemy, Drizzle)
    DATABASE_SCHEMA_GENERATED = "database_schema_generated"
    DATABASE_SCHEMA_FAILED = "database_schema_failed"  # Task 10: Backend failure event
    DATABASE_MIGRATION_NEEDED = "database_migration_needed"
    DATABASE_MIGRATION_COMPLETE = "database_migration_complete"
    DATABASE_MIGRATION_FAILED = "database_migration_failed"
    DATABASE_SEED_STARTED = "database_seed_started"
    DATABASE_SEED_COMPLETE = "database_seed_complete"
    DATABASE_SEED_FAILED = "database_seed_failed"
    DATABASE_CONNECTION_VERIFIED = "database_connection_verified"
    DATABASE_CONNECTION_FAILED = "database_connection_failed"

    # API Generation Events (REST endpoints from contracts)
    API_ROUTES_GENERATED = "api_routes_generated"
    API_GENERATION_FAILED = "api_generation_failed"  # Task 10: Backend failure event
    API_ENDPOINT_CREATED = "api_endpoint_created"
    API_ENDPOINT_FAILED = "api_endpoint_failed"
    API_TYPES_UPDATED = "api_types_updated"
    API_CLIENT_GENERATED = "api_client_generated"
    API_MIDDLEWARE_GENERATED = "api_middleware_generated"
    API_VALIDATION_SCHEMAS_GENERATED = "api_validation_schemas_generated"

    # WebSocket Generation Events (Real-time features)
    WEBSOCKET_HANDLER_GENERATED = "websocket_handler_generated"
    WEBSOCKET_GENERATION_FAILED = "websocket_generation_failed"
    WEBSOCKET_HANDLER_NEEDED = "websocket_handler_needed"
    REALTIME_FEATURE_REQUESTED = "realtime_feature_requested"
    REALTIME_FEATURE_COMPLETE = "realtime_feature_complete"

    # Redis Pub/Sub Events (Scaling and caching)
    REDIS_PUBSUB_CONFIGURED = "redis_pubsub_configured"
    REDIS_SETUP_FAILED = "redis_setup_failed"
    REDIS_SETUP_NEEDED = "redis_setup_needed"
    REDIS_CACHE_CONFIGURED = "redis_cache_configured"
    REDIS_QUEUE_CONFIGURED = "redis_queue_configured"

    # =========================================================================
    # Messaging Platform Events (WhatsApp-like Real-time Messaging)
    # =========================================================================

    # Group Management Events
    GROUP_MANAGEMENT_NEEDED = "group_management_needed"
    GROUP_CREATED = "group_created"
    GROUP_UPDATED = "group_updated"
    GROUP_DELETED = "group_deleted"
    GROUP_MEMBER_ADDED = "group_member_added"
    GROUP_MEMBER_REMOVED = "group_member_removed"
    GROUP_ADMIN_CHANGED = "group_admin_changed"
    GROUP_MANAGEMENT_FAILED = "group_management_failed"

    # Presence Tracking Events
    PRESENCE_TRACKING_NEEDED = "presence_tracking_needed"
    PRESENCE_UPDATED = "presence_updated"
    PRESENCE_ONLINE = "presence_online"
    PRESENCE_OFFLINE = "presence_offline"
    PRESENCE_TYPING_STARTED = "presence_typing_started"
    PRESENCE_TYPING_STOPPED = "presence_typing_stopped"
    PRESENCE_TRACKING_FAILED = "presence_tracking_failed"

    # Read Receipt Events
    READ_RECEIPT_SENT = "read_receipt_sent"
    READ_RECEIPT_DELIVERED = "read_receipt_delivered"
    READ_RECEIPT_READ = "read_receipt_read"

    # End-to-End Encryption Events
    ENCRYPTION_REQUIRED = "encryption_required"
    E2EE_KEY_EXCHANGE_STARTED = "e2ee_key_exchange_started"
    E2EE_KEY_EXCHANGE_COMPLETE = "e2ee_key_exchange_complete"
    E2EE_CONFIGURED = "e2ee_configured"
    E2EE_MESSAGE_ENCRYPTED = "e2ee_message_encrypted"
    E2EE_MESSAGE_DECRYPTED = "e2ee_message_decrypted"
    E2EE_SETUP_FAILED = "e2ee_setup_failed"
    E2EE_KEY_ROTATION_NEEDED = "e2ee_key_rotation_needed"

    # Media Handling Events (for future MediaHandlerAgent)
    MEDIA_UPLOAD_STARTED = "media_upload_started"
    MEDIA_UPLOAD_COMPLETE = "media_upload_complete"
    MEDIA_UPLOAD_FAILED = "media_upload_failed"
    MEDIA_THUMBNAIL_GENERATED = "media_thumbnail_generated"

    # Voice/Video Calling Events (for future CallHandlerAgent)
    CALL_INITIATED = "call_initiated"
    CALL_ACCEPTED = "call_accepted"
    CALL_REJECTED = "call_rejected"
    CALL_ENDED = "call_ended"
    CALL_HANDLING_REQUIRED = "call_handling_required"

    # Authentication Events (JWT, OAuth2, Session)
    AUTH_SETUP_STARTED = "auth_setup_started"
    AUTH_SETUP_COMPLETE = "auth_setup_complete"
    AUTH_SETUP_FAILED = "auth_setup_failed"
    AUTH_CONFIG_UPDATED = "auth_config_updated"  # Task 10: Auth config change event
    AUTH_JWT_CONFIGURED = "auth_jwt_configured"
    AUTH_OAUTH_CONFIGURED = "auth_oauth_configured"
    AUTH_SESSION_CONFIGURED = "auth_session_configured"
    AUTH_HOOKS_GENERATED = "auth_hooks_generated"
    AUTH_MIDDLEWARE_GENERATED = "auth_middleware_generated"

    # Authorization Events (RBAC)
    RBAC_ROLES_DEFINED = "rbac_roles_defined"
    RBAC_PERMISSIONS_CONFIGURED = "rbac_permissions_configured"
    RBAC_MIDDLEWARE_GENERATED = "rbac_middleware_generated"

    # Environment & Infrastructure Events
    ENV_CONFIG_GENERATED = "env_config_generated"
    ENV_SECRETS_GENERATED = "env_secrets_generated"
    ENV_TEMPLATE_CREATED = "env_template_created"
    ENV_UPDATE_NEEDED = "env_update_needed"  # Task 10: Trigger .env update
    DOCKER_COMPOSE_GENERATED = "docker_compose_generated"
    DOCKER_COMPOSE_READY = "docker_compose_ready"
    DOCKER_CONFIG_NEEDED = "docker_config_needed"  # Task 10: Request Docker setup
    CI_PIPELINE_CREATED = "ci_pipeline_created"
    CI_PIPELINE_NEEDED = "ci_pipeline_needed"  # Task 10: Request CI/CD setup
    CI_WORKFLOW_GENERATED = "ci_workflow_generated"
    DEPLOY_PIPELINE_CREATED = "deploy_pipeline_created"
    INFRASTRUCTURE_READY = "infrastructure_ready"
    ENV_CONFIG_FAILED = "env_config_failed"  # Task 19: Infrastructure agent failure

    # Contracts Events (Phase 1 Architect outputs)
    CONTRACTS_GENERATED = "contracts_generated"
    CONTRACTS_UPDATED = "contracts_updated"
    SCHEMA_UPDATE_NEEDED = "schema_update_needed"
    API_UPDATE_NEEDED = "api_update_needed"
    AUTH_REQUIRED = "auth_required"
    ROLE_DEFINITION_NEEDED = "role_definition_needed"
    PROJECT_SCAFFOLDED = "project_scaffolded"

    # =========================================================================
    # No-Mock Policy Events (Anti-Mock Validation)
    # =========================================================================
    MOCK_DETECTED = "mock_detected"
    MOCK_REPLACEMENT_NEEDED = "mock_replacement_needed"
    MOCK_REPLACED = "mock_replaced"
    MOCK_VALIDATION_STARTED = "mock_validation_started"
    MOCK_VALIDATION_PASSED = "mock_validation_passed"
    MOCK_VALIDATION_FAILED = "mock_validation_failed"

    # =========================================================================
    # Security Scanning Events (OWASP, Vulnerability Detection)
    # =========================================================================
    SECURITY_SCAN_STARTED = "security_scan_started"
    SECURITY_SCAN_PASSED = "security_scan_passed"
    SECURITY_SCAN_FAILED = "security_scan_failed"
    VULNERABILITY_DETECTED = "vulnerability_detected"
    SECRET_LEAKED = "secret_leaked"  # API key/password found in code
    SECURITY_FIX_NEEDED = "security_fix_needed"

    # =========================================================================
    # Dependency Management Events (npm audit, License Compliance)
    # =========================================================================
    DEPENDENCY_CHECK_STARTED = "dependency_check_started"
    DEPENDENCY_CHECK_PASSED = "dependency_check_passed"
    DEPENDENCY_OUTDATED = "dependency_outdated"
    DEPENDENCY_UPDATED = "dependency_updated"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    DEPENDENCY_VULNERABILITY = "dependency_vulnerability"
    LICENSE_ISSUE_FOUND = "license_issue_found"

    # =========================================================================
    # Performance Analysis Events (Bundle Size, Lighthouse, Core Web Vitals)
    # =========================================================================
    PERFORMANCE_ANALYSIS_STARTED = "performance_analysis_started"
    PERFORMANCE_BENCHMARK_PASSED = "performance_benchmark_passed"
    PERFORMANCE_ISSUE_DETECTED = "performance_issue_detected"
    BUNDLE_SIZE_WARNING = "bundle_size_warning"
    LIGHTHOUSE_SCORE_LOW = "lighthouse_score_low"

    # =========================================================================
    # Accessibility Events (WCAG Compliance, A11y Testing)
    # =========================================================================
    A11Y_SCAN_STARTED = "a11y_scan_started"
    A11Y_TEST_PASSED = "a11y_test_passed"
    A11Y_ISSUE_FOUND = "a11y_issue_found"
    WCAG_VIOLATION = "wcag_violation"

    # =========================================================================
    # API Documentation Events (OpenAPI, Swagger)
    # =========================================================================
    API_DOCS_GENERATION_STARTED = "api_docs_generation_started"
    API_DOCS_GENERATED = "api_docs_generated"
    OPENAPI_SPEC_CREATED = "openapi_spec_created"

    # =========================================================================
    # Localization Events (i18n, Translations)
    # =========================================================================
    I18N_SETUP_STARTED = "i18n_setup_started"
    I18N_CONFIGURED = "i18n_configured"
    TRANSLATION_KEYS_EXTRACTED = "translation_keys_extracted"
    TRANSLATION_NEEDED = "translation_needed"
    LOCALIZATION_COMPLETE = "localization_complete"

    # =========================================================================
    # Cell Colony Events (Autonomous Microservice Deployment System)
    # =========================================================================

    # Cell Lifecycle Events
    CELL_CREATED = "cell_created"
    CELL_INITIALIZING = "cell_initializing"
    CELL_BUILDING = "cell_building"
    CELL_DEPLOYING = "cell_deploying"
    CELL_READY = "cell_ready"
    CELL_DEGRADED = "cell_degraded"
    CELL_FAILURE_DETECTED = "cell_failure_detected"
    CELL_RECOVERING = "cell_recovering"
    CELL_TERMINATED = "cell_terminated"

    # Cell Health Events
    CELL_HEALTH_CHECK = "cell_health_check"
    CELL_HEALTH_PASSED = "cell_health_passed"
    CELL_HEALTH_FAILED = "cell_health_failed"
    CELL_HEALTH_SCORE_UPDATED = "cell_health_score_updated"

    # Cell Mutation Events (Self-Healing via LLM Code Fixes)
    CELL_MUTATION_REQUESTED = "cell_mutation_requested"
    CELL_MUTATION_STARTED = "cell_mutation_started"
    CELL_MUTATION_APPLIED = "cell_mutation_applied"
    CELL_MUTATION_FAILED = "cell_mutation_failed"
    CELL_MUTATION_REJECTED = "cell_mutation_rejected"
    CELL_ROLLBACK_STARTED = "cell_rollback_started"
    CELL_ROLLBACK_COMPLETE = "cell_rollback_complete"
    CELL_ROLLBACK_FAILED = "cell_rollback_failed"

    # Cell Autophagy Events (Graceful Termination after Max Failures)
    CELL_AUTOPHAGY_TRIGGERED = "cell_autophagy_triggered"
    CELL_AUTOPHAGY_COMPLETE = "cell_autophagy_complete"

    # Colony-Level Events (Orchestrator for Multiple Cells)
    COLONY_CREATED = "colony_created"
    COLONY_HEALTH_CHECK = "colony_health_check"
    COLONY_REBALANCE_NEEDED = "colony_rebalance_needed"
    COLONY_REBALANCE_STARTED = "colony_rebalance_started"
    COLONY_REBALANCE_COMPLETE = "colony_rebalance_complete"
    COLONY_SCALE_UP_NEEDED = "colony_scale_up_needed"
    COLONY_SCALE_UP_COMPLETE = "colony_scale_up_complete"
    COLONY_SCALE_DOWN_NEEDED = "colony_scale_down_needed"
    COLONY_SCALE_DOWN_COMPLETE = "colony_scale_down_complete"
    COLONY_CONVERGENCE_ACHIEVED = "colony_convergence_achieved"

    # Human-in-the-Loop Events (Critical Mutation Approval)
    MUTATION_APPROVAL_REQUIRED = "mutation_approval_required"
    USER_MUTATION_APPROVED = "user_mutation_approved"
    USER_MUTATION_REJECTED = "user_mutation_rejected"
    MUTATION_TIMEOUT_EXPIRED = "mutation_timeout_expired"
    CRITICAL_MUTATION_ALERT = "critical_mutation_alert"
    OPERATOR_NOTIFICATION = "operator_notification"

    # =========================================================================
    # MCP Orchestrator Events (LLM-planned Tool Execution)
    # =========================================================================

    # MCP Task Lifecycle Events
    MCP_TASK_STARTED = "mcp_task_started"  # Natural language task received
    MCP_TASK_PLANNED = "mcp_task_planned"  # LLM plan created
    MCP_TASK_COMPLETE = "mcp_task_complete"  # Task execution finished successfully
    MCP_TASK_FAILED = "mcp_task_failed"  # Task execution failed

    # MCP Tool Execution Events
    MCP_TOOL_STARTED = "mcp_tool_started"  # Individual tool started
    MCP_TOOL_COMPLETE = "mcp_tool_complete"  # Individual tool finished
    MCP_TOOL_FAILED = "mcp_tool_failed"  # Individual tool failed
    MCP_TOOL_RECOVERY = "mcp_tool_recovery"  # Recovery plan triggered

    # Docker Tool Events (via MCP Orchestrator)
    MCP_DOCKER_CONTAINER_STARTED = "mcp_docker_container_started"
    MCP_DOCKER_CONTAINER_STOPPED = "mcp_docker_container_stopped"
    MCP_DOCKER_COMPOSE_UP = "mcp_docker_compose_up"
    MCP_DOCKER_COMPOSE_DOWN = "mcp_docker_compose_down"
    MCP_DOCKER_IMAGE_PULLED = "mcp_docker_image_pulled"

    # Git Tool Events (via MCP Orchestrator)
    MCP_GIT_COMMIT_CREATED = "mcp_git_commit_created"
    MCP_GIT_BRANCH_CREATED = "mcp_git_branch_created"
    MCP_GIT_PUSH_COMPLETE = "mcp_git_push_complete"

    # NPM Tool Events (via MCP Orchestrator)
    MCP_NPM_INSTALL_COMPLETE = "mcp_npm_install_complete"
    MCP_NPM_BUILD_COMPLETE = "mcp_npm_build_complete"
    MCP_NPM_TEST_COMPLETE = "mcp_npm_test_complete"

    # Filesystem Tool Events (via MCP Orchestrator)
    MCP_FILE_CREATED = "mcp_file_created"
    MCP_FILE_MODIFIED = "mcp_file_modified"
    MCP_DIRECTORY_CREATED = "mcp_directory_created"

    # Cell Source Events (Code Generation / Repository Clone)
    CELL_CODE_GENERATION_STARTED = "cell_code_generation_started"
    CELL_CODE_GENERATION_COMPLETE = "cell_code_generation_complete"
    CELL_CODE_GENERATION_FAILED = "cell_code_generation_failed"
    CELL_REPO_CLONE_STARTED = "cell_repo_clone_started"
    CELL_REPO_CLONE_COMPLETE = "cell_repo_clone_complete"
    CELL_REPO_CLONE_FAILED = "cell_repo_clone_failed"

    # Cell Container Events (Docker Build/Push)
    CELL_IMAGE_BUILD_STARTED = "cell_image_build_started"
    CELL_IMAGE_BUILD_COMPLETE = "cell_image_build_complete"
    CELL_IMAGE_BUILD_FAILED = "cell_image_build_failed"
    CELL_IMAGE_PUSH_STARTED = "cell_image_push_started"
    CELL_IMAGE_PUSH_COMPLETE = "cell_image_push_complete"
    CELL_IMAGE_SIGNED = "cell_image_signed"

    # Kubernetes Deployment Events
    CELL_K8S_DEPLOY_STARTED = "cell_k8s_deploy_started"
    CELL_K8S_DEPLOY_COMPLETE = "cell_k8s_deploy_complete"
    CELL_K8S_DEPLOY_FAILED = "cell_k8s_deploy_failed"
    CELL_K8S_SERVICE_CREATED = "cell_k8s_service_created"
    CELL_K8S_POD_READY = "cell_k8s_pod_ready"
    CELL_K8S_POD_FAILED = "cell_k8s_pod_failed"

    # Community Portal Events (Marketplace)
    CELL_PUBLISHED = "cell_published"
    CELL_UNPUBLISHED = "cell_unpublished"
    CELL_VERSION_UPLOADED = "cell_version_uploaded"
    CELL_IMPORTED = "cell_imported"
    CELL_REVIEW_SUBMITTED = "cell_review_submitted"
    CELL_REPORTED = "cell_reported"
    CELL_QUARANTINED = "cell_quarantined"
    CELL_QUARANTINE_RELEASED = "cell_quarantine_released"

    # =========================================================================
    # Fungus Completeness Events (Requirement Fulfillment Verification)
    # =========================================================================
    REQUIREMENT_CHECK_REQUESTED = "requirement_check_requested"
    REQUIREMENT_COMPLETENESS_REPORT = "requirement_completeness_report"
    REQUIREMENT_TEST_MISSING = "requirement_test_missing"
    REQUIREMENT_ENV_MISSING = "requirement_env_missing"
    REQUIREMENT_ARTIFACT_MISSING = "requirement_artifact_missing"
    FUNGUS_SIMULATION_RESTARTED = "fungus_simulation_restarted"

    # =========================================================================
    # Fungus Validation Events (Autonomous Code Quality via MCMP Simulation)
    # =========================================================================
    FUNGUS_VALIDATION_STARTED = "fungus_validation_started"
    FUNGUS_VALIDATION_ISSUE = "fungus_validation_issue"
    FUNGUS_VALIDATION_PASSED = "fungus_validation_passed"
    FUNGUS_VALIDATION_REPORT = "fungus_validation_report"
    FUNGUS_VALIDATION_STOPPED = "fungus_validation_stopped"

    # =========================================================================
    # Fungus Memory Events (Memory-Augmented MCMP Search)
    # =========================================================================
    FUNGUS_MEMORY_STARTED = "fungus_memory_started"
    FUNGUS_MEMORY_STOPPED = "fungus_memory_stopped"
    FUNGUS_MEMORY_CONTEXT_ENRICHED = "fungus_memory_context_enriched"
    FUNGUS_MEMORY_PATTERN_FOUND = "fungus_memory_pattern_found"
    FUNGUS_MEMORY_FIX_SUGGESTED = "fungus_memory_fix_suggested"
    FUNGUS_MEMORY_STORED = "fungus_memory_stored"
    FUNGUS_MEMORY_REPORT = "fungus_memory_report"

    # =========================================================================
    # Git Push Agent Events (Autonomous Git Operations after Generation)
    # =========================================================================
    GIT_PUSH_STARTED = "git_push_started"
    GIT_PUSH_SUCCEEDED = "git_push_succeeded"
    GIT_PUSH_FAILED = "git_push_failed"
    GIT_COMMIT_CREATED = "git_commit_created"
    GIT_BRANCH_CREATED = "git_branch_created"
    GIT_REPO_INITIALIZED = "git_repo_initialized"

    # =========================================================================
    # Pattern Learning Events (Supermemory RAG Integration)
    # =========================================================================
    PATTERN_LEARNED = "pattern_learned"
    PATTERN_RETRIEVED = "pattern_retrieved"
    PATTERN_MATCH_FOUND = "pattern_match_found"

    # =========================================================================
    # Classification Events (LLM-based Category Detection)
    # =========================================================================
    CLASSIFICATION_COMPLETED = "classification_completed"
    CLASSIFICATION_CACHE_HIT = "classification_cache_hit"
    CLASSIFICATION_LLM_FALLBACK = "classification_llm_fallback"

    # =========================================================================
    # Task Progress Events (Dashboard Task Visibility)
    # =========================================================================
    TASK_PROGRESS_UPDATE = "task_progress_update"

    # =========================================================================
    # Epic Orchestrator Integration (Universal SoM Bridge)
    # =========================================================================
    EPIC_EXECUTION_STARTED = "epic_execution_started"
    EPIC_TASK_STARTED = "epic_task_started"
    EPIC_TASK_COMPLETED = "epic_task_completed"
    EPIC_TASK_FAILED = "epic_task_failed"
    EPIC_PHASE_COMPLETED = "epic_phase_completed"
    EPIC_EXECUTION_COMPLETED = "epic_execution_completed"
    EPIC_CHECKPOINT_REACHED = "epic_checkpoint_reached"

    # Task validation (post-epic fix loop)
    TASK_VALIDATION_COMPLETE = "task_validation_complete"

    # =========================================================================
    # Differential Analysis Events (Documentation vs Code Gap Detection)
    # =========================================================================
    DIFFERENTIAL_ANALYSIS_STARTED = "differential_analysis_started"
    DIFFERENTIAL_ANALYSIS_COMPLETE = "differential_analysis_complete"
    DIFFERENTIAL_GAP_FOUND = "differential_gap_found"
    DIFFERENTIAL_COVERAGE_REPORT = "differential_coverage_report"
    DIFFERENTIAL_EPIC_VALIDATED = "differential_epic_validated"
    DIFFERENTIAL_EPIC_FAILED = "differential_epic_failed"
    DIFFERENTIAL_FIX_COMPLETE = "differential_fix_complete"

    # Cross-Layer Validation Events (Frontend ↔ Backend consistency)
    CROSS_LAYER_VALIDATION_STARTED = "cross_layer_validation_started"
    CROSS_LAYER_VALIDATION_ISSUE = "cross_layer_validation_issue"
    CROSS_LAYER_VALIDATION_COMPLETE = "cross_layer_validation_complete"
    CROSS_LAYER_VALIDATION_REPORT = "cross_layer_validation_report"

    # =========================================================================
    # Emergent System Events (TreeQuest, ShinkaEvolve, Minibook, OpenClaw)
    # =========================================================================

    # Package Ingestion Events (Dynamic project watcher)
    PACKAGE_READY = "package_ready"  # New project package parsed and ready
    PACKAGE_INGESTION_FAILED = "package_ingestion_failed"

    # TreeQuest Verification Events (AB-MCTS code↔docs verification)
    TREEQUEST_VERIFICATION_STARTED = "treequest_verification_started"
    TREEQUEST_VERIFICATION_COMPLETE = "treequest_verification_complete"
    TREEQUEST_FINDING_CRITICAL = "treequest_finding_critical"  # High severity finding
    TREEQUEST_FINDING_WARNING = "treequest_finding_warning"  # Medium severity
    TREEQUEST_FINDING_INFO = "treequest_finding_info"  # Low severity/informational
    TREEQUEST_NO_ISSUES = "treequest_no_issues"  # Clean verification pass

    # ShinkaEvolve Events (Evolutionary code improvement)
    EVOLUTION_REQUESTED = "evolution_requested"  # Standard fixers exhausted
    EVOLUTION_STARTED = "evolution_started"
    EVOLUTION_GENERATION_COMPLETE = "evolution_generation_complete"  # One generation done
    EVOLUTION_IMPROVED = "evolution_improved"  # Score improved
    EVOLUTION_CONVERGED = "evolution_converged"  # Best solution found
    EVOLUTION_FAILED = "evolution_failed"  # No improvement after max generations
    EVOLUTION_APPLIED = "evolution_applied"  # Evolved code written back

    # Minibook Collaboration Events (Agent-to-agent discussion)
    MINIBOOK_CONNECTED = "minibook_connected"
    MINIBOOK_DISCONNECTED = "minibook_disconnected"
    MINIBOOK_POST_CREATED = "minibook_post_created"
    MINIBOOK_COMMENT_ADDED = "minibook_comment_added"
    MINIBOOK_AGENT_MENTIONED = "minibook_agent_mentioned"  # @mention notification
    MINIBOOK_DISCUSSION_RESOLVED = "minibook_discussion_resolved"

    # DaveLovable Bridge Events (Vibe Coder UI)
    DAVELOVABLE_PROJECT_CREATED = "davelovable_project_created"
    DAVELOVABLE_FILES_PUSHED = "davelovable_files_pushed"
    DAVELOVABLE_PREVIEW_READY = "davelovable_preview_ready"
    DAVELOVABLE_CHAT_MESSAGE = "davelovable_chat_message"

    # OpenClaw Events (External control via WhatsApp/Slack/Discord)
    OPENCLAW_COMMAND_RECEIVED = "openclaw_command_received"
    OPENCLAW_STATUS_REQUESTED = "openclaw_status_requested"
    OPENCLAW_NOTIFICATION_SENT = "openclaw_notification_sent"

    # Security Events (emergent)
    SECURITY_VULNERABILITY = "security_vulnerability"

    # Pipeline Lifecycle Events
    PIPELINE_STARTED = "pipeline_started"  # Full emergent pipeline kicked off
    PIPELINE_PHASE_CHANGED = "pipeline_phase_changed"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"


# ---------------------------------------------------------------------------
# Correlation / Tracing Context
# ---------------------------------------------------------------------------

# Context vars for automatic correlation ID propagation
_current_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_correlation_id", default=None
)
_current_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_span_id", default=None
)


def generate_trace_id() -> str:
    """Generate a short, sortable trace ID: t-<8 hex chars>."""
    return f"t-{uuid.uuid4().hex[:8]}"


def generate_span_id() -> str:
    """Generate a short span ID: s-<6 hex chars>."""
    return f"s-{uuid.uuid4().hex[:6]}"


def get_current_correlation_id() -> Optional[str]:
    """Get the active correlation ID from context."""
    return _current_correlation_id.get()


def set_current_correlation_id(cid: str) -> contextvars.Token:
    """Set the active correlation ID in context."""
    return _current_correlation_id.set(cid)


class PipelineTrace:
    """
    Context manager for pipeline tracing with correlation IDs.

    All events published within a PipelineTrace scope automatically get
    the same correlation_id, making it trivial to trace an entire pipeline
    run across dozens of agents and hundreds of events.

    Usage::

        async with PipelineTrace("MyPipeline") as trace:
            await bus.publish(Event(type=EventType.BUILD_STARTED, source="builder"))
            # event.correlation_id == trace.trace_id automatically

        # Nested spans:
        async with PipelineTrace("OuterPipeline") as outer:
            async with PipelineTrace("InnerVerification", parent_trace=outer) as inner:
                # inner.trace_id is unique, inner.parent_id == outer.trace_id
                ...
    """

    def __init__(self, name: str, parent_trace: Optional["PipelineTrace"] = None):
        self.name = name
        self.trace_id = generate_trace_id()
        self.span_id = generate_span_id()
        self.parent_id = parent_trace.trace_id if parent_trace else None
        self._token_cid: Optional[contextvars.Token] = None
        self._token_sid: Optional[contextvars.Token] = None
        self._start_time: Optional[datetime] = None

    async def __aenter__(self) -> "PipelineTrace":
        self._start_time = datetime.now()
        self._token_cid = _current_correlation_id.set(self.trace_id)
        self._token_sid = _current_span_id.set(self.span_id)
        logger.info(
            "trace_started",
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_id=self.parent_id,
            name=self.name,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        logger.info(
            "trace_ended",
            trace_id=self.trace_id,
            span_id=self.span_id,
            name=self.name,
            duration_seconds=round(duration, 2),
            error=str(exc_val) if exc_val else None,
        )
        if self._token_cid is not None:
            _current_correlation_id.reset(self._token_cid)
        if self._token_sid is not None:
            _current_span_id.reset(self._token_sid)
        return False  # Don't suppress exceptions


@dataclass
class Event:
    """
    An event in the system.

    Events now support typed payloads and prompt hints for better
    type safety and Claude guidance.

    Usage:
        # Old way (still works):
        errors = event.data.get("errors", [])

        # New way (type-safe):
        if event.typed:
            errors = event.typed.errors  # IDE autocomplete!

        # With prompt hints:
        if event.prompt_hints:
            prompt_section = event.prompt_hints.to_prompt_section()
    """
    type: EventType
    source: str  # Agent or component that generated the event
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict = field(default_factory=dict)

    # Optional fields for specific event types
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    success: bool = True

    # Tracing / Correlation
    correlation_id: Optional[str] = None  # Links events in the same pipeline run
    parent_id: Optional[str] = None       # Parent trace for nested spans
    span_id: Optional[str] = None         # Unique span within a trace

    # NEW: Typed payload support (Phase 11)
    _typed_payload: Any = field(default=None, repr=False)
    _prompt_hints: Any = field(default=None, repr=False)

    def __post_init__(self):
        """Auto-parse typed payload if not provided and validate data structure."""
        # Auto-inherit correlation ID from context if not explicitly set
        if self.correlation_id is None:
            self.correlation_id = _current_correlation_id.get()
        if self.span_id is None:
            self.span_id = _current_span_id.get()

        # Auto-parse typed payload
        if self._typed_payload is None and self.data:
            try:
                from .event_payloads import get_typed_payload
                self._typed_payload = get_typed_payload(self.type, self.data)
            except ImportError:
                pass  # event_payloads not available yet

        # Validate data structure for known event types (Phase 12)
        self._validate_event_data()

    @property
    def typed(self) -> Any:
        """
        Get typed payload for this event.

        Returns None if no typed payload is registered for this event type
        or if parsing failed.
        """
        return self._typed_payload

    @property
    def prompt_hints(self) -> Any:
        """
        Get prompt hints for this event.

        Returns existing hints or builds them on-demand.
        """
        if self._prompt_hints is not None:
            return self._prompt_hints

        # Try to build hints on-demand
        try:
            from .prompt_hints import build_hints_from_event
            self._prompt_hints = build_hints_from_event(self)
        except ImportError:
            pass  # prompt_hints not available yet

        return self._prompt_hints

    @prompt_hints.setter
    def prompt_hints(self, value: Any) -> None:
        """Set prompt hints."""
        self._prompt_hints = value

    def _validate_event_data(self) -> None:
        """
        Validate event data structure for known event types.

        Logs warnings for invalid data structures to catch errors early.
        This helps identify inconsistent event publishing in development.
        """
        # Skip validation if no data or if typed payload was successfully parsed
        if not self.data or self._typed_payload is not None:
            return

        # Define expected fields per event type for basic validation
        validation_rules: dict[EventType, dict] = {
            EventType.MOCK_DETECTED: {
                "expected_field": "violations",
                "expected_type": list,
                "warning": "MOCK_DETECTED event should have 'violations' list",
            },
            EventType.BUILD_FAILED: {
                "expected_field": "errors",
                "expected_type": list,
                "warning": "BUILD_FAILED event should have 'errors' list",
                "alt_field": "failures",  # Accept either
            },
            EventType.TYPE_ERROR: {
                "expected_field": "errors",
                "expected_type": list,
                "warning": "TYPE_ERROR event should have 'errors' list",
            },
            EventType.DEBUG_REPORT_CREATED: {
                "expected_field": "doc_id",
                "expected_type": str,
                "warning": "DEBUG_REPORT_CREATED event should have 'doc_id'",
            },
            EventType.QUALITY_REPORT_CREATED: {
                "expected_field": "doc_id",
                "expected_type": str,
                "warning": "QUALITY_REPORT_CREATED event should have 'doc_id'",
            },
        }

        rule = validation_rules.get(self.type)
        if rule:
            field = rule["expected_field"]
            alt_field = rule.get("alt_field")
            expected_type = rule["expected_type"]
            warning = rule["warning"]

            value = self.data.get(field)
            alt_value = self.data.get(alt_field) if alt_field else None

            # Check if expected field exists and has correct type
            if value is None and alt_value is None:
                logger.warning(
                    "event_data_validation_warning",
                    event_type=self.type.value,
                    source=self.source,
                    issue=f"Missing field: {field}",
                    hint=warning,
                )
            elif value is not None and not isinstance(value, expected_type):
                logger.warning(
                    "event_data_validation_warning",
                    event_type=self.type.value,
                    source=self.source,
                    issue=f"Wrong type for {field}: expected {expected_type.__name__}, got {type(value).__name__}",
                    hint=warning,
                )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from event data with fallback to typed payload.

        This provides backward-compatible access while preferring
        typed payload when available.

        Args:
            key: The key to look up
            default: Default value if key not found

        Returns:
            Value from typed payload, data dict, or default
        """
        # Try typed payload first (more reliable)
        if self._typed_payload is not None:
            if hasattr(self._typed_payload, key):
                return getattr(self._typed_payload, key)

        # Fall back to data dict
        return self.data.get(key, default)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "type": self.type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "file_path": self.file_path,
            "error_message": self.error_message,
            "success": self.success,
            "correlation_id": self.correlation_id,
            "parent_id": self.parent_id,
            "span_id": self.span_id,
        }

        # Include typed payload data if available
        if self._typed_payload is not None:
            if hasattr(self._typed_payload, 'to_dict'):
                result["typed_payload"] = self._typed_payload.to_dict()

        return result

    @classmethod
    def with_payload(
        cls,
        type: EventType,
        source: str,
        payload: Any,
        **kwargs
    ) -> "Event":
        """
        Create an Event with a typed payload.

        The payload's data is also stored in the data dict for
        backward compatibility.

        Args:
            type: Event type
            source: Source component
            payload: Typed payload instance
            **kwargs: Additional Event fields

        Returns:
            Event with typed payload
        """
        data = payload.to_dict() if hasattr(payload, 'to_dict') else {}

        return cls(
            type=type,
            source=source,
            data=data,
            _typed_payload=payload,
            **kwargs
        )


# Type for event handlers
EventHandler = Callable[[Event], Any]


class EventBus:
    """
    Central event bus for agent communication.

    Implements pub/sub pattern with:
    - Async event publishing
    - Multiple subscribers per event type
    - Event history for late subscribers
    - WebSocket broadcast capability
    """

    def __init__(self, history_size: int = 1000):
        """
        Initialize the event bus.

        Args:
            history_size: Maximum events to keep in history
        """
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._wildcard_subscribers: list[EventHandler] = []
        self._history: list[Event] = []
        self._history_size = history_size
        self._lock = asyncio.Lock()
        self._websocket_handlers: list[Callable[[Event], Any]] = []

        self.logger = logger.bind(component="event_bus")

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """
        Subscribe to a specific event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async or sync function to call when event occurs
        """
        self._subscribers[event_type].append(handler)
        self.logger.debug("subscriber_added", event_type=event_type.value)

    def subscribe_all(self, handler: EventHandler) -> None:
        """
        Subscribe to all events (wildcard).

        Args:
            handler: Function to call for every event
        """
        self._wildcard_subscribers.append(handler)
        self.logger.debug("wildcard_subscriber_added")

    def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """Remove a subscriber."""
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def add_websocket_handler(self, handler: Callable[[Event], Any]) -> None:
        """Add a handler for WebSocket broadcasting."""
        self._websocket_handlers.append(handler)

    def remove_websocket_handler(self, handler: Callable[[Event], Any]) -> None:
        """Remove a WebSocket handler."""
        if handler in self._websocket_handlers:
            self._websocket_handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event: Event to publish
        """
        async with self._lock:
            # Add to history
            self._history.append(event)
            if len(self._history) > self._history_size:
                self._history = self._history[-self._history_size:]

        # Enhanced logging for visibility
        subscriber_count = len(self._subscribers[event.type]) + len(self._wildcard_subscribers)

        # Warn if no subscribers for important error events (helps debug silent failures)
        if subscriber_count == 0 and event.type.value in (
            "VALIDATION_ERROR", "BROWSER_ERROR", "BUILD_FAILED", "CODE_FIX_NEEDED"
        ):
            self.logger.warning(
                "event_no_subscribers",
                event_type=event.type.value,
                source=event.source,
                message="Event published but no agents subscribed - errors may not be fixed!",
            )

        self.logger.info(
            "[OUT] EVENT_PUBLISHED",
            event_type=event.type.value,
            source=event.source,
            success=event.success,
            data_keys=list(event.data.keys()) if event.data else [],
            subscribers=subscriber_count,
            has_error=bool(event.error_message),
            correlation_id=event.correlation_id,
            span_id=event.span_id,
        )

        # Notify type-specific subscribers
        for handler in self._subscribers[event.type]:
            handler_name = getattr(handler, "__name__", str(handler))
            try:
                self.logger.debug(
                    "[IN] EVENT_DELIVERING",
                    event_type=event.type.value,
                    subscriber=handler_name,
                )
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
                self.logger.debug(
                    "[OK] EVENT_DELIVERED",
                    event_type=event.type.value,
                    subscriber=handler_name,
                )
            except Exception as e:
                self.logger.error(
                    "[ERR] SUBSCRIBER_ERROR",
                    event_type=event.type.value,
                    subscriber=handler_name,
                    error=str(e),
                )

        # Notify wildcard subscribers
        for handler in self._wildcard_subscribers:
            handler_name = getattr(handler, "__name__", str(handler))
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error(
                    "[ERR] WILDCARD_SUBSCRIBER_ERROR",
                    subscriber=handler_name,
                    error=str(e),
                )

        # Broadcast to WebSocket handlers
        for handler in self._websocket_handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error(
                    "[ERR] WEBSOCKET_BROADCAST_ERROR",
                    error=str(e),
                )

    async def publish_many(self, events: list[Event]) -> None:
        """Publish multiple events."""
        for event in events:
            await self.publish(event)

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[Event]:
        """
        Get event history.

        Args:
            event_type: Filter by event type
            since: Only events after this time
            limit: Maximum events to return

        Returns:
            List of events matching criteria
        """
        events = self._history

        if event_type:
            events = [e for e in events if e.type == event_type]

        if since:
            events = [e for e in events if e.timestamp > since]

        return events[-limit:]

    def get_latest(self, event_type: EventType) -> Optional[Event]:
        """Get the most recent event of a type."""
        for event in reversed(self._history):
            if event.type == event_type:
                return event
        return None

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()


# Helper functions for creating common events

def file_event(
    event_type: EventType,
    source: str,
    file_path: str,
    **kwargs,
) -> Event:
    """Create a file-related event."""
    return Event(
        type=event_type,
        source=source,
        file_path=file_path,
        data=kwargs,
    )


def test_event(
    source: str,
    passed: bool,
    test_name: str,
    error: Optional[str] = None,
) -> Event:
    """Create a test result event."""
    return Event(
        type=EventType.TEST_PASSED if passed else EventType.TEST_FAILED,
        source=source,
        success=passed,
        error_message=error,
        data={"test_name": test_name},
    )


def error_event(
    source: str,
    event_type: EventType,
    message: str,
    file_path: Optional[str] = None,
    line: Optional[int] = None,
) -> Event:
    """Create an error event."""
    return Event(
        type=event_type,
        source=source,
        success=False,
        error_message=message,
        file_path=file_path,
        data={"line": line} if line else {},
    )


def agent_event(
    agent_name: str,
    event_type: EventType,
    action: Optional[str] = None,
    **kwargs,
) -> Event:
    """Create an agent lifecycle event."""
    data = {"action": action} if action else {}
    data.update(kwargs)
    return Event(
        type=event_type,
        source=agent_name,
        data=data,
    )


def screen_stream_event(
    source: str,
    event_type: EventType,
    vnc_url: Optional[str] = None,
    container_id: Optional[str] = None,
    **kwargs,
) -> Event:
    """Create a VNC screen streaming event."""
    data = {}
    if vnc_url:
        data["vnc_url"] = vnc_url
    if container_id:
        data["container_id"] = container_id
    data.update(kwargs)
    return Event(
        type=event_type,
        source=source,
        data=data,
    )


def cli_event(
    source: str,
    event_type: EventType,
    call_id: Optional[str] = None,
    prompt: Optional[str] = None,
    response: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
    **kwargs,
) -> Event:
    """Create a CLI monitoring event."""
    data = {}
    if call_id:
        data["call_id"] = call_id
    if prompt:
        data["prompt"] = prompt[:500] if len(prompt) > 500 else prompt  # Truncate for events
    if response:
        data["response"] = response[:500] if len(response) > 500 else response
    if tokens_in is not None:
        data["tokens_in"] = tokens_in
    if tokens_out is not None:
        data["tokens_out"] = tokens_out
    if latency_ms is not None:
        data["latency_ms"] = latency_ms
    if error:
        data["error"] = error
    data.update(kwargs)
    return Event(
        type=event_type,
        source=source,
        success=error is None,
        error_message=error,
        data=data,
    )


def handoff_event(
    source: str,
    target_agent: str,
    original_event_type: str,
    original_event_data: dict,
    reason: str,
    priority: int = 5,
    context: Optional[list] = None,
    **kwargs,
) -> Event:
    """Create a handoff event for Event Interpreter pattern.

    Args:
        source: The agent initiating the handoff (usually "EventInterpreter")
        target_agent: The specialist agent receiving the task
        original_event_type: The original event type being delegated
        original_event_data: Data from the original event
        reason: Why this handoff was made (routing reasoning)
        priority: Task priority (1 = highest, 10 = lowest)
        context: Conversation context for the specialist
    """
    # Map target agent to handoff event type
    handoff_type_map = {
        "GeneratorAgent": EventType.HANDOFF_TO_GENERATOR,
        "TesterTeamAgent": EventType.HANDOFF_TO_TESTER,
        "ValidationTeamAgent": EventType.HANDOFF_TO_VALIDATOR,
        "DeploymentTeamAgent": EventType.HANDOFF_TO_DEPLOYER,
        "ContinuousDebugAgent": EventType.HANDOFF_TO_DEBUGGER,
        "UXDesignAgent": EventType.HANDOFF_TO_UX_REVIEWER,
        "HumanAgent": EventType.ESCALATE_TO_HUMAN,
    }

    event_type = handoff_type_map.get(target_agent, EventType.HANDOFF_COMPLETE)

    data = {
        "target_agent": target_agent,
        "original_event_type": original_event_type,
        "original_event_data": original_event_data,
        "reason": reason,
        "priority": priority,
        "context": context or [],
    }
    data.update(kwargs)

    return Event(
        type=event_type,
        source=source,
        data=data,
    )


def triage_event(
    source: str,
    event_type: EventType,
    routing_decision: Optional[dict] = None,
    queue_size: Optional[int] = None,
    **kwargs,
) -> Event:
    """Create a triage/Event Interpreter lifecycle event.

    Args:
        source: Usually "EventInterpreter"
        event_type: TRIAGE_STARTED, TRIAGE_ROUTING_DECISION, or TRIAGE_QUEUE_EMPTY
        routing_decision: Details about the routing decision made
        queue_size: Current size of the event queue
    """
    data = {}
    if routing_decision:
        data["routing_decision"] = routing_decision
    if queue_size is not None:
        data["queue_size"] = queue_size
    data.update(kwargs)

    return Event(
        type=event_type,
        source=source,
        data=data,
    )


# =============================================================================
# Typed Payload Factory Functions (Phase 12)
# =============================================================================

def build_failed_event(
    source: str,
    errors: list[dict],
    command: Optional[str] = None,
    exit_code: int = 1,
    build_output: Optional[str] = None,
) -> Event:
    """Create BUILD_FAILED event with typed payload.

    Args:
        source: Agent name publishing this event
        errors: List of error dicts with file, line, message
        command: The failing command (e.g., "npm run build")
        exit_code: Process exit code
        build_output: Raw build output (will be parsed)

    Returns:
        Event with BuildFailurePayload attached
    """
    from .event_payloads import BuildFailurePayload

    if build_output:
        payload = BuildFailurePayload.from_build_output(build_output, exit_code)
    else:
        # Determine error type from errors
        is_import_error = any(
            "cannot find module" in str(e.get("message", "")).lower() or
            "import" in str(e.get("message", "")).lower()
            for e in errors
        )
        is_type_error = any(
            "ts(" in str(e.get("message", "")).lower() or
            "type" in str(e.get("message", "")).lower()
            for e in errors
        )

        affected_files = list(set(e.get("file", "") for e in errors if e.get("file")))

        payload = BuildFailurePayload(
            error_count=len(errors),
            errors=errors,
            failing_command=command,
            exit_code=exit_code,
            affected_files=affected_files,
            is_import_error=is_import_error,
            is_type_error=is_type_error,
        )

    return Event.with_payload(
        type=EventType.BUILD_FAILED,
        source=source,
        payload=payload,
        success=False,
        error_message=errors[0].get("message") if errors else "Build failed",
    )


def mock_detected_event(
    source: str,
    violations: list[dict],
) -> Event:
    """Create MOCK_DETECTED event with typed payload.

    Args:
        source: Agent name (usually "ValidatorAgent")
        violations: List of mock violation dicts with file, line, message, severity

    Returns:
        Event with MockViolationPayload attached
    """
    from .event_payloads import MockViolationPayload

    payload = MockViolationPayload.from_violations(violations)

    return Event.with_payload(
        type=EventType.MOCK_DETECTED,
        source=source,
        payload=payload,
        success=payload.error_count == 0,
    )


def type_error_event(
    source: str,
    tsc_output: Optional[str] = None,
    errors: Optional[list[dict]] = None,
) -> Event:
    """Create TYPE_ERROR event with typed payload.

    Args:
        source: Agent name
        tsc_output: Raw TypeScript compiler output (preferred)
        errors: Pre-parsed error list (fallback)

    Returns:
        Event with TypeErrorPayload attached
    """
    from .event_payloads import TypeErrorPayload

    if tsc_output:
        payload = TypeErrorPayload.from_tsc_output(tsc_output)
    else:
        errors_by_file: dict[str, list[dict]] = {}
        for error in (errors or []):
            file_path = error.get("file", "unknown")
            if file_path not in errors_by_file:
                errors_by_file[file_path] = []
            errors_by_file[file_path].append(error)

        payload = TypeErrorPayload(
            error_count=len(errors or []),
            errors=errors or [],
            errors_by_file=errors_by_file,
        )

    return Event.with_payload(
        type=EventType.TYPE_ERROR,
        source=source,
        payload=payload,
        success=False,
    )


def sandbox_test_event(
    source: str,
    passed: bool,
    container_id: Optional[str] = None,
    container_name: Optional[str] = None,
    app_url: Optional[str] = None,
    vnc_url: Optional[str] = None,
    error_message: Optional[str] = None,
    container_logs: Optional[str] = None,
) -> Event:
    """Create SANDBOX_TEST_* event with typed payload.

    Args:
        source: Agent name
        passed: Whether the sandbox test passed
        container_id: Docker container ID
        container_name: Container name
        app_url: URL where the app is running
        vnc_url: VNC stream URL if available
        error_message: Error message if failed
        container_logs: Container output logs

    Returns:
        Event with SandboxTestPayload attached
    """
    from .event_payloads import SandboxTestPayload

    payload = SandboxTestPayload(
        container_id=container_id,
        container_name=container_name,
        passed=passed,
        error_message=error_message,
        app_url=app_url,
        vnc_url=vnc_url,
        container_logs=container_logs[:2000] if container_logs and len(container_logs) > 2000 else container_logs,
    )

    return Event.with_payload(
        type=EventType.SANDBOX_TEST_PASSED if passed else EventType.SANDBOX_TEST_FAILED,
        source=source,
        payload=payload,
        success=passed,
        error_message=error_message,
    )


def debug_report_event(
    source: str,
    doc_id: str,
    issues_found: int = 0,
    screenshots: Optional[list[str]] = None,
    visual_issues: Optional[list[dict]] = None,
    functional_issues: Optional[list[dict]] = None,
    requires_immediate_fix: bool = False,
) -> Event:
    """Create DEBUG_REPORT_CREATED event with typed payload.

    Args:
        source: Agent name (usually "PlaywrightE2EAgent")
        doc_id: Document ID for the debug report
        issues_found: Total number of issues
        screenshots: List of screenshot paths
        visual_issues: Visual problems found
        functional_issues: Functional problems found
        requires_immediate_fix: Whether immediate action is needed

    Returns:
        Event with DebugReportCreatedPayload attached
    """
    from .event_payloads import DebugReportCreatedPayload

    payload = DebugReportCreatedPayload(
        doc_id=doc_id,
        issues_found=issues_found,
        screenshots=screenshots or [],
        visual_issues=visual_issues or [],
        functional_issues=functional_issues or [],
        requires_immediate_fix=requires_immediate_fix,
    )

    return Event.with_payload(
        type=EventType.DEBUG_REPORT_CREATED,
        source=source,
        payload=payload,
    )


def quality_report_event(
    source: str,
    doc_id: str,
    requires_action: bool = False,
    cleanup_tasks: int = 0,
    refactor_tasks: int = 0,
    cleanup_items: Optional[list[dict]] = None,
    refactor_items: Optional[list[dict]] = None,
) -> Event:
    """Create QUALITY_REPORT_CREATED event with typed payload.

    Args:
        source: Agent name (usually "CodeQualityAgent")
        doc_id: Document ID for the quality report
        requires_action: Whether code changes are needed
        cleanup_tasks: Number of cleanup tasks
        refactor_tasks: Number of refactor tasks
        cleanup_items: Detailed cleanup items
        refactor_items: Detailed refactor items

    Returns:
        Event with QualityReportCreatedPayload attached
    """
    from .event_payloads import QualityReportCreatedPayload

    payload = QualityReportCreatedPayload(
        doc_id=doc_id,
        requires_action=requires_action,
        cleanup_tasks=cleanup_tasks,
        refactor_tasks=refactor_tasks,
        cleanup_items=cleanup_items or [],
        refactor_items=refactor_items or [],
    )

    return Event.with_payload(
        type=EventType.QUALITY_REPORT_CREATED,
        source=source,
        payload=payload,
    )


def convergence_update_event(
    source: str,
    iteration: int,
    progress_percent: float,
    build_passing: bool = False,
    tests_passing: bool = False,
    type_errors: int = 0,
    mock_violations: int = 0,
    active_agents: Optional[list[str]] = None,
) -> Event:
    """Create CONVERGENCE_UPDATE event with typed payload.

    Args:
        source: Usually "Orchestrator"
        iteration: Current iteration number
        progress_percent: Progress towards convergence (0-100)
        build_passing: Whether build is currently passing
        tests_passing: Whether tests are currently passing
        type_errors: Current type error count
        mock_violations: Current mock violation count
        active_agents: List of currently active agent names

    Returns:
        Event with ConvergenceUpdatePayload attached
    """
    from .event_payloads import ConvergenceUpdatePayload

    payload = ConvergenceUpdatePayload(
        iteration=iteration,
        progress_percent=progress_percent,
        build_passing=build_passing,
        tests_passing=tests_passing,
        type_errors=type_errors,
        mock_violations=mock_violations,
        active_agents=active_agents or [],
    )

    return Event.with_payload(
        type=EventType.CONVERGENCE_UPDATE,
        source=source,
        payload=payload,
    )


def deploy_succeeded_event(
    source: str,
    deploy_url: Optional[str] = None,
    container_id: Optional[str] = None,
    vnc_url: Optional[str] = None,
    app_port: Optional[int] = None,
    health_check_passed: bool = False,
) -> Event:
    """Create DEPLOY_SUCCEEDED event with typed payload.

    Args:
        source: Agent name (usually "DeploymentTeamAgent")
        deploy_url: URL where the app is deployed
        container_id: Docker container ID
        vnc_url: VNC streaming URL
        app_port: Port the app is running on
        health_check_passed: Whether health check passed

    Returns:
        Event with DeploySucceededPayload attached
    """
    from .event_payloads import DeploySucceededPayload

    payload = DeploySucceededPayload(
        deploy_url=deploy_url,
        container_id=container_id,
        vnc_url=vnc_url,
        app_port=app_port,
        health_check_passed=health_check_passed,
    )

    return Event.with_payload(
        type=EventType.DEPLOY_SUCCEEDED,
        source=source,
        payload=payload,
        success=True,
    )


# Docker Build Factory Functions


def docker_build_requested_event(
    source: str,
    tag: str,
    context: str,
    dockerfile: Optional[str] = None,
) -> Event:
    """Create DOCKER_BUILD_REQUESTED event.

    Args:
        source: Agent requesting the build
        tag: Docker image tag to build
        context: Build context directory
        dockerfile: Path to Dockerfile (optional)

    Returns:
        Event requesting a Docker build
    """
    return Event(
        type=EventType.DOCKER_BUILD_REQUESTED,
        source=source,
        data={
            "tag": tag,
            "context": context,
            "dockerfile": dockerfile,
        },
    )


def docker_build_started_event(
    source: str,
    tag: str,
    context: str,
    dockerfile: Optional[str] = None,
) -> Event:
    """Create DOCKER_BUILD_STARTED event.

    Args:
        source: Agent name (usually "GordonBuildAgent")
        tag: Docker image tag being built
        context: Build context directory
        dockerfile: Path to Dockerfile (optional)

    Returns:
        Event with Docker build metadata
    """
    return Event(
        type=EventType.DOCKER_BUILD_STARTED,
        source=source,
        data={
            "tag": tag,
            "context": context,
            "dockerfile": dockerfile,
        },
    )


def docker_build_succeeded_event(
    source: str,
    tag: str,
    iterations: int = 1,
    history: Optional[list[dict]] = None,
) -> Event:
    """Create DOCKER_BUILD_SUCCEEDED event.

    Args:
        source: Agent name (usually "GordonBuildAgent")
        tag: Docker image tag that was built
        iterations: Number of build attempts
        history: Build attempt history

    Returns:
        Event with build success metadata
    """
    return Event(
        type=EventType.DOCKER_BUILD_SUCCEEDED,
        source=source,
        success=True,
        data={
            "tag": tag,
            "iterations": iterations,
            "history": history or [],
        },
    )


def docker_build_failed_event(
    source: str,
    tag: str,
    error: str,
    iterations: int = 1,
    history: Optional[list[dict]] = None,
) -> Event:
    """Create DOCKER_BUILD_FAILED event.

    Args:
        source: Agent name (usually "GordonBuildAgent")
        tag: Docker image tag that failed to build
        error: Error message from the build
        iterations: Number of build attempts
        history: Build attempt history

    Returns:
        Event with build failure metadata
    """
    return Event(
        type=EventType.DOCKER_BUILD_FAILED,
        source=source,
        success=False,
        error_message=error,
        data={
            "tag": tag,
            "error": error,
            "iterations": iterations,
            "history": history or [],
        },
    )


def docker_build_fix_applied_event(
    source: str,
    iteration: int,
    fix_summary: str,
) -> Event:
    """Create DOCKER_BUILD_FIX_APPLIED event.

    Args:
        source: Agent name (usually "GordonBuildAgent")
        iteration: Current build iteration
        fix_summary: Summary of the fix that was applied

    Returns:
        Event with fix metadata
    """
    return Event(
        type=EventType.DOCKER_BUILD_FIX_APPLIED,
        source=source,
        data={
            "iteration": iteration,
            "fix_summary": fix_summary,
        },
    )


# Playwright E2E Factory Functions

def playwright_e2e_started_event(
    source: str,
    url: str,
) -> Event:
    """Create PLAYWRIGHT_E2E_STARTED event.

    Args:
        source: Agent name (usually "PlaywrightE2EAgent")
        url: URL being tested

    Returns:
        Event with E2E test metadata
    """
    return Event(
        type=EventType.PLAYWRIGHT_E2E_STARTED,
        source=source,
        data={"url": url},
    )


def playwright_screenshot_analyzed_event(
    source: str,
    analysis_data: dict,
) -> Event:
    """Create PLAYWRIGHT_SCREENSHOT_ANALYZED event.

    Args:
        source: Agent name (usually "PlaywrightE2EAgent")
        analysis_data: Visual analysis results

    Returns:
        Event with analysis metadata
    """
    return Event(
        type=EventType.PLAYWRIGHT_SCREENSHOT_ANALYZED,
        source=source,
        data=analysis_data,
    )


def playwright_debug_plan_created_event(
    source: str,
    steps: list[dict],
) -> Event:
    """Create PLAYWRIGHT_DEBUG_PLAN_CREATED event.

    Args:
        source: Agent name (usually "PlaywrightE2EAgent")
        steps: List of interaction/debug steps

    Returns:
        Event with debug plan metadata
    """
    return Event(
        type=EventType.PLAYWRIGHT_DEBUG_PLAN_CREATED,
        source=source,
        data={"steps": steps},
    )


def playwright_e2e_result_event(
    source: str,
    success: bool,
    url: Optional[str] = None,
    tests_run: int = 0,
    tests_passed: int = 0,
    tests_failed: int = 0,
    screenshots: Optional[list[str]] = None,
    visual_issues: Optional[list[dict]] = None,
    error: Optional[str] = None,
    data: Optional[dict] = None,
) -> Event:
    """Create PLAYWRIGHT_E2E_PASSED or PLAYWRIGHT_E2E_FAILED event.

    Args:
        source: Agent name (usually "PlaywrightE2EAgent")
        success: Whether the E2E test passed
        url: URL that was tested
        tests_run: Number of tests executed
        tests_passed: Number of tests that passed
        tests_failed: Number of tests that failed
        screenshots: List of screenshot paths
        visual_issues: List of visual issues found
        error: Error message if failed
        data: Optional full data dict (overrides individual params if provided)

    Returns:
        Event with E2E test results
    """
    event_type = EventType.PLAYWRIGHT_E2E_PASSED if success else EventType.PLAYWRIGHT_E2E_FAILED
    event_data = data if data is not None else {
        "url": url,
        "tests_run": tests_run,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "screenshots": screenshots or [],
        "visual_issues": visual_issues or [],
    }
    return Event(
        type=event_type,
        source=source,
        success=success,
        error_message=error,
        data=event_data,
    )


# Test Factory Functions

def app_launched_event(
    source: str,
    command: str,
    pid: Optional[int] = None,
) -> Event:
    """Create APP_LAUNCHED event.

    Args:
        source: Agent name (usually "TesterTeamAgent")
        command: Command used to launch the app
        pid: Process ID of the launched app

    Returns:
        Event with app launch metadata
    """
    return Event(
        type=EventType.APP_LAUNCHED,
        source=source,
        success=True,
        data={
            "command": command,
            "pid": pid,
        },
    )


def test_spec_created_event(
    source: str,
    doc_id: str,
    tests_run: int = 0,
    tests_passed: int = 0,
    tests_failed: int = 0,
    responding_to: Optional[list[str]] = None,
) -> Event:
    """Create TEST_SPEC_CREATED event.

    Args:
        source: Agent name (usually "TesterTeamAgent")
        doc_id: Document ID for the test spec
        tests_run: Number of tests executed
        tests_passed: Number of tests that passed
        tests_failed: Number of tests that failed
        responding_to: List of events this test spec responds to

    Returns:
        Event with test spec metadata
    """
    return Event(
        type=EventType.TEST_SPEC_CREATED,
        source=source,
        data={
            "doc_id": doc_id,
            "tests_run": tests_run,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "responding_to": responding_to or [],
        },
    )


# UX Factory Functions

def ux_issue_found_event(
    source: str,
    issues: list[dict],
    screenshot_path: Optional[str] = None,
    page_url: Optional[str] = None,
    severity: str = "medium",
) -> Event:
    """Create UX_ISSUE_FOUND event.

    Args:
        source: Agent name (usually "UXDesignAgent")
        issues: List of UX issues found
        screenshot_path: Path to the analyzed screenshot
        page_url: URL of the page with issues
        severity: Overall severity level

    Returns:
        Event with UX issue metadata
    """
    return Event(
        type=EventType.UX_ISSUE_FOUND,
        source=source,
        data={
            "issues": issues,
            "issue_count": len(issues),
            "screenshot_path": screenshot_path,
            "page_url": page_url,
            "severity": severity,
        },
    )


def ux_review_passed_event(
    source: str,
    page_url: Optional[str] = None,
    score: Optional[float] = None,
) -> Event:
    """Create UX_REVIEW_PASSED event.

    Args:
        source: Agent name (usually "UXDesignAgent")
        page_url: URL of the reviewed page
        score: UX quality score (0-100)

    Returns:
        Event indicating UX review passed
    """
    return Event(
        type=EventType.UX_REVIEW_PASSED,
        source=source,
        success=True,
        data={
            "page_url": page_url,
            "score": score,
        },
    )


def ux_review_started_event(source: str) -> Event:
    """Create UX_REVIEW_STARTED event.

    Args:
        source: Agent name (usually "UXDesignAgent")

    Returns:
        Event indicating UX review has started
    """
    return Event(
        type=EventType.UX_REVIEW_STARTED,
        source=source,
        success=True,
    )


def ux_recommendation_event(
    source: str,
    recommendation: str,
    category: Optional[str] = None,
    priority: Optional[str] = None,
) -> Event:
    """Create UX_RECOMMENDATION event.

    Args:
        source: Agent name (usually "UXDesignAgent")
        recommendation: The UX recommendation text
        category: Category of recommendation
        priority: Priority level

    Returns:
        Event with UX recommendation
    """
    return Event(
        type=EventType.UX_RECOMMENDATION,
        source=source,
        success=True,
        data={
            "recommendation": recommendation,
            "category": category,
            "priority": priority,
        },
    )


def ux_review_complete_event(
    source: str,
    success: bool,
    overall_score: Optional[float] = None,
    issues_count: int = 0,
    recommendations_count: int = 0,
    review_data: Optional[dict] = None,
) -> Event:
    """Create UX_REVIEW_COMPLETE event.

    Args:
        source: Agent name (usually "UXDesignAgent")
        success: Whether the review completed successfully
        overall_score: Overall UX score
        issues_count: Number of issues found
        recommendations_count: Number of recommendations made
        review_data: Full review data dict

    Returns:
        Event indicating UX review is complete
    """
    data = review_data or {}
    data.update({
        "overall_score": overall_score,
        "issues_count": issues_count,
        "recommendations_count": recommendations_count,
    })
    return Event(
        type=EventType.UX_REVIEW_COMPLETE,
        source=source,
        success=success,
        data=data,
    )


# Deploy Factory Functions

def deploy_started_event(
    source: str,
    attempt: int = 1,
    working_dir: Optional[str] = None,
) -> Event:
    """Create DEPLOY_STARTED event.

    Args:
        source: Agent name (usually "DeployAgent")
        attempt: Deployment attempt number
        working_dir: Working directory being deployed

    Returns:
        Event indicating deployment has started
    """
    return Event(
        type=EventType.DEPLOY_STARTED,
        source=source,
        data={
            "attempt": attempt,
            "working_dir": working_dir,
        },
    )


def deploy_failed_event(
    source: str,
    error: str,
    attempt: int = 1,
    duration_ms: Optional[int] = None,
    steps: Optional[list[dict]] = None,
) -> Event:
    """Create DEPLOY_FAILED event.

    Args:
        source: Agent name (usually "DeployAgent")
        error: Error message describing the failure
        attempt: Deployment attempt number
        duration_ms: Total deployment duration
        steps: List of deployment steps with status

    Returns:
        Event indicating deployment failed
    """
    return Event(
        type=EventType.DEPLOY_FAILED,
        source=source,
        success=False,
        error_message=error,
        data={
            "attempt": attempt,
            "duration_ms": duration_ms,
            "steps": steps or [],
        },
    )


def deploy_logs_collected_event(
    source: str,
    logs: str,
    steps: Optional[list[dict]] = None,
) -> Event:
    """Create DEPLOY_LOGS_COLLECTED event.

    Args:
        source: Agent name (usually "DeployAgent")
        logs: Deployment log output
        steps: List of deployment steps with details

    Returns:
        Event with deployment logs
    """
    return Event(
        type=EventType.DEPLOY_LOGS_COLLECTED,
        source=source,
        data={
            "logs": logs,
            "steps": steps or [],
        },
    )


# Database Migration Factory Functions

def database_migration_event(
    source: str,
    success: bool,
    migration_name: Optional[str] = None,
    tool: str = "prisma",
    error: Optional[str] = None,
) -> Event:
    """Create DATABASE_MIGRATION_COMPLETE or DATABASE_MIGRATION_FAILED event.

    Args:
        source: Agent name (usually "MigrationAgent")
        success: Whether migration succeeded
        migration_name: Name of the migration
        tool: Migration tool used (prisma, drizzle, alembic)
        error: Error message if failed

    Returns:
        Event indicating migration result
    """
    event_type = EventType.DATABASE_MIGRATION_COMPLETE if success else EventType.DATABASE_MIGRATION_FAILED
    return Event(
        type=event_type,
        source=source,
        success=success,
        error_message=error,
        data={
            "migration_name": migration_name,
            "tool": tool,
        },
    )


def database_seed_complete_event(
    source: str,
    tool: str = "prisma",
) -> Event:
    """Create DATABASE_SEED_COMPLETE event.

    Args:
        source: Agent name (usually "MigrationAgent")
        tool: Seeding tool used

    Returns:
        Event indicating seed data was applied
    """
    return Event(
        type=EventType.DATABASE_SEED_COMPLETE,
        source=source,
        data={"tool": tool},
    )


# Sandbox/Continuous Testing Factory Functions

def sandbox_test_started_event(
    source: str,
    working_dir: Optional[str] = None,
    mode: str = "single",
    cycle_interval: Optional[int] = None,
    vnc_enabled: bool = False,
    vnc_port: Optional[int] = None,
    deploy_number: Optional[int] = None,
) -> Event:
    """Create SANDBOX_TEST_STARTED event.

    Args:
        source: Agent name (usually "DeploymentTeamAgent")
        working_dir: Working directory being tested
        mode: Test mode ("single", "continuous")
        cycle_interval: Interval between cycles for continuous mode
        vnc_enabled: Whether VNC is enabled
        vnc_port: VNC port if enabled
        deploy_number: Deployment attempt number

    Returns:
        Event indicating sandbox test started
    """
    data = {
        "working_dir": working_dir,
        "mode": mode,
    }
    if cycle_interval is not None:
        data["cycle_interval"] = cycle_interval
    if vnc_enabled:
        data["vnc_enabled"] = vnc_enabled
        data["vnc_port"] = vnc_port
    if deploy_number is not None:
        data["deploy_number"] = deploy_number

    return Event(
        type=EventType.SANDBOX_TEST_STARTED,
        source=source,
        data=data,
    )


def screen_stream_ready_event(
    source: str,
    vnc_url: str,
    vnc_port: Optional[int] = None,
    container_id: Optional[str] = None,
    project_type: Optional[str] = None,
    mode: str = "single",
) -> Event:
    """Create SCREEN_STREAM_READY event for VNC streaming.

    Args:
        source: Agent name (usually "DeploymentTeamAgent")
        vnc_url: Full URL to access VNC stream
        vnc_port: VNC port number
        container_id: Docker container ID
        project_type: Type of project (electron, react, etc.)
        mode: Test mode ("single", "continuous")

    Returns:
        Event indicating VNC stream is ready
    """
    data = {
        "vnc_url": vnc_url,
    }
    if vnc_port is not None:
        data["vnc_port"] = vnc_port
    if container_id:
        data["container_id"] = container_id
    if project_type:
        data["project_type"] = project_type
    if mode:
        data["mode"] = mode

    return Event(
        type=EventType.SCREEN_STREAM_READY,
        source=source,
        data=data,
    )


def persistent_deploy_started_event(
    source: str,
    vnc_port: int,
    working_dir: Optional[str] = None,
) -> Event:
    """Create PERSISTENT_DEPLOY_STARTED event.

    Args:
        source: Agent name (usually "DeploymentTeamAgent")
        vnc_port: VNC port for the persistent deployment
        working_dir: Working directory being deployed

    Returns:
        Event indicating persistent deployment started
    """
    return Event(
        type=EventType.PERSISTENT_DEPLOY_STARTED,
        source=source,
        data={
            "vnc_port": vnc_port,
            "working_dir": working_dir,
        },
    )


def persistent_deploy_ready_event(
    source: str,
    vnc_url: Optional[str] = None,
    vnc_port: Optional[int] = None,
    container_id: Optional[str] = None,
    secrets_injected: Optional[list[str]] = None,
) -> Event:
    """Create PERSISTENT_DEPLOY_READY event."""
    data = {"mode": "persistent"}
    if vnc_url:
        data["vnc_url"] = vnc_url
    if vnc_port:
        data["vnc_port"] = vnc_port
    if container_id:
        data["container_id"] = container_id
    if secrets_injected:
        data["secrets_injected"] = secrets_injected
    return Event(
        type=EventType.PERSISTENT_DEPLOY_READY,
        source=source,
        success=True,
        data=data,
    )


def persistent_deploy_failed_event(
    source: str,
    error_message: str,
    vnc_port: Optional[int] = None,
) -> Event:
    """Create PERSISTENT_DEPLOY_FAILED event."""
    data = {}
    if vnc_port:
        data["vnc_port"] = vnc_port
    return Event(
        type=EventType.PERSISTENT_DEPLOY_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data=data if data else None,
    )


def sandbox_test_passed_event(
    source: str,
    message: Optional[str] = None,
    data: Optional[dict] = None,
) -> Event:
    """Create SANDBOX_TEST_PASSED event."""
    event_data = data or {}
    if message:
        event_data["message"] = message
    return Event(
        type=EventType.SANDBOX_TEST_PASSED,
        source=source,
        success=True,
        data=event_data if event_data else None,
    )


def sandbox_test_failed_event(
    source: str,
    error_message: Optional[str] = None,
    deploy_number: Optional[int] = None,
    data: Optional[dict] = None,
) -> Event:
    """Create SANDBOX_TEST_FAILED event."""
    event_data = data or {}
    if deploy_number is not None:
        event_data["deploy_number"] = deploy_number
    return Event(
        type=EventType.SANDBOX_TEST_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data=event_data if event_data else None,
    )


# Validation/Testing Factory Functions

def mock_validation_passed_event(
    source: str,
    checks_run: int = 0,
) -> Event:
    """Create MOCK_VALIDATION_PASSED event.

    Args:
        source: Agent name (usually "ValidationTeamAgent")
        checks_run: Number of validation checks run

    Returns:
        Event indicating mock validation passed
    """
    return Event(
        type=EventType.MOCK_VALIDATION_PASSED,
        source=source,
        success=True,
        data={"checks_run": checks_run},
    )


def tests_running_event(
    source: str,
    phase: Optional[str] = None,
    validation_number: Optional[int] = None,
    working_dir: Optional[str] = None,
    test_framework: Optional[str] = None,
    **kwargs,
) -> Event:
    """Create TESTS_RUNNING event.

    Args:
        source: Agent name (usually "ValidationTeamAgent")
        phase: Current testing phase (test_generation, testing, etc.)
        validation_number: Validation attempt number
        working_dir: Working directory being tested
        test_framework: Test framework in use
        **kwargs: Additional data to include

    Returns:
        Event indicating tests are running
    """
    data = {}
    if phase:
        data["phase"] = phase
    if validation_number is not None:
        data["validation_number"] = validation_number
    if working_dir:
        data["working_dir"] = working_dir
    if test_framework:
        data["test_framework"] = test_framework
    data.update(kwargs)

    return Event(
        type=EventType.TESTS_RUNNING,
        source=source,
        data=data,
    )


# Generator Agent Factory Functions

def mock_replaced_event(
    source: str,
    violations_fixed: int = 0,
    files_modified: Optional[list[str]] = None,
) -> Event:
    """Create MOCK_REPLACED event.

    Args:
        source: Agent name (usually "GeneratorAgent")
        violations_fixed: Number of mock violations fixed
        files_modified: List of files that were modified

    Returns:
        Event indicating mocks were replaced
    """
    return Event(
        type=EventType.MOCK_REPLACED,
        source=source,
        success=True,
        data={
            "violations_fixed": violations_fixed,
            "files_modified": files_modified or [],
        },
    )


def file_modified_event(
    source: str,
    file_path: str,
    language: Optional[str] = None,
    quality_task: bool = False,
) -> Event:
    """Create FILE_MODIFIED event.

    Args:
        source: Agent name (usually "GeneratorAgent")
        file_path: Path to the modified file
        language: Programming language of the file
        quality_task: Whether this was a quality improvement task

    Returns:
        Event indicating a file was modified
    """
    data = {}
    if language:
        data["language"] = language
    if quality_task:
        data["quality_task"] = quality_task

    return Event(
        type=EventType.FILE_MODIFIED,
        source=source,
        file_path=file_path,
        data=data,
    )


def implementation_plan_created_event(
    source: str,
    doc_id: str,
    files_changed: int = 0,
    fixes_planned: int = 0,
    responding_to: Optional[list[str]] = None,
) -> Event:
    """Create IMPLEMENTATION_PLAN_CREATED event.

    Args:
        source: Agent name (usually "GeneratorAgent")
        doc_id: Document ID for the implementation plan
        files_changed: Number of files changed
        fixes_planned: Number of fixes planned
        responding_to: List of debug report IDs being addressed

    Returns:
        Event indicating implementation plan was created
    """
    return Event(
        type=EventType.IMPLEMENTATION_PLAN_CREATED,
        source=source,
        data={
            "doc_id": doc_id,
            "files_changed": files_changed,
            "fixes_planned": fixes_planned,
            "responding_to": responding_to or [],
        },
    )


# Debug Agent Factory Functions

def debug_started_event(
    source: str,
    cycle: int = 0,
    working_dir: Optional[str] = None,
) -> Event:
    """Create DEBUG_STARTED event.

    Args:
        source: Agent name (usually "ContinuousDebugAgent")
        cycle: Debug cycle number
        working_dir: Working directory being debugged

    Returns:
        Event indicating debug cycle started
    """
    return Event(
        type=EventType.DEBUG_STARTED,
        source=source,
        data={
            "cycle": cycle,
            "working_dir": working_dir,
        },
    )


def file_created_event(
    source: str,
    file_path: str,
) -> Event:
    """Create FILE_CREATED event.

    Args:
        source: Agent name
        file_path: Path to the created file

    Returns:
        Event indicating a file was created
    """
    return Event(
        type=EventType.FILE_CREATED,
        source=source,
        file_path=file_path,
        success=True,
    )


# Localization Agent Factory Functions

def i18n_setup_started_event(
    source: str,
    working_dir: str,
    default_locale: str = "en",
    target_locales: Optional[list[str]] = None,
) -> Event:
    """Create I18N_SETUP_STARTED event."""
    return Event(
        type=EventType.I18N_SETUP_STARTED,
        source=source,
        data={
            "working_dir": working_dir,
            "default_locale": default_locale,
            "target_locales": target_locales or [],
        },
    )


def localization_complete_event(
    source: str,
    library: str,
    locales: list[str],
    keys_extracted: int = 0,
    namespaces: Optional[list[str]] = None,
) -> Event:
    """Create LOCALIZATION_COMPLETE event."""
    return Event(
        type=EventType.LOCALIZATION_COMPLETE,
        source=source,
        data={
            "library": library,
            "locales": locales,
            "keys_extracted": keys_extracted,
            "namespaces": namespaces or [],
        },
    )


def i18n_configured_event(
    source: str,
    library: str,
    messages_dir: str,
) -> Event:
    """Create I18N_CONFIGURED event."""
    return Event(
        type=EventType.I18N_CONFIGURED,
        source=source,
        data={
            "library": library,
            "messages_dir": messages_dir,
        },
    )


def translation_needed_event(
    source: str,
    hardcoded_strings: list[dict],
    count: int = 0,
) -> Event:
    """Create TRANSLATION_NEEDED event."""
    return Event(
        type=EventType.TRANSLATION_NEEDED,
        source=source,
        data={
            "hardcoded_strings": hardcoded_strings,
            "count": count,
        },
    )


def translation_keys_extracted_event(
    source: str,
    keys: int = 0,
    namespaces: Optional[list[str]] = None,
    hardcoded_count: int = 0,
) -> Event:
    """Create TRANSLATION_KEYS_EXTRACTED event."""
    return Event(
        type=EventType.TRANSLATION_KEYS_EXTRACTED,
        source=source,
        data={
            "keys": keys,
            "namespaces": namespaces or [],
            "hardcoded_count": hardcoded_count,
        },
    )


# ============================================================================
# Performance Events
# ============================================================================


def performance_analysis_started_event(
    source: str,
    working_dir: str,
    trigger: Optional[str] = None,
) -> Event:
    """Create PERFORMANCE_ANALYSIS_STARTED event."""
    return Event(
        type=EventType.PERFORMANCE_ANALYSIS_STARTED,
        source=source,
        data={
            "working_dir": working_dir,
            "trigger": trigger,
        },
    )


def bundle_size_warning_event(
    source: str,
    total_size_kb: float,
    js_size_kb: float = 0.0,
    css_size_kb: float = 0.0,
    threshold_kb: float = 500.0,
) -> Event:
    """Create BUNDLE_SIZE_WARNING event."""
    return Event(
        type=EventType.BUNDLE_SIZE_WARNING,
        source=source,
        data={
            "total_size_kb": total_size_kb,
            "js_size_kb": js_size_kb,
            "css_size_kb": css_size_kb,
            "threshold_kb": threshold_kb,
        },
    )


def lighthouse_score_low_event(
    source: str,
    score: int,
    threshold: int,
    categories: Optional[dict] = None,
) -> Event:
    """Create LIGHTHOUSE_SCORE_LOW event."""
    return Event(
        type=EventType.LIGHTHOUSE_SCORE_LOW,
        source=source,
        data={
            "score": score,
            "threshold": threshold,
            "categories": categories or {},
        },
    )


def performance_issue_detected_event(
    source: str,
    total_issues: int,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    issues: Optional[list] = None,
) -> Event:
    """Create PERFORMANCE_ISSUE_DETECTED event."""
    return Event(
        type=EventType.PERFORMANCE_ISSUE_DETECTED,
        source=source,
        data={
            "total_issues": total_issues,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "issues": issues or [],
        },
    )


def performance_benchmark_passed_event(
    source: str,
    total_issues: int = 0,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    issues: Optional[list] = None,
) -> Event:
    """Create PERFORMANCE_BENCHMARK_PASSED event."""
    return Event(
        type=EventType.PERFORMANCE_BENCHMARK_PASSED,
        source=source,
        data={
            "total_issues": total_issues,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "issues": issues or [],
        },
    )


# ============================================================================
# Accessibility Events
# ============================================================================


def a11y_scan_started_event(
    source: str,
    working_dir: str,
    wcag_level: str = "AA",
    trigger: Optional[str] = None,
) -> Event:
    """Create A11Y_SCAN_STARTED event."""
    return Event(
        type=EventType.A11Y_SCAN_STARTED,
        source=source,
        data={
            "working_dir": working_dir,
            "wcag_level": wcag_level,
            "trigger": trigger,
        },
    )


def a11y_issue_found_event(
    source: str,
    wcag: Optional[str] = None,
    guideline: Optional[str] = None,
    level: Optional[str] = None,
    violations: Optional[list] = None,
    total_issues: int = 0,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    wcag_level: Optional[str] = None,
    wcag_violations: Optional[dict] = None,
    issues: Optional[list] = None,
) -> Event:
    """Create A11Y_ISSUE_FOUND event."""
    data = {}
    if wcag is not None:
        data["wcag"] = wcag
    if guideline is not None:
        data["guideline"] = guideline
    if level is not None:
        data["level"] = level
    if violations is not None:
        data["violations"] = violations
    if total_issues:
        data["total_issues"] = total_issues
    if critical:
        data["critical"] = critical
    if high:
        data["high"] = high
    if medium:
        data["medium"] = medium
    if low:
        data["low"] = low
    if wcag_level:
        data["wcag_level"] = wcag_level
    if wcag_violations:
        data["wcag_violations"] = wcag_violations
    if issues:
        data["issues"] = issues
    return Event(
        type=EventType.A11Y_ISSUE_FOUND,
        source=source,
        data=data,
    )


def a11y_test_passed_event(
    source: str,
    total_issues: int = 0,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    wcag_level: str = "AA",
    wcag_violations: Optional[dict] = None,
    issues: Optional[list] = None,
) -> Event:
    """Create A11Y_TEST_PASSED event."""
    return Event(
        type=EventType.A11Y_TEST_PASSED,
        source=source,
        data={
            "total_issues": total_issues,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "wcag_level": wcag_level,
            "wcag_violations": wcag_violations or {},
            "issues": issues or [],
        },
    )


# ============================================================================
# Docker Swarm/Secrets Events
# ============================================================================


def swarm_initialized_event(source: str) -> Event:
    """Create SWARM_INITIALIZED event."""
    return Event(
        type=EventType.SWARM_INITIALIZED,
        source=source,
        success=True,
    )


def swarm_init_failed_event(source: str, error_message: Optional[str] = None) -> Event:
    """Create SWARM_INIT_FAILED event."""
    return Event(
        type=EventType.SWARM_INIT_FAILED,
        source=source,
        success=False,
        error_message=error_message,
    )


def secret_created_event(
    source: str,
    name: str,
    secret_id: Optional[str] = None,
    already_existed: bool = False,
) -> Event:
    """Create SECRET_CREATED event."""
    data = {"name": name}
    if secret_id:
        data["secret_id"] = secret_id
    if already_existed:
        data["already_existed"] = True
    return Event(
        type=EventType.SECRET_CREATED,
        source=source,
        success=True,
        data=data,
    )


def secret_create_failed_event(
    source: str,
    error_message: str,
    name: Optional[str] = None,
) -> Event:
    """Create SECRET_CREATE_FAILED event."""
    data = {}
    if name:
        data["name"] = name
    return Event(
        type=EventType.SECRET_CREATE_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data=data if data else None,
    )


def service_deployed_event(
    source: str,
    name: str,
    secrets: Optional[list[str]] = None,
    service_id: Optional[str] = None,
) -> Event:
    """Create SERVICE_DEPLOYED event."""
    data = {"name": name}
    if secrets:
        data["secrets"] = secrets
    if service_id:
        data["service_id"] = service_id
    return Event(
        type=EventType.SERVICE_DEPLOYED,
        source=source,
        success=True,
        data=data,
    )


def service_deploy_failed_event(
    source: str,
    error_message: str,
    name: Optional[str] = None,
    missing_secret: Optional[str] = None,
) -> Event:
    """Create SERVICE_DEPLOY_FAILED event."""
    data = {}
    if name:
        data["name"] = name
    if missing_secret:
        data["missing_secret"] = missing_secret
    return Event(
        type=EventType.SERVICE_DEPLOY_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data=data if data else None,
    )


# ============================================================================
# API Documentation Events
# ============================================================================


def api_docs_generation_started_event(
    source: str,
    working_dir: str,
    trigger: Optional[str] = None,
) -> Event:
    """Create API_DOCS_GENERATION_STARTED event."""
    return Event(
        type=EventType.API_DOCS_GENERATION_STARTED,
        source=source,
        data={
            "working_dir": working_dir,
            "trigger": trigger,
        },
    )


def api_docs_generated_event(
    source: str,
    routes_documented: int = 0,
    openapi_generated: bool = False,
    swagger_ui_generated: bool = False,
    postman_generated: bool = False,
) -> Event:
    """Create API_DOCS_GENERATED event."""
    return Event(
        type=EventType.API_DOCS_GENERATED,
        source=source,
        data={
            "routes_documented": routes_documented,
            "openapi_generated": openapi_generated,
            "swagger_ui_generated": swagger_ui_generated,
            "postman_generated": postman_generated,
        },
    )


def openapi_spec_created_event(
    source: str,
    spec_path: str,
    routes_count: int = 0,
) -> Event:
    """Create OPENAPI_SPEC_CREATED event."""
    return Event(
        type=EventType.OPENAPI_SPEC_CREATED,
        source=source,
        data={
            "spec_path": spec_path,
            "routes_count": routes_count,
        },
    )


# ============================================================================
# Environment/Documentation Events
# ============================================================================


def env_report_created_event(
    source: str,
    project_name: Optional[str] = None,
    tech_stack: Optional[dict] = None,
    environment_vars: Optional[list] = None,
    docker_services: Optional[list] = None,
) -> Event:
    """Create ENV_REPORT_CREATED event."""
    return Event(
        type=EventType.ENV_REPORT_CREATED,
        source=source,
        data={
            "project_name": project_name,
            "tech_stack": tech_stack or {},
            "environment_vars": environment_vars or [],
            "docker_services": docker_services or [],
        },
    )


def documentation_generated_event(
    source: str,
    files_created: Optional[list[str]] = None,
    total_docs: int = 0,
) -> Event:
    """Create DOCUMENTATION_GENERATED event."""
    return Event(
        type=EventType.DOCUMENTATION_GENERATED,
        source=source,
        data={
            "files_created": files_created or [],
            "total_docs": total_docs,
        },
    )


# ============================================================================
# Debug/Verification Events
# ============================================================================


def debug_fix_applied_event(
    source: str,
    file_path: str,
    fix_type: Optional[str] = None,
    success: bool = True,
) -> Event:
    """Create DEBUG_FIX_APPLIED event."""
    return Event(
        type=EventType.DEBUG_FIX_APPLIED,
        source=source,
        success=success,
        data={
            "file_path": file_path,
            "fix_type": fix_type,
        },
    )


def verification_complete_event(
    source: str,
    result: str,
    confidence: float = 0.0,
    details: Optional[dict] = None,
) -> Event:
    """Create VERIFICATION_COMPLETE event."""
    return Event(
        type=EventType.VERIFICATION_COMPLETE,
        source=source,
        data={
            "result": result,
            "confidence": confidence,
            "details": details or {},
        },
    )


# ============================================================================
# Agent Lifecycle Events
# ============================================================================


def agent_started_event(
    source: str,
    agent_name: str,
) -> Event:
    """Create AGENT_STARTED event."""
    return Event(
        type=EventType.AGENT_STARTED,
        source=source,
        data={
            "agent_name": agent_name,
        },
    )


def agent_action_event(
    source: str,
    action: str,
    details: Optional[dict] = None,
) -> Event:
    """Create AGENT_ACTION event."""
    return Event(
        type=EventType.AGENT_ACTION,
        source=source,
        data={
            "action": action,
            "details": details or {},
        },
    )


def code_fix_needed_event(
    source: str,
    file_path: Optional[str] = None,
    error_message: Optional[str] = None,
    fix_type: str = "refactor",
    task_id: Optional[str] = None,
    priority: str = "medium",
    data: Optional[dict] = None,
) -> Event:
    """Create CODE_FIX_NEEDED event."""
    event_data = data or {}
    if fix_type:
        event_data["type"] = fix_type
    if task_id:
        event_data["task_id"] = task_id
    if priority:
        event_data["priority"] = priority
    return Event(
        type=EventType.CODE_FIX_NEEDED,
        source=source,
        file_path=file_path,
        error_message=error_message,
        data=event_data if event_data else None,
    )


def verification_started_event(
    source: str,
    requirement_count: int = 0,
) -> Event:
    """Create VERIFICATION_STARTED event."""
    return Event(
        type=EventType.VERIFICATION_STARTED,
        source=source,
        data={"requirement_count": requirement_count},
    )


def verification_failed_event(
    source: str,
    requirement_id: Optional[str] = None,
    actions_needed: Optional[list] = None,
    result: Optional[dict] = None,
) -> Event:
    """Create VERIFICATION_FAILED event."""
    return Event(
        type=EventType.VERIFICATION_FAILED,
        source=source,
        success=False,
        data={
            "requirement_id": requirement_id,
            "actions_needed": actions_needed or [],
            "result": result or {},
        },
    )


def env_missing_required_event(
    source: str,
    missing_vars: list[str],
    report: Optional[dict] = None,
) -> Event:
    """Create ENV_MISSING_REQUIRED event."""
    return Event(
        type=EventType.ENV_MISSING_REQUIRED,
        source=source,
        success=False,
        error_message=f"Missing required env vars: {', '.join(missing_vars)}",
        data=report or {"missing_required": missing_vars},
    )


def secret_create_requested_event(
    source: str,
    name: str,
    env_var: Optional[str] = None,
    description: Optional[str] = None,
) -> Event:
    """Create SECRET_CREATE_REQUESTED event."""
    data = {"name": name}
    if env_var:
        data["env_var"] = env_var
    if description:
        data["description"] = description
    return Event(
        type=EventType.SECRET_CREATE_REQUESTED,
        source=source,
        data=data,
    )


# =========================================================================
# Base Agent Events (autonomous_base.py agents)
# =========================================================================


def test_suite_complete_event(
    source: str,
    success: bool,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    failures: Optional[list[dict]] = None,
) -> Event:
    """Create TEST_SUITE_COMPLETE event for TesterAgent."""
    data = {
        "total": total,
        "passed": passed,
        "failed": failed,
    }
    if failures:
        data["failures"] = failures
    return Event(
        type=EventType.TEST_SUITE_COMPLETE,
        source=source,
        success=success,
        data=data,
    )


def build_succeeded_event(source: str) -> Event:
    """Create BUILD_SUCCEEDED event for BuilderAgent."""
    return Event(
        type=EventType.BUILD_SUCCEEDED,
        source=source,
        success=True,
    )


def type_check_passed_event(source: str) -> Event:
    """Create TYPE_CHECK_PASSED event for ValidatorAgent."""
    return Event(
        type=EventType.TYPE_CHECK_PASSED,
        source=source,
        success=True,
    )


def code_fixed_event(
    source: str,
    success: bool,
    attempted: int = 0,
    files_modified: Optional[Union[int, list]] = None,
    error: Optional[str] = None,
    fix_type: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> Event:
    """Create CODE_FIXED event for FixerAgent and DockerOrchestratorAgent."""
    data = {"attempted": attempted}
    if success:
        if files_modified is not None:
            data["files_modified"] = files_modified
    else:
        data["error"] = error
    if fix_type:
        data["fix_type"] = fix_type
    if extra_data:
        data.update(extra_data)
    return Event(
        type=EventType.CODE_FIXED,
        source=source,
        success=success,
        data=data,
    )


def system_error_event(
    source: str,
    error_message: str,
    error_type: Optional[str] = None,
    recoverable: bool = True,
    hint: Optional[str] = None,
) -> Event:
    """Create SYSTEM_ERROR event for exception handling."""
    data = {}
    if error_type:
        data["error_type"] = error_type
    data["recoverable"] = recoverable
    if hint:
        data["hint"] = hint
    return Event(
        type=EventType.SYSTEM_ERROR,
        source=source,
        success=False,
        error_message=error_message,
        data=data if data else None,
    )


def env_report_complete_event(
    source: str,
    success: bool,
    report: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> Event:
    """Create ENV_REPORT_COMPLETE event for EnvironmentReportAgent."""
    return Event(
        type=EventType.ENV_REPORT_COMPLETE,
        source=source,
        success=success,
        error_message=error_message,
        data=report,
    )


def verification_passed_event(
    source: str,
    verified_count: int = 0,
    failed_count: int = 0,
    total_count: int = 0,
    results: Optional[list[dict]] = None,
) -> Event:
    """Create VERIFICATION_PASSED event for VerificationDebateAgent."""
    return Event(
        type=EventType.VERIFICATION_PASSED,
        source=source,
        success=True,
        data={
            "verified_count": verified_count,
            "failed_count": failed_count,
            "total_count": total_count,
            "results": results or [],
        },
    )


def recovery_failed_event(
    source: str,
    error: Optional[str] = None,
    attempted: int = 0,
) -> Event:
    """Create RECOVERY_FAILED event for GeneratorAgent."""
    data = {"attempted": attempted}
    if error:
        data["error"] = error
    return Event(
        type=EventType.RECOVERY_FAILED,
        source=source,
        success=False,
        data=data,
    )


# =========================================================================
# Backend Agent Events (database, api, auth, infrastructure)
# =========================================================================


def database_schema_generated_event(
    source: str,
    db_type: str = "prisma",
    schema_path: Optional[str] = None,
    tables_created: int = 0,
    schema_valid: bool = True,  # Phase 5A: Schema validation status
) -> Event:
    """Create DATABASE_SCHEMA_GENERATED event.

    Args:
        source: Agent that generated the schema
        db_type: Database ORM type (prisma, sqlalchemy, etc.)
        schema_path: Path to the schema file
        tables_created: Number of tables/models created
        schema_valid: Whether the schema passed validation (e.g., prisma generate)
    """
    return Event(
        type=EventType.DATABASE_SCHEMA_GENERATED,
        source=source,
        success=schema_valid,  # Phase 5A: Success depends on validation
        data={
            "db_type": db_type,
            "schema_path": schema_path,
            "tables_created": tables_created,
            "schema_valid": schema_valid,
        },
    )


def database_schema_failed_event(
    source: str,
    error_message: str,
    db_type: str = "prisma",
) -> Event:
    """Create DATABASE_SCHEMA_FAILED event."""
    return Event(
        type=EventType.DATABASE_SCHEMA_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data={"db_type": db_type},
    )


def api_routes_generated_event(
    source: str,
    framework: str = "nextjs",
    routes_count: int = 0,
    endpoints: Optional[list[str]] = None,
) -> Event:
    """Create API_ROUTES_GENERATED event."""
    return Event(
        type=EventType.API_ROUTES_GENERATED,
        source=source,
        success=True,
        data={
            "framework": framework,
            "routes_count": routes_count,
            "endpoints": endpoints or [],
        },
    )


def api_generation_failed_event(
    source: str,
    error_message: str,
    framework: str = "nextjs",
) -> Event:
    """Create API_GENERATION_FAILED event."""
    return Event(
        type=EventType.API_GENERATION_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data={"framework": framework},
    )


def auth_setup_complete_event(
    source: str,
    auth_type: str = "jwt",
    features: Optional[list[str]] = None,
) -> Event:
    """Create AUTH_SETUP_COMPLETE event."""
    return Event(
        type=EventType.AUTH_SETUP_COMPLETE,
        source=source,
        success=True,
        data={
            "auth_type": auth_type,
            "features": features or [],
        },
    )


def auth_setup_failed_event(
    source: str,
    error_message: str,
    auth_type: str = "jwt",
) -> Event:
    """Create AUTH_SETUP_FAILED event."""
    return Event(
        type=EventType.AUTH_SETUP_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data={"auth_type": auth_type},
    )


def infrastructure_ready_event(
    source: str,
    docker_configured: bool = False,
    ci_configured: bool = False,
    env_configured: bool = False,
) -> Event:
    """Create INFRASTRUCTURE_READY event."""
    return Event(
        type=EventType.INFRASTRUCTURE_READY,
        source=source,
        success=True,
        data={
            "docker_configured": docker_configured,
            "ci_configured": ci_configured,
            "env_configured": env_configured,
        },
    )


def infrastructure_failed_event(
    source: str,
    error_message: str,
) -> Event:
    """Create ENV_CONFIG_FAILED event for InfrastructureAgent."""
    return Event(
        type=EventType.ENV_CONFIG_FAILED,
        source=source,
        success=False,
        error_message=error_message,
    )


def env_config_generated_event(
    source: str,
    docker_enabled: bool = False,
    ci_enabled: bool = False,
    ci_provider: str = "github",
    files_created: Optional[list[str]] = None,
) -> Event:
    """Create ENV_CONFIG_GENERATED event for InfrastructureAgent."""
    return Event(
        type=EventType.ENV_CONFIG_GENERATED,
        source=source,
        success=True,
        data={
            "docker_enabled": docker_enabled,
            "ci_enabled": ci_enabled,
            "ci_provider": ci_provider,
            "files_created": files_created or [],
        },
    )


# =========================================================================
# Docker Orchestrator Agent Events
# =========================================================================


def code_generated_event(
    source: str,
    task: Optional[str] = None,
    files_created: Optional[list[str]] = None,
) -> Event:
    """Create CODE_GENERATED event for code/config generation."""
    data = {}
    if task:
        data["task"] = task
    if files_created:
        data["files_created"] = files_created
    return Event(
        type=EventType.CODE_GENERATED,
        source=source,
        success=True,
        data=data if data else None,
    )


# =========================================================================
# Dependency Manager Agent Events
# =========================================================================


def dependency_check_started_event(
    source: str,
    working_dir: Optional[str] = None,
) -> Event:
    """Create DEPENDENCY_CHECK_STARTED event."""
    data = {}
    if working_dir:
        data["working_dir"] = working_dir
    return Event(
        type=EventType.DEPENDENCY_CHECK_STARTED,
        source=source,
        data=data if data else None,
    )


def dependency_check_passed_event(
    source: str,
    project_type: Optional[str] = None,
    message: Optional[str] = None,
) -> Event:
    """Create DEPENDENCY_CHECK_PASSED event."""
    data = {}
    if project_type:
        data["project_type"] = project_type
    if message:
        data["message"] = message
    return Event(
        type=EventType.DEPENDENCY_CHECK_PASSED,
        source=source,
        success=True,
        data=data if data else None,
    )


def dependency_outdated_event(
    source: str,
    packages: Optional[list[dict]] = None,
    count: int = 0,
) -> Event:
    """Create DEPENDENCY_OUTDATED event."""
    return Event(
        type=EventType.DEPENDENCY_OUTDATED,
        source=source,
        data={
            "packages": packages or [],
            "count": count,
        },
    )


def dependency_conflict_event(
    source: str,
    conflict_type: Optional[str] = None,
    message: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> Event:
    """Create DEPENDENCY_CONFLICT event."""
    data = {}
    if conflict_type:
        data["type"] = conflict_type
    if message:
        data["message"] = message
    if extra_data:
        data.update(extra_data)
    return Event(
        type=EventType.DEPENDENCY_CONFLICT,
        source=source,
        data=data if data else None,
    )


def dependency_updated_event(
    source: str,
    name: Optional[str] = None,
    from_version: Optional[str] = None,
    to_version: Optional[str] = None,
    update_type: Optional[str] = None,
    data: Optional[dict] = None,
) -> Event:
    """Create DEPENDENCY_UPDATED event."""
    event_data = data.copy() if data else {}
    if name:
        event_data["name"] = name
    if from_version:
        event_data["from"] = from_version
    if to_version:
        event_data["to"] = to_version
    if update_type:
        event_data["update_type"] = update_type
    return Event(
        type=EventType.DEPENDENCY_UPDATED,
        source=source,
        success=True,
        data=event_data if event_data else None,
    )


def license_issue_found_event(
    source: str,
    package: Optional[str] = None,
    license_type: Optional[str] = None,
    severity: str = "medium",
    message: Optional[str] = None,
) -> Event:
    """Create LICENSE_ISSUE_FOUND event."""
    data = {"severity": severity}
    if package:
        data["package"] = package
    if license_type:
        data["license"] = license_type
    if message:
        data["message"] = message
    return Event(
        type=EventType.LICENSE_ISSUE_FOUND,
        source=source,
        data=data,
    )


# =========================================================================
# Security Scanner Agent Events
# =========================================================================


def security_scan_started_event(
    source: str,
    working_dir: Optional[str] = None,
) -> Event:
    """Create SECURITY_SCAN_STARTED event."""
    data = {}
    if working_dir:
        data["working_dir"] = working_dir
    return Event(
        type=EventType.SECURITY_SCAN_STARTED,
        source=source,
        data=data if data else None,
    )


def security_scan_passed_event(
    source: str,
    vulnerabilities_total: int = 0,
    secrets_found: int = 0,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
) -> Event:
    """Create SECURITY_SCAN_PASSED event."""
    return Event(
        type=EventType.SECURITY_SCAN_PASSED,
        source=source,
        success=True,
        data={
            "vulnerabilities_total": vulnerabilities_total,
            "secrets_found": secrets_found,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "passed": True,
        },
    )


def security_scan_failed_event(
    source: str,
    error_message: Optional[str] = None,
    vulnerabilities_total: int = 0,
    secrets_found: int = 0,
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
) -> Event:
    """Create SECURITY_SCAN_FAILED event."""
    return Event(
        type=EventType.SECURITY_SCAN_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data={
            "vulnerabilities_total": vulnerabilities_total,
            "secrets_found": secrets_found,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "passed": False,
        },
    )


def vulnerability_detected_event(
    source: str,
    file_path: Optional[str] = None,
    vuln_type: Optional[str] = None,
    severity: str = "medium",
    description: Optional[str] = None,
    line: Optional[int] = None,
    extra_data: Optional[dict] = None,
) -> Event:
    """Create VULNERABILITY_DETECTED event."""
    data = {"severity": severity}
    if vuln_type:
        data["type"] = vuln_type
    if description:
        data["description"] = description
    if line:
        data["line"] = line
    if extra_data:
        data.update(extra_data)
    return Event(
        type=EventType.VULNERABILITY_DETECTED,
        source=source,
        file_path=file_path,
        data=data,
    )


def secret_leaked_event(
    source: str,
    file_path: Optional[str] = None,
    secret_type: Optional[str] = None,
    line: Optional[int] = None,
    description: Optional[str] = None,
) -> Event:
    """Create SECRET_LEAKED event."""
    data = {"severity": "critical"}
    if secret_type:
        data["secret_type"] = secret_type
    if line:
        data["line"] = line
    if description:
        data["description"] = description
    return Event(
        type=EventType.SECRET_LEAKED,
        source=source,
        file_path=file_path,
        data=data,
    )


def security_fix_needed_event(
    source: str,
    file_path: Optional[str] = None,
    vulnerability: Optional[dict] = None,
    fix_suggestion: Optional[str] = None,
) -> Event:
    """Create SECURITY_FIX_NEEDED event."""
    data = {}
    if vulnerability:
        data["vulnerability"] = vulnerability
    if fix_suggestion:
        data["fix_suggestion"] = fix_suggestion
    return Event(
        type=EventType.SECURITY_FIX_NEEDED,
        source=source,
        file_path=file_path,
        data=data if data else None,
    )


def dependency_vulnerability_event(
    source: str,
    package: Optional[str] = None,
    severity: Optional[str] = None,
    fix_available: bool = False,
) -> Event:
    """Create DEPENDENCY_VULNERABILITY event."""
    data = {}
    if package:
        data["package"] = package
    if severity:
        data["severity"] = severity
    data["fix_available"] = fix_available
    return Event(
        type=EventType.DEPENDENCY_VULNERABILITY,
        source=source,
        data=data,
    )


# =========================================================================
# E2E Testing Events
# =========================================================================


def e2e_test_passed_event(
    source: str,
    data: Optional[dict] = None,
) -> Event:
    """Create E2E_TEST_PASSED event."""
    return Event(
        type=EventType.E2E_TEST_PASSED,
        source=source,
        success=True,
        data=data,
    )


def e2e_test_failed_event(
    source: str,
    error_message: Optional[str] = None,
    data: Optional[dict] = None,
) -> Event:
    """Create E2E_TEST_FAILED event."""
    return Event(
        type=EventType.E2E_TEST_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data=data,
    )


# =========================================================================
# Test Result Events
# =========================================================================


def tests_passed_event(
    source: str,
    validation_number: Optional[int] = None,
    tests_passed: int = 0,
    tests_total: int = 0,
    pass_rate: float = 0.0,
    debug_iterations: int = 0,
    fixes_applied: int = 0,
    execution_time_ms: int = 0,
) -> Event:
    """Create TESTS_PASSED event."""
    data = {
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "pass_rate": pass_rate,
        "debug_iterations": debug_iterations,
        "fixes_applied": fixes_applied,
        "execution_time_ms": execution_time_ms,
    }
    if validation_number is not None:
        data["validation_number"] = validation_number
    return Event(
        type=EventType.TESTS_PASSED,
        source=source,
        success=True,
        data=data,
    )


def tests_failed_event(
    source: str,
    error_message: Optional[str] = None,
    validation_number: Optional[int] = None,
    tests_passed: int = 0,
    tests_failed: int = 0,
    tests_total: int = 0,
    data: Optional[dict] = None,
) -> Event:
    """Create TESTS_FAILED event."""
    event_data = data or {}
    if validation_number is not None:
        event_data["validation_number"] = validation_number
    event_data["tests_passed"] = tests_passed
    event_data["tests_failed"] = tests_failed
    event_data["tests_total"] = tests_total
    return Event(
        type=EventType.TESTS_FAILED,
        source=source,
        success=False,
        error_message=error_message,
        data=event_data,
    )


# =========================================================================
# Debug Events
# =========================================================================


def debug_complete_event(
    source: str,
    success: bool,
    error_message: Optional[str] = None,
    cycle: Optional[int] = None,
    errors_found: int = 0,
    data: Optional[dict] = None,
) -> Event:
    """Create DEBUG_COMPLETE event."""
    event_data = data or {}
    if cycle is not None:
        event_data["cycle"] = cycle
    event_data["errors_found"] = errors_found
    return Event(
        type=EventType.DEBUG_COMPLETE,
        source=source,
        success=success,
        error_message=error_message,
        data=event_data,
    )


# =========================================================================
# Validation Events
# =========================================================================


def validation_passed_event(
    source: str,
    check_type: str = "runtime",
    project_type: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[dict] = None,
) -> Event:
    """Create VALIDATION_PASSED event."""
    event_data = data or {}
    event_data["check_type"] = check_type
    if project_type:
        event_data["project_type"] = project_type
    if message:
        event_data["message"] = message
    return Event(
        type=EventType.VALIDATION_PASSED,
        source=source,
        success=True,
        data=event_data,
    )


def validation_error_event(
    source: str,
    error_message: Optional[str] = None,
    check_type: str = "runtime",
    project_type: Optional[str] = None,
    fix_attempts: int = 0,
    data: Optional[dict] = None,
) -> Event:
    """Create VALIDATION_ERROR event."""
    event_data = data or {}
    event_data["check_type"] = check_type
    if project_type:
        event_data["project_type"] = project_type
    event_data["fix_attempts"] = fix_attempts
    return Event(
        type=EventType.VALIDATION_ERROR,
        source=source,
        success=False,
        error_message=error_message,
        data=event_data,
    )


# =========================================================================
# Global EventBus Singleton
# =========================================================================

_event_bus_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    Get or create the global EventBus singleton.

    Returns:
        The global EventBus instance

    Usage:
        from src.mind.event_bus import get_event_bus

        event_bus = get_event_bus()
        await event_bus.publish(Event(...))
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance


def reset_event_bus() -> None:
    """Reset the global EventBus singleton (for testing)."""
    global _event_bus_instance
    _event_bus_instance = None


# =============================================================================
# Git Push Agent Event Helpers
# =============================================================================

def git_push_started_event(
    source: str,
    branch: str,
    remote: str = "origin",
    files_changed: Optional[list] = None,
) -> Event:
    """Create GIT_PUSH_STARTED event."""
    return Event(
        type=EventType.GIT_PUSH_STARTED,
        source=source,
        data={
            "branch": branch,
            "remote": remote,
            "files_changed": files_changed or [],
        },
    )


def git_push_succeeded_event(
    source: str,
    branch: str,
    commit_hash: str,
    commit_message: str,
    files_committed: Optional[list] = None,
    remote: str = "origin",
) -> Event:
    """Create GIT_PUSH_SUCCEEDED event."""
    return Event(
        type=EventType.GIT_PUSH_SUCCEEDED,
        source=source,
        success=True,
        data={
            "branch": branch,
            "commit_hash": commit_hash,
            "commit_message": commit_message,
            "files_committed": files_committed or [],
            "remote": remote,
        },
    )


def git_push_failed_event(
    source: str,
    branch: str,
    error: str,
    error_type: str = "unknown",
    remote: str = "origin",
) -> Event:
    """Create GIT_PUSH_FAILED event."""
    return Event(
        type=EventType.GIT_PUSH_FAILED,
        source=source,
        success=False,
        error_message=error,
        data={
            "branch": branch,
            "remote": remote,
            "error_type": error_type,
        },
    )


def git_commit_created_event(
    source: str,
    commit_hash: str,
    commit_message: str,
    branch: str,
    files_committed: Optional[list] = None,
) -> Event:
    """Create GIT_COMMIT_CREATED event."""
    return Event(
        type=EventType.GIT_COMMIT_CREATED,
        source=source,
        success=True,
        data={
            "commit_hash": commit_hash,
            "commit_message": commit_message,
            "branch": branch,
            "files_committed": files_committed or [],
        },
    )


def pattern_learned_event(
    source: str,
    pattern_type: str,
    pattern_key: str,
    confidence: float = 0.0,
    metadata: Optional[dict] = None,
) -> Event:
    """Create PATTERN_LEARNED event for Supermemory RAG integration."""
    return Event(
        type=EventType.PATTERN_LEARNED,
        source=source,
        success=True,
        data={
            "pattern_type": pattern_type,
            "pattern_key": pattern_key,
            "confidence": confidence,
            "metadata": metadata or {},
        },
    )
