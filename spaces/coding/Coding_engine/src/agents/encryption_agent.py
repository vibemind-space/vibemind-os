"""
EncryptionAgent - Implements end-to-end encryption (E2EE) for messaging platforms.

This agent handles all cryptographic operations for secure messaging:
- ECDH key exchange protocol (Double Ratchet / Signal Protocol inspired)
- Message encryption/decryption middleware
- Secure key storage and rotation
- Device fingerprinting and verification
- Key backup and recovery

Architecture:
    AuthAgent (AUTH_SETUP_COMPLETE)
        ↓
    EncryptionAgent → Crypto services + Key management
        ↓
    E2EE_CONFIGURED (messages can now be encrypted)

Uses AutoGen Team pattern:
    EncryptionOperator (has Claude Code tool) + EncryptionValidator (security review)

CRITICAL: This agent generates security-sensitive code. All output MUST be reviewed.
"""

import asyncio
from pathlib import Path
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from src.mind.event_bus import Event, EventType

logger = structlog.get_logger(__name__)


class EncryptionAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for end-to-end encryption in messaging platforms.

    Generates:
    - Key exchange service (ECDH / X25519)
    - Message encryption middleware
    - Key storage service (secure, encrypted at rest)
    - Device registration and fingerprinting
    - Key verification UI helpers

    Uses AutoGen RoundRobinGroupChat:
        EncryptionOperator: Generates crypto code using Claude Code tool
        EncryptionValidator: Security-focused review for cryptographic correctness

    WARNING: Cryptographic code requires careful review. This agent generates
    implementations based on established patterns (Signal Protocol) but should
    NOT be used in production without security audit.
    """

    def __init__(
        self,
        name: str = "encryption_agent",
        working_dir: str = "./output",
        event_bus=None,
        shared_state=None,
        skill_loader=None,  # Kept for backwards compatibility, not used
        **kwargs,
    ):
        super().__init__(
            name=name,
            working_dir=working_dir,
            event_bus=event_bus,
            shared_state=shared_state,
            **kwargs,
        )
        self.skill_loader = skill_loader  # Store locally if needed
        self.logger = logger.bind(agent=self.name)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent responds to."""
        return [
            EventType.AUTH_SETUP_COMPLETE,
            EventType.GENERATION_COMPLETE,  # After presence, may trigger encryption
            # EventType.ENCRYPTION_REQUIRED,  # Add when defined in event_bus.py
        ]

    def should_act(self, events: list[Event]) -> bool:
        """Determine if agent should act based on events."""
        if not events:
            return False

        for event in events:
            # Act when auth is complete (encryption depends on user identity)
            if event.type == EventType.AUTH_SETUP_COMPLETE:
                return True
            # Act on explicit encryption request
            if event.type == EventType.GENERATION_COMPLETE:
                # Check if this is from presence agent (chain trigger)
                if event.data.get("agent") == "presence_agent":
                    return True

        return False

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "auth"  # Uses security/auth context for encryption

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate end-to-end encryption infrastructure.

        Uses AutoGen team if available, otherwise falls back to legacy mode.
        """
        self.logger.info(
            "encryption_agent_acting",
            event_count=len(events),
            event_types=[e.event_type.value for e in events],
        )

        # Use AutoGen team pattern if available
        if self.is_autogen_available():
            return await self._act_with_autogen_team(events)

        # Fallback to legacy implementation
        return await self._act_legacy(events)

    # -------------------------------------------------------------------------
    # AutoGen Team Implementation
    # -------------------------------------------------------------------------

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """Execute encryption generation using AutoGen RoundRobinGroupChat."""
        self.logger.info("encryption_autogen_team_starting")

        try:
            # Get RAG context for encryption patterns
            context = await self.get_task_context(
                query="encryption E2EE ECDH key exchange cryptography NestJS libsodium tweetnacl",
                epic_id=events[0].data.get("epic_id") if events and events[0].data else None,
            )

            # Build task prompt with context
            encryption_prompt = self._build_encryption_prompt(events)

            # Inject RAG results into prompt
            if context and context.rag_results:
                encryption_prompt += "\n\n## Relevant Code Examples (from RAG)"
                for result in context.rag_results[:3]:
                    file_path = result.get("relative_path", result.get("file_path", "unknown"))
                    content = result.get("content", "")[:500]
                    score = result.get("score", 0)
                    encryption_prompt += f"\n### {file_path} (score: {score:.2f})\n```\n{content}\n```"

                self.logger.info(
                    "rag_context_injected",
                    rag_results_count=len(context.rag_results),
                )

            task = self.build_task_prompt(events, extra_context=encryption_prompt)

            # Create Claude Code tools for the Operator
            claude_code_tools = self._create_claude_code_tools()

            # Create Operator + Validator team
            team = self.create_team(
                operator_name="EncryptionOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="EncryptionValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=claude_code_tools,
                max_turns=15,  # Encryption may need more iterations
            )

            # Execute team
            result = await self.run_team(team, task)

            if result["success"]:
                self.logger.info(
                    "encryption_generation_complete",
                    files_created=result.get("files_mentioned", []),
                )

                return Event(
                    event_type=EventType.GENERATION_COMPLETE,  # Or E2EE_CONFIGURED when defined
                    source=self.name,
                    data={
                        "agent": self.name,
                        "task": "end_to_end_encryption",
                        "files": result.get("files_mentioned", []),
                        "result_summary": result.get("result_text", "")[:500],
                        "features": [
                            "ecdh_key_exchange",
                            "message_encryption",
                            "key_storage",
                            "device_fingerprinting",
                            "key_verification",
                        ],
                        "security_notice": "Generated crypto code requires security audit before production use",
                    },
                )
            else:
                self.logger.error(
                    "encryption_generation_failed",
                    error=result.get("error", "Unknown error"),
                )
                return Event(
                    event_type=EventType.BUILD_FAILED,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "error": result.get("error", "Encryption generation failed"),
                    },
                )

        except Exception as e:
            self.logger.exception("encryption_autogen_team_error", error=str(e))
            return Event(
                event_type=EventType.BUILD_FAILED,
                source=self.name,
                data={"agent": self.name, "error": str(e)},
            )

    def _build_encryption_prompt(self, events: list[Event]) -> str:
        """Build detailed prompt for encryption generation."""
        # Extract context from events
        auth_context = ""
        for event in events:
            if event.type == EventType.AUTH_SETUP_COMPLETE:
                auth_context = event.data.get("result_summary", "")

        return f"""
