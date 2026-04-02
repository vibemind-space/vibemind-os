"""
Contract Generator - Generates interface contracts from requirements.

This module analyzes requirements and generates:
1. Shared type definitions
2. API endpoint contracts
3. Component contracts
4. Service interfaces
5. File ownership mappings
"""
import re
from typing import Optional
import structlog

from src.engine.dag_parser import RequirementsData
from src.engine.contracts import (
    InterfaceContracts,
    TypeDefinition,
    APIEndpoint,
    ComponentContract,
    ServiceContract,
)

logger = structlog.get_logger()


class ContractGenerator:
    """
    Generates interface contracts from requirements analysis.

    Uses heuristics to identify:
    - Data models from requirement descriptions
    - API endpoints from backend requirements
    - UI components from frontend requirements
    - Service interfaces from business logic requirements
    """

    def __init__(self, working_dir: str | None = None):
        """
        Initialize the contract generator.

        Args:
            working_dir: Working directory for Claude CLI (avoids CLAUDE.md context interference)
        """
        self.logger = logger.bind(component="contract_generator")
        self.working_dir = working_dir

        # Patterns for identifying different contract types
        # Extended to catch implicit API requirements (data management = needs endpoints)
        self.api_patterns = [
            # Explicit API mentions
            r"(?i)(?:api|rest|endpoint|route|service)",
            r"(?i)http\s+(?:get|post|put|delete|patch)",
            # Implicit API requirements (data management = needs endpoints)
            r"(?i)(?:manage|track|store|persist|save|fetch|retrieve|list|create|update|delete|search|filter)",
            r"(?i)(?:display|show|list|retrieve).+(?:data|information|list|items)",
            r"(?i)(?:submit|send|receive).+(?:data|request|form)",
            # CRUD operations
            r"(?i)(?:create|add|new|delete|remove|update|edit|modify|query|search|filter).+(?:entry|item|record|resource|entity)",
            # Data persistence patterns
            r"(?i)(?:database|db|storage|repository|collection)",
            # Backend service patterns
            r"(?i)(?:backend|server|api).+(?:for|to|that)",
        ]

        self.model_patterns = [
            r"data\s+model",
            r"database\s+schema",
            r"entity\s+for",
            r"store\s+(\w+)",
            r"track\s+(\w+)",
        ]

        self.component_patterns = [
            r"ui\s+component",
            r"display\s+(\w+)",
            r"form\s+for",
            r"button\s+to",
            r"panel\s+showing",
            r"overlay",
            r"window",
        ]

        self.service_patterns = [
            r"service\s+for",
            r"handler\s+for",
            r"processor",
            r"manager",
            r"controller",
        ]

    def generate(
        self,
        req_data: RequirementsData,
        project_name: str = "Generated Project",
    ) -> InterfaceContracts:
        """
        Generate interface contracts from requirements.

        Args:
            req_data: Parsed requirements data
            project_name: Name of the project

        Returns:
            InterfaceContracts with all identified interfaces
        """
        self.logger.info(
            "generating_contracts",
            requirements=len(req_data.requirements),
        )

        contracts = InterfaceContracts(project_name=project_name)

        # Analyze each requirement
        for req in req_data.requirements:
            title = req.get("title", "").lower()
            description = req.get("description", "").lower()
            req_id = req.get("id", "")
            tags = req.get("tags", [])

            combined_text = f"{title} {description}"

            # Identify models/types
            if self._matches_patterns(combined_text, self.model_patterns):
                type_def = self._extract_type(req)
                if type_def:
                    contracts.add_type(type_def)

            # Identify API endpoints
            if self._matches_patterns(combined_text, self.api_patterns):
                endpoint = self._extract_endpoint(req)
                if endpoint:
                    contracts.add_endpoint(endpoint)

            # Identify UI components
            if self._matches_patterns(combined_text, self.component_patterns):
                component = self._extract_component(req)
                if component:
                    contracts.add_component(component)

            # Identify services
            if self._matches_patterns(combined_text, self.service_patterns):
                service = self._extract_service(req)
                if service:
                    contracts.add_service(service)

        # Generate file ownership based on tags
        contracts.file_ownership = self._generate_file_ownership(req_data)

        # Add default types if none were found
        if not contracts.types:
            contracts.types = self._generate_default_types(req_data)

        self.logger.info(
            "contracts_generated",
            types=len(contracts.types),
            endpoints=len(contracts.endpoints),
            components=len(contracts.components),
            services=len(contracts.services),
        )

        return contracts

    def _matches_patterns(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the patterns."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _extract_type(self, req: dict) -> Optional[TypeDefinition]:
        """Extract a type definition from a requirement."""
        title = req.get("title", "")

        # Try to extract entity name
        name_match = re.search(
            r"(?:model|entity|schema)\s+(?:for\s+)?(\w+)",
            title,
            re.IGNORECASE,
        )

        if name_match:
            entity_name = name_match.group(1).title()
        else:
            # Generate name from title
            words = re.findall(r"\b[A-Z][a-z]+\b", title.title())
            entity_name = "".join(words[:2]) if words else "Entity"

        # Generate common fields based on context
        fields = {"id": "str"}

        title_lower = title.lower()
        if "user" in title_lower:
            fields.update({"email": "str", "name": "str", "created_at": "str"})
        elif "mouse" in title_lower or "position" in title_lower:
            fields.update({"x": "float", "y": "float", "timestamp": "float"})
        elif "config" in title_lower or "setting" in title_lower:
            fields.update({"key": "str", "value": "str"})
        elif "session" in title_lower:
            fields.update({"start_time": "str", "end_time": "str", "data": "dict"})

        return TypeDefinition(
            name=entity_name,
            fields=fields,
            description=title,
        )

    def _extract_endpoint(self, req: dict) -> Optional[APIEndpoint]:
        """Extract an API endpoint from a requirement."""
        title = req.get("title", "")
        description = req.get("description", "")
        tags = req.get("tags", [])

        # Determine HTTP method
        method = "GET"
        if any(word in title.lower() for word in ["create", "add", "post", "submit"]):
            method = "POST"
        elif any(word in title.lower() for word in ["update", "edit", "modify"]):
            method = "PUT"
        elif any(word in title.lower() for word in ["delete", "remove"]):
            method = "DELETE"

        # Generate path from title
        path_words = re.findall(r"\b(\w+)\b", title.lower())
        resource = next(
            (w for w in path_words if w not in ["api", "endpoint", "for", "the", "a", "an"]),
            "resource"
        )
        path = f"/api/v1/{resource}s"

        return APIEndpoint(
            path=path,
            method=method,
            description=title,
            tags=tags,
        )

    def _extract_component(self, req: dict) -> Optional[ComponentContract]:
        """Extract a component contract from a requirement."""
        title = req.get("title", "")

        # Generate component name
        words = re.findall(r"\b[A-Z][a-z]+\b", title.title())
        component_name = "".join(words[:3]) if words else "Component"

        # Remove common non-component words
        for word in ["The", "For", "With", "And", "To"]:
            component_name = component_name.replace(word, "")

        # Generate common props based on component type
        props = {}
        events = []

        title_lower = title.lower()
        if "button" in title_lower:
            props = {"label": "string", "disabled": "boolean"}
            events = ["onClick"]
        elif "form" in title_lower:
            props = {"initialValues": "Record<string, any>"}
            events = ["onSubmit", "onChange"]
        elif "display" in title_lower or "panel" in title_lower:
            props = {"data": "any"}
        elif "overlay" in title_lower:
            props = {"visible": "boolean", "opacity": "number"}
            events = ["onClose"]

        return ComponentContract(
            name=component_name,
            props=props,
            description=title,
            events=events,
        )

    def _extract_service(self, req: dict) -> Optional[ServiceContract]:
        """Extract a service contract from a requirement."""
        title = req.get("title", "")

        # Generate service name
        words = re.findall(r"\b[A-Z][a-z]+\b", title.title())
        service_name = "".join(words[:2]) + "Service" if words else "Service"

        # Generate methods based on context
        methods = {}

        title_lower = title.lower()
        if "track" in title_lower or "record" in title_lower:
            methods["record"] = {
                "params": {"data": "dict"},
                "return_type": "bool",
                "description": "Record data",
            }
        if "process" in title_lower:
            methods["process"] = {
                "params": {"input": "Any"},
                "return_type": "Any",
                "description": "Process input",
            }
        if "get" in title_lower or "fetch" in title_lower:
            methods["get"] = {
                "params": {"id": "str"},
                "return_type": "Optional[dict]",
                "description": "Get by ID",
            }

        # Default method if none identified
        if not methods:
            methods["execute"] = {
                "params": {},
                "return_type": "bool",
                "description": title,
            }

        return ServiceContract(
            name=service_name,
            methods=methods,
            description=title,
        )

    def _generate_file_ownership(self, req_data: RequirementsData) -> dict[str, str]:
        """Generate file ownership mapping based on requirement tags."""
        ownership = {
            # Frontend patterns
            "src/components/**": "frontend",
            "src/pages/**": "frontend",
            "src/hooks/**": "frontend",
            "*.tsx": "frontend",
            "*.jsx": "frontend",
            "*.css": "frontend",

            # Backend patterns
            "src/api/**": "backend",
            "src/models/**": "backend",
            "src/services/**": "backend",
            "src/utils/**": "backend",
            "*.py": "backend",

            # Testing patterns
            "tests/**": "testing",
            "*_test.py": "testing",
            "*.test.ts": "testing",
            "*.test.tsx": "testing",

            # DevOps patterns
            "Dockerfile*": "devops",
            "docker-compose*.yml": "devops",
            ".github/**": "devops",
            "k8s/**": "devops",

            # Security patterns
            "security/**": "security",
        }

        return ownership

    def _generate_default_types(self, req_data: RequirementsData) -> list[TypeDefinition]:
        """Generate default types based on project analysis."""
        types = []

        # Check for common patterns in requirements
        all_text = " ".join(
            req.get("title", "") + " " + req.get("description", "")
            for req in req_data.requirements
        ).lower()

        # Mouse tracking project
        if "mouse" in all_text:
            types.append(TypeDefinition(
                name="MousePosition",
                fields={"x": "float", "y": "float", "timestamp": "float"},
                description="Mouse position data",
            ))

        if "session" in all_text:
            types.append(TypeDefinition(
                name="Session",
                fields={
                    "id": "str",
                    "start_time": "str",
                    "end_time": "str",
                    "data": "dict",
                },
                description="Recording session",
                optional_fields=["end_time"],
            ))

        if "config" in all_text or "setting" in all_text:
            types.append(TypeDefinition(
                name="Config",
                fields={"key": "str", "value": "str"},
                description="Configuration setting",
            ))

        # Always add a base Result type
        types.append(TypeDefinition(
            name="Result",
            fields={"success": "bool", "data": "Any", "error": "str"},
            description="Generic result type",
            optional_fields=["data", "error"],
        ))

        return types

    # =========================================================================
    # Phase 9: LLM-Enhanced Database Schema Inference
    # =========================================================================

    async def infer_schema_from_requirements(
        self,
        requirements: list[dict],
        include_audit_fields: bool = True,
        include_soft_delete: bool = True,
    ) -> str:
        """
        Use LLM to design a complete Prisma database schema from requirements.

        This method provides semantic understanding of business requirements
        to generate a proper database schema including:
        - Entity models with correct field types
        - Relations (one-to-one, one-to-many, many-to-many)
        - Indexes for performance
        - Soft delete support
        - Audit fields (createdAt, updatedAt)

        Args:
            requirements: List of requirement dicts with id, title, description
            include_audit_fields: Add createdAt/updatedAt to all models
            include_soft_delete: Add deletedAt for soft delete support

        Returns:
            Prisma schema as a string
        """
        import json

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            # Format requirements for LLM
            req_text = json.dumps(requirements[:30], indent=2)  # Limit for tokens

            audit_instruction = """
- Add `createdAt DateTime @default(now())`
- Add `updatedAt DateTime @updatedAt`""" if include_audit_fields else ""

            soft_delete_instruction = """
- Add `deletedAt DateTime?` for soft delete support
- Add `@@index([deletedAt])` for efficient filtering""" if include_soft_delete else ""

            prompt = f"""Design a complete Prisma database schema for these requirements:

## REQUIREMENTS:
{req_text}

## SCHEMA DESIGN TASK:

Analyze the requirements and create a Prisma schema that includes:

### 1. Entity Models
For each entity mentioned or implied in the requirements:
- Model name (PascalCase, singular: User not Users)
- Fields with appropriate Prisma types:
  - `String` for text, emails, names
  - `Int` for counts, quantities
  - `Float` for decimals, coordinates
  - `Boolean` for flags
  - `DateTime` for timestamps
  - `Json` for flexible nested data
  - `Enum` for fixed options
- Field modifiers: `?` for optional, `@unique`, `@default()`

### 2. Relations
- One-to-One: `@relation(fields: [foreignId], references: [id])`
- One-to-Many: `Post[] posts` on parent, `author User @relation(...)` on child
- Many-to-Many: Implicit `Tag[] tags` or explicit join table

### 3. Indexes
- `@@index([fieldName])` for frequently queried fields
- `@@unique([field1, field2])` for composite uniqueness

### 4. Standard Fields
{audit_instruction}
{soft_delete_instruction}
- Always include `id String @id @default(cuid())` or `@default(uuid())`

## RESPONSE FORMAT:

Return ONLY the Prisma schema, no explanation:

```prisma
generator client {{
  provider = "prisma-client-js"
}}

datasource db {{
  provider = "postgresql"
  url      = env("DATABASE_URL")
}}

model User {{
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  posts     Post[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}}

// ... more models
```

## GUIDELINES:
- Extract ALL entities from requirements (users, products, orders, etc.)
- Include join tables for many-to-many relationships
- Use enums for status fields (PENDING, ACTIVE, COMPLETED)
- Add `@@map("table_name")` if model name differs from table name
- Include appropriate indexes for foreign keys
"""

            tool = ClaudeCodeTool(working_dir=self.working_dir or ".", timeout=90)
            result = await tool.execute(
                prompt=prompt,
                context="Database schema inference from requirements",
                agent_type="schema_designer",
            )

            # Extract Prisma schema from response
            output = result.output or ""

            # Try to extract from code block
            prisma_match = re.search(r'```prisma\s*(.*?)\s*```', output, re.DOTALL)
            if prisma_match:
                schema = prisma_match.group(1).strip()

                self.logger.info(
                    "schema_inferred_from_requirements",
                    model_count=schema.count("model "),
                    enum_count=schema.count("enum "),
                    has_relations=("@relation" in schema),
                )

                return schema

            # Fallback: try to find schema without code block
            if "model " in output and "datasource " in output:
                # Find start of schema
                start_idx = output.find("generator client")
                if start_idx == -1:
                    start_idx = output.find("datasource db")
                if start_idx >= 0:
                    return output[start_idx:].strip()

        except Exception as e:
            self.logger.warning("llm_schema_inference_failed", error=str(e))

        # Fallback: generate basic schema from heuristics
        return self._fallback_schema_generation(requirements, include_audit_fields, include_soft_delete)

    def _fallback_schema_generation(
        self,
        requirements: list[dict],
        include_audit_fields: bool,
        include_soft_delete: bool,
    ) -> str:
        """
        Generate basic Prisma schema without LLM.

        Uses keyword extraction to identify entities and relationships.
        """
        entities = set()
        all_text = ""

        for req in requirements:
            title = req.get("title", "")
            description = req.get("description", "")
            all_text += f" {title} {description} "

            # Extract potential entity names
            # Look for "X management", "X tracking", "X list"
            entity_patterns = [
                r'\b(\w+)\s+(?:management|tracking|list|catalog|inventory)',
                r'(?:manage|track|store|create|delete)\s+(\w+)s?\b',
                r'\b(\w+)\s+(?:entity|model|record|data)',
            ]

            for pattern in entity_patterns:
                matches = re.findall(pattern, all_text, re.IGNORECASE)
                for match in matches:
                    if len(match) > 2 and match.lower() not in ['the', 'and', 'for', 'with']:
                        entities.add(match.title())

        # Common entities based on keywords
        all_text_lower = all_text.lower()
        if 'user' in all_text_lower or 'login' in all_text_lower or 'auth' in all_text_lower:
            entities.add('User')
        if 'product' in all_text_lower or 'item' in all_text_lower or 'catalog' in all_text_lower:
            entities.add('Product')
        if 'order' in all_text_lower or 'purchase' in all_text_lower:
            entities.add('Order')
        if 'category' in all_text_lower:
            entities.add('Category')

        # Build schema
        schema_parts = [
            'generator client {',
            '  provider = "prisma-client-js"',
            '}',
            '',
            'datasource db {',
            '  provider = "postgresql"',
            '  url      = env("DATABASE_URL")',
            '}',
            '',
        ]

        # Generate model for each entity
        for entity in sorted(entities):
            model_lines = [f'model {entity} {{', '  id String @id @default(cuid())']

            # Add entity-specific fields
            entity_lower = entity.lower()
            if entity_lower == 'user':
                model_lines.extend([
                    '  email    String @unique',
                    '  name     String?',
                    '  password String',
                ])
            elif entity_lower == 'product':
                model_lines.extend([
                    '  name        String',
                    '  description String?',
                    '  price       Float',
                    '  stock       Int      @default(0)',
                ])
            elif entity_lower == 'order':
                model_lines.extend([
                    '  userId    String',
                    '  status    String   @default("pending")',
                    '  total     Float',
                ])
            elif entity_lower == 'category':
                model_lines.extend([
                    '  name        String @unique',
                    '  description String?',
                ])
            else:
                model_lines.extend([
                    '  name        String',
                    '  description String?',
                ])

            # Add audit fields
            if include_audit_fields:
                model_lines.extend([
                    '  createdAt DateTime @default(now())',
                    '  updatedAt DateTime @updatedAt',
                ])

            # Add soft delete
            if include_soft_delete:
                model_lines.append('  deletedAt DateTime?')

            model_lines.append('}')
            model_lines.append('')

            schema_parts.extend(model_lines)

        return '\n'.join(schema_parts)

    async def infer_relations_with_llm(
        self,
        entities: list[dict],
    ) -> list[dict]:
        """
        Use LLM to design Prisma relations between entities.

        Args:
            entities: List of entity dicts with name and fields

        Returns:
            List of relation dicts with from, to, type, fields, onDelete
        """
        import json

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            entities_text = json.dumps(entities, indent=2)

            prompt = f"""Design Prisma relations between these entities:

## ENTITIES:
{entities_text}

## TASK:

For each relationship between entities, determine:

1. **Type**: one-to-one, one-to-many, many-to-many
2. **Field names** on both sides of the relation
3. **Cascade behavior**: Cascade, SetNull, Restrict, NoAction
4. **Is it optional?**
5. **Implicit many-to-many or explicit join table?**

## CONSIDERATIONS:

- Soft deletes: Use SetNull instead of Cascade to preserve history
- Tenant isolation: If multi-tenant, add tenant relation to all models
- Audit trails: Consider who created/updated records
- Orphan prevention: Restrict deletes if child records would be orphaned

## RESPONSE FORMAT:

```json
{{
  "relations": [
    {{
      "from": "User",
      "to": "Post",
      "type": "one-to-many",
      "from_field": "posts",
      "to_field": "author",
      "foreign_key": "authorId",
      "onDelete": "Cascade",
      "optional": false
    }},
    {{
      "from": "Post",
      "to": "Tag",
      "type": "many-to-many",
      "from_field": "tags",
      "to_field": "posts",
      "join_table": null,
      "onDelete": "Cascade",
      "optional": true
    }}
  ]
}}
```
"""

            tool = ClaudeCodeTool(working_dir=self.working_dir or ".", timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context="Prisma relation inference",
                agent_type="relation_designer",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))

                self.logger.info(
                    "relations_inferred",
                    count=len(analysis.get("relations", [])),
                )

                return analysis.get("relations", [])

        except Exception as e:
            self.logger.warning("llm_relation_inference_failed", error=str(e))

        return []


async def generate_contracts_for_requirements(
    req_data: RequirementsData,
    project_name: str = "Generated Project",
    working_dir: str | None = None,
) -> InterfaceContracts:
    """
    Convenience function to generate contracts.

    Args:
        req_data: Parsed requirements
        project_name: Project name
        working_dir: Working directory for Claude CLI (avoids CLAUDE.md context interference)

    Returns:
        InterfaceContracts
    """
    generator = ContractGenerator(working_dir=working_dir)
    return generator.generate(req_data, project_name)