## End-to-End Encryption (E2EE) System Generation

### Context
Authentication system is ready. Now implement E2EE for message privacy.

{f"Auth Context: {auth_context}" if auth_context else ""}

### Security Notice
This code is for EDUCATIONAL/PROTOTYPE purposes. Production E2EE requires:
- Security audit by cryptography experts
- Use of well-tested libraries (libsignal, libsodium)
- Key management infrastructure

### Required Components

#### 1. Key Exchange Service (`src/crypto/key-exchange.service.ts`)
- X25519 ECDH key pair generation
- Pre-key bundle creation (identity key, signed pre-key, one-time pre-keys)
- Key agreement protocol (derive shared secret)
- Use tweetnacl or libsodium-wrappers

```typescript
interface PreKeyBundle {{
  identityKey: Uint8Array;        // Long-term identity
  signedPreKey: Uint8Array;       // Rotated periodically
  signedPreKeySignature: Uint8Array;
  oneTimePreKey?: Uint8Array;     // Used once, then discarded
}}
```

#### 2. Message Encryption Service (`src/crypto/message-crypto.service.ts`)
- Encrypt message with shared secret (XChaCha20-Poly1305)
- Include message key in header (encrypted with ratchet key)
- Support for media encryption (separate keys)

```typescript
interface EncryptedMessage {{
  ciphertext: Uint8Array;
  nonce: Uint8Array;
  header: {{
    publicKey: Uint8Array;  // Sender's ephemeral key
    messageNumber: number;
    previousChainLength: number;
  }};
}}
```

#### 3. Double Ratchet Service (`src/crypto/double-ratchet.service.ts`)
- Symmetric key ratchet (per message)
- Diffie-Hellman ratchet (per round-trip)
- Out-of-order message handling
- Session state management

#### 4. Key Storage Service (`src/crypto/key-storage.service.ts`)
- Secure storage of identity keys (encrypted at rest)
- Session state persistence
- Key backup to server (encrypted with user password)
- Cross-device key sync

#### 5. Device Fingerprint Service (`src/crypto/device-fingerprint.service.ts`)
- Generate unique device fingerprint
- Register device with server
- Safety number generation (for verification)
- QR code generation for in-person verification

#### 6. Encryption Middleware (`src/crypto/encryption.middleware.ts`)
- Intercept outgoing messages → encrypt
- Intercept incoming messages → decrypt
- Handle key exchange automatically
- Graceful fallback for unencrypted legacy messages

### Technical Requirements
- Use tweetnacl or libsodium-wrappers (NOT Node's crypto for EC operations)
- All keys stored encrypted (AES-256-GCM with user-derived key)
- Implement constant-time comparisons for MACs
- Clear sensitive data from memory after use
- Generate cryptographically secure random numbers (crypto.getRandomValues)

### Output Directory
{self.working_dir}

### IMPORTANT
1. Do NOT implement your own cryptographic primitives
2. Use established libraries for all crypto operations
3. Include appropriate security warnings in generated code
4. Implement proper error handling (don't leak information)
"""

    def _get_operator_system_prompt(self) -> str:
        """System prompt for EncryptionOperator agent."""
        return """You are EncryptionOperator, an expert in cryptographic systems and secure messaging.

Your role is to generate end-to-end encryption code following established security patterns.

## Expertise
- Elliptic Curve Diffie-Hellman (ECDH) key exchange
- Signal Protocol / Double Ratchet algorithm
- Authenticated encryption (XChaCha20-Poly1305)
- Secure key storage and management
- Device fingerprinting and verification

## CRITICAL Security Rules
1. NEVER implement custom cryptographic primitives
2. ALWAYS use established libraries (tweetnacl, libsodium-wrappers)
3. Use crypto.getRandomValues() for randomness (NOT Math.random())
4. Implement constant-time comparisons for all MACs/signatures
5. Clear sensitive data from memory after use (overwrite with zeros)
6. Include security warnings in generated code

## Code Standards
1. TypeScript with strict types for all crypto operations
2. Use Uint8Array for binary data (NOT strings)
3. Proper error handling without information leakage
4. Comprehensive JSDoc with security notes
5. Follow OWASP cryptographic guidelines

## Libraries to Use
- tweetnacl: For X25519, Ed25519, XSalsa20-Poly1305
- libsodium-wrappers: For XChaCha20-Poly1305, Argon2
- buffer: For Uint8Array/Buffer conversions

When you receive a task:
1. Analyze security requirements carefully
2. Use the generate_encryption_code tool to create each component
3. Include appropriate security warnings
4. Ensure proper key lifecycle management

After completing all components, say "TERMINATE" to signal completion."""

    def _get_validator_system_prompt(self) -> str:
        """System prompt for EncryptionValidator agent."""
        return """You are EncryptionValidator, a security expert reviewing cryptographic implementations.

Your role is to ensure generated encryption code is secure and follows best practices.

## Security Review Checklist
1. **No Custom Crypto**: Verify only standard libraries are used
2. **Proper Randomness**: crypto.getRandomValues(), NOT Math.random()
3. **Key Management**: Keys encrypted at rest, cleared after use
4. **Constant-Time**: MAC comparisons are timing-safe
5. **No Information Leakage**: Error messages don't reveal sensitive info
6. **Proper Nonces**: Never reused, generated securely
7. **Key Rotation**: Pre-keys and session keys rotated appropriately

## Common Vulnerabilities to Catch
- Nonce reuse (catastrophic for XChaCha20)
- Timing attacks in comparisons
- Weak key derivation (use Argon2 or HKDF)
- Sensitive data in logs
- Missing authentication (encrypt-then-MAC)
- Improper error handling

## Crypto-Specific Issues
- Identity key stored unencrypted
- Session state not persisted securely
- Missing signature verification on pre-keys
- One-time pre-keys reused
- Double ratchet state corruption

## Review Process
1. Check each generated file for security issues
2. Verify library usage is correct
3. Look for information leakage in errors
4. Ensure all keys have proper lifecycle

If code passes review, respond with "SECURITY_APPROVED - [summary]"
If issues found, respond with "SECURITY_ISSUE - [critical issues]"

When all code is security-approved, say "TERMINATE" to signal completion."""

    def _create_claude_code_tools(self) -> list:
        """Create Claude Code as FunctionTool for AutoGen."""
        try:
            from autogen_core.tools import FunctionTool
        except ImportError:
            self.logger.warning("autogen_tools_not_available")
            return []

        from src.tools.claude_code_tool import ClaudeCodeTool

        claude_tool = ClaudeCodeTool(
            working_dir=self.working_dir,
            skill_loader=self.skill_loader,
        )

        async def generate_encryption_code(
            prompt: str,
            context: str = "",
            component_type: str = "service",
        ) -> dict:
            """
            Generate encryption/crypto code using Claude Code.

            Args:
                prompt: What to generate (e.g., "Create key exchange service")
                context: Additional context (security requirements)
                component_type: Type (service, middleware, utility)

            Returns:
                Dictionary with success status and generated file info
            """
            security_preamble = """
## SECURITY REQUIREMENTS
- Use tweetnacl or libsodium-wrappers for all crypto operations
- NEVER use Math.random() - only crypto.getRandomValues()
- Include security warnings in code comments
- Clear sensitive data from memory after use
- Implement constant-time comparisons for MACs

"""
            full_prompt = f"""
{security_preamble}

## Task
{prompt}

## Component Type
{component_type}

## Context
{context}

## Technical Stack
- NestJS with TypeScript
- tweetnacl or libsodium-wrappers for crypto
- Proper TypeScript types for all crypto operations
"""

            try:
                result = await claude_tool.execute(
                    prompt=full_prompt,
                    context=context,
                    agent_type="backend",
                )

                return {
                    "success": result.success,
                    "files_created": result.files_created if hasattr(result, "files_created") else [],
                    "files_modified": result.files_modified if hasattr(result, "files_modified") else [],
                    "summary": result.summary if hasattr(result, "summary") else "",
                    "error": result.error if hasattr(result, "error") else None,
                    "security_notice": "Generated code requires security audit",
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "files_created": [],
                    "files_modified": [],
                }

        return [
            FunctionTool(
                func=generate_encryption_code,
                name="generate_encryption_code",
                description="Generate encryption/crypto code (key exchange, message crypto, storage) using Claude Code. "
                "SECURITY-SENSITIVE: Generated code requires audit before production use.",
            )
        ]

    # -------------------------------------------------------------------------
    # Legacy Implementation (Fallback)
    # -------------------------------------------------------------------------

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Legacy implementation without AutoGen."""
        self.logger.info("encryption_legacy_mode")

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            claude_tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                skill_loader=self.skill_loader,
            )

            prompt = self._build_encryption_prompt(events)

            result = await claude_tool.execute(
                prompt=prompt,
                context="Generate E2EE system with security focus",
                agent_type="backend",
            )

            if result.success:
                return Event(
                    event_type=EventType.GENERATION_COMPLETE,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "task": "end_to_end_encryption",
                        "files": result.files_created if hasattr(result, "files_created") else [],
                        "security_notice": "Generated crypto code requires security audit",
                    },
                )
            else:
                return Event(
                    event_type=EventType.BUILD_FAILED,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "error": result.error if hasattr(result, "error") else "Unknown error",
                    },
                )

        except Exception as e:
            self.logger.exception("encryption_legacy_error", error=str(e))
            return Event(
                event_type=EventType.BUILD_FAILED,
                source=self.name,
                data={"agent": self.name, "error": str(e)},
            )

    # -------------------------------------------------------------------------
    # Swarm Handoff Configuration (for AutogenSwarmMixin)
    # -------------------------------------------------------------------------

    def get_handoff_targets(self) -> dict[str, str]:
        """Define handoff targets for Swarm pattern."""
        return {
            "E2EE_CONFIGURED": "infrastructure_agent",  # After E2EE, setup infra
            "ENCRYPTION_COMPLETE": "validation_team_agent",  # Validate encryption
        }

    def get_agent_capabilities(self) -> list[str]:
        """Define capabilities for Swarm routing."""
        return [
            "encryption",
            "e2ee",
            "key_exchange",
            "ecdh",
            "double_ratchet",
            "message_crypto",
            "key_storage",
            "device_fingerprint",
            "security",
        ]
