"""
DatabaseDockerAgent - AI-Powered PostgreSQL Docker Container Management.

Uses Docker CLI and Claude AI to:
1. Analyze project requirements and detect database needs
2. Create PostgreSQL containers from DATABASE_URL credentials
3. Initialize database schema from Prisma/migrations
4. Intelligently debug and fix connection issues
5. Use AI to understand and resolve complex database problems
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType
from src.tools.claude_code_tool import ClaudeCodeTool


logger = structlog.get_logger(__name__)


@dataclass
class DatabaseConfig:
    """Parsed database configuration."""
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str = "public"

    @classmethod
    def from_url(cls, url: str) -> Optional["DatabaseConfig"]:
        """Parse DATABASE_URL into config."""
        try:
            # postgresql://user:password@localhost:5432/dbname?schema=public
            parsed = urlparse(url)

            # Extract schema from query params
            schema = "public"
            if parsed.query:
                for param in parsed.query.split("&"):
                    if param.startswith("schema="):
                        schema = param.split("=", 1)[1]

            return cls(
                host=parsed.hostname or "localhost",
                port=parsed.port or 5432,
                user=parsed.username or "postgres",
                password=parsed.password or "postgres",
                database=parsed.path.lstrip("/") or "postgres",
                schema=schema,
            )
        except Exception:
            return None


@dataclass
class ProjectDatabaseInfo:
    """Information about project's database requirements."""
    orm_type: Optional[str] = None  # prisma, drizzle, typeorm, etc.
    schema_file: Optional[str] = None
    migrations_dir: Optional[str] = None
    models: list[str] = field(default_factory=list)
    has_seed: bool = False


class DatabaseDockerAgent(AutonomousAgent):
    """
    AI-powered autonomous agent for managing database Docker containers.

    Uses Docker CLI and Claude AI to:
    1. Detect database connection errors
    2. Analyze project to understand database requirements
    3. Create/start database container with correct configuration (PostgreSQL, MySQL, MongoDB, Redis)
    4. Initialize database schema using Prisma/migrations
    5. Intelligently debug connection issues with Claude
    6. Emit DATABASE_READY when fully operational

    Each project gets its own isolated database container named after the project directory.
    Supports multiple database types via DATABASE_IMAGES registry.
    """

    COOLDOWN_SECONDS = 30.0  # Prevent rapid container creation
    CONTAINER_PREFIX = "coding-engine"  # Prefix for all containers
    POSTGRES_IMAGE = "postgres:15"  # Default (kept for backward compat)

    # Universal database image registry
    DATABASE_IMAGES: Dict[str, Dict[str, Any]] = {
        "postgresql": {
            "image": "postgres:15",
            "port": 5432,
            "health_cmd": "pg_isready -U {user}",
            "env_prefix": "POSTGRES",
            "env_vars": lambda cfg: {
                "POSTGRES_USER": cfg.user,
                "POSTGRES_PASSWORD": cfg.password,
                "POSTGRES_DB": cfg.database,
            },
        },
        "mysql": {
            "image": "mysql:8",
            "port": 3306,
            "health_cmd": "mysqladmin ping -h localhost",
            "env_prefix": "MYSQL",
            "env_vars": lambda cfg: {
                "MYSQL_ROOT_PASSWORD": cfg.password,
                "MYSQL_USER": cfg.user,
                "MYSQL_PASSWORD": cfg.password,
                "MYSQL_DATABASE": cfg.database,
            },
        },
        "mongodb": {
            "image": "mongo:7",
            "port": 27017,
            "health_cmd": "mongosh --eval 'db.runCommand({ping:1})'",
            "env_prefix": "MONGO",
            "env_vars": lambda cfg: {
                "MONGO_INITDB_ROOT_USERNAME": cfg.user,
                "MONGO_INITDB_ROOT_PASSWORD": cfg.password,
                "MONGO_INITDB_DATABASE": cfg.database,
            },
        },
        "redis": {
            "image": "redis:7",
            "port": 6379,
            "health_cmd": "redis-cli ping",
            "env_prefix": "REDIS",
            "env_vars": lambda _cfg: {},  # Redis needs no credentials by default
        },
    }

    # Database error patterns
    DATABASE_ERROR_PATTERNS = [
        r"Database connection failed",
        r"ECONNREFUSED.*5432",
        r"Connection refused.*PostgreSQL",
        r"Authentication failed.*database",
        r"P1001.*Can't reach database",  # Prisma error code
        r"P1000.*Authentication failed",  # Prisma auth error
        r"connect ECONNREFUSED.*:5432",
        r"Can't reach database server",
        r"error: password authentication failed",
        r"FATAL:.*does not exist",  # Database doesn't exist
        r"relation .* does not exist",  # Table doesn't exist (needs migration)
        r"provide valid database credentials",  # Prisma credential error
        r"PrismaClientInitializationError",  # Prisma init error
    ]

    def __init__(
        self,
        name: str = "DatabaseDockerAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.code_tool = ClaudeCodeTool(working_dir=working_dir)
        self._start_attempts: int = 0
        self._max_start_attempts: int = 3
        self._schema_applied: bool = False
        self.logger = logger.bind(agent=name)

        # Generate project-specific container name
        self._container_name = self._generate_container_name()

        # Log initialization
        self.logger.info(
            "database_docker_agent_initialized",
            working_dir=working_dir,
            container_name=self._container_name,
            subscribed_events=[e.value for e in self.subscribed_events],
        )

    def _generate_container_name(self) -> str:
        """
        Generate a project-specific container name from the working directory.

        Examples:
            - /output_microservices -> coding-engine-output_microservices-postgres
            - /my-cool-app -> coding-engine-my-cool-app-postgres
        """
        import re

        # Get the last directory component (project name)
        project_dir = Path(self.working_dir).resolve()
        project_name = project_dir.name

        # Sanitize for Docker container naming (lowercase, alphanumeric + dash)
        # Docker container names must match: [a-zA-Z0-9][a-zA-Z0-9_.-]*
        sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '-', project_name.lower())
        sanitized = re.sub(r'-+', '-', sanitized)  # Collapse multiple dashes
        sanitized = sanitized.strip('-')

        # Ensure it doesn't start with a digit (add prefix if so)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"p{sanitized}"

        # Fallback if empty
        if not sanitized:
            sanitized = "default"

        container_name = f"{self.CONTAINER_PREFIX}-{sanitized}-postgres"

        return container_name

    def _find_existing_postgres_container(self) -> Optional[str]:
        """
        Find any running postgres container for this project.

        Returns container name if found, None otherwise.
        """
        try:
            raw = self.tool_registry.call_tool("docker.list_containers")
            data = json.loads(raw) if isinstance(raw, str) else raw

            if "error" in data:
                self.logger.debug("find_postgres_failed", error=data["error"])
                return None

            # Parse containers list - each line is a JSON object
            containers_list = data if isinstance(data, list) else []
            if isinstance(data, dict) and "containers" in data:
                containers_list = data["containers"]

            project_name = Path(self.working_dir).resolve().name.lower()

            for container in containers_list:
                if isinstance(container, dict):
                    name = container.get("Names", container.get("Name", ""))
                    image = container.get("Image", "")
                elif isinstance(container, str):
                    # Might be raw string from docker ps
                    name = container
                    image = ""
                else:
                    continue

                # Match postgres containers with our prefix and project name
                if ("postgres" in image.lower() or "postgres" in name.lower()):
                    if name.startswith(self.CONTAINER_PREFIX) and project_name in name.lower():
                        self.logger.info("found_existing_postgres", container=name)
                        return name

        except Exception as e:
            self.logger.debug("find_postgres_failed", error=str(e))

        return None

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.VALIDATION_ERROR,      # Reactive: on DB errors
            EventType.PROJECT_SCAFFOLDED,    # Proactive: early DB startup
        ]

    def _handle_event(self, event: Event) -> None:
        """Override to add diagnostic logging for event reception."""
        # Log every event we receive (before filtering)
        self.logger.info(
            "📨 DB_AGENT_EVENT_RECEIVED",
            event_type=event.type.value,
            source=event.source,
            has_error=bool(event.error_message),
            queue_size=self._event_queue.qsize(),
        )
        # Call parent implementation
        super()._handle_event(event)
        # Log after adding to queue
        self.logger.info(
            "📥 DB_AGENT_EVENT_QUEUED",
            event_type=event.type.value,
            queue_size_after=self._event_queue.qsize(),
        )

    async def should_act(self, events: list[Event]) -> bool:
        """Check if any event is a database error or proactive trigger."""
        self.logger.info(
            "🔍 DB_AGENT_CHECKING_EVENTS",
            event_count=len(events),
            event_types=[e.type.value for e in events[:5]],
        )

        for event in events:
            # PROACTIVE: Check for PROJECT_SCAFFOLDED to start DB early
            if event.type == EventType.PROJECT_SCAFFOLDED:
                if self._detect_database_requirement():
                    self.logger.info(
                        "🗄️ DB_PROACTIVE_TRIGGER",
                        reason="project_scaffolded",
                        source=event.source,
                    )
                    return True
                continue

            # REACTIVE: Check for database errors
            if event.type != EventType.VALIDATION_ERROR:
                continue

            error_data = event.data or {}
            error_type = error_data.get("error_type")
            raw_error = error_data.get("raw_error", "")
            error_message = event.error_message or ""

            self.logger.info(
                "🔎 DB_AGENT_CHECKING_ERROR",
                error_type=error_type,
                source=event.source,
                has_raw_error=bool(raw_error),
                raw_error_preview=raw_error[:100] if raw_error else "",
            )

            # Check for database-specific error types
            if error_type == "database_error":
                self.logger.info("database_error_type_matched", error_type=error_type)
                return True

            # Check patterns in error message
            combined_error = f"{error_message} {raw_error}"
            for pattern in self.DATABASE_ERROR_PATTERNS:
                if re.search(pattern, combined_error, re.IGNORECASE):
                    self.logger.info("✅ DB_PATTERN_MATCHED", pattern=pattern)
                    return True

        self.logger.info("❌ DB_AGENT_NO_MATCH", event_count=len(events))
        return False

    def _find_database_error(self, events: list[Event]) -> Optional[Event]:
        """Find the first database-related error event."""
        for event in events:
            if event.type != EventType.VALIDATION_ERROR:
                continue

            error_data = event.data or {}
            error_type = error_data.get("error_type")
            raw_error = error_data.get("raw_error", "")
            error_message = event.error_message or ""

            if error_type == "database_error":
                return event

            combined_error = f"{error_message} {raw_error}"
            for pattern in self.DATABASE_ERROR_PATTERNS:
                if re.search(pattern, combined_error, re.IGNORECASE):
                    return event

        return None

    async def act(self, events: list[Event]) -> None:
        """Handle database startup - proactively or reactively."""
        # Check for PROACTIVE triggers first (PROJECT_SCAFFOLDED)
        proactive_events = [e for e in events if e.type == EventType.PROJECT_SCAFFOLDED]
        if proactive_events:
            self.logger.info("🗄️ PROACTIVE_DB_STARTUP", source=proactive_events[0].source)

            # Read config or create default
            config = self._read_database_config()
            if not config:
                # Create default .env with DATABASE_URL
                self.logger.info("creating_default_database_config")
                await self._ai_create_database_config(proactive_events[0])
                config = self._read_database_config()

            if config:
                success = await self._ensure_database_running(config)
                if success:
                    # Publish DATABASE_READY event
                    project_info = await self._analyze_project_database()
                    await self.event_bus.publish(Event(
                        type=EventType.DEPENDENCY_UPDATED,
                        source=self.name,
                        data={
                            "action": "database_ready",
                            "module": "postgresql",
                            "container": self._container_name,
                            "port": config.port,
                            "orm": project_info.orm_type,
                            "proactive": True,
                        },
                    ))
            return

        # REACTIVE: Find the database error event from the batch
        event = self._find_database_error(events)
        if not event:
            self.logger.debug("no_database_error_in_batch")
            return

        if self._start_attempts >= self._max_start_attempts:
            self.logger.warning(
                "max_database_start_attempts_reached",
                attempts=self._start_attempts,
            )
            # Use AI to analyze why we keep failing
            await self._ai_analyze_repeated_failures(event)
            return

        self._start_attempts += 1
        self.logger.info(
            "database_error_detected_starting_postgres",
            attempt=self._start_attempts,
        )

        # 1. Parse DATABASE_URL from .env
        config = self._read_database_config()
        if not config:
            self.logger.error("database_url_not_found_in_env")
            # Use AI to create appropriate .env configuration
            await self._ai_create_database_config(event)
            return

        self.logger.info(
            "database_config_parsed",
            host=config.host,
            port=config.port,
            user=config.user,
            database=config.database,
        )

        # 2. Analyze project database requirements
        project_info = await self._analyze_project_database()

        # 3. Check if container already exists
        container_status = self._get_container_status()

        if container_status == "running":
            # Container running but connection failed
            # Check if it's a schema/migration issue
            error_data = event.data or {}
            raw_error = error_data.get("raw_error", "")

            if "does not exist" in raw_error.lower():
                # Schema issue - run migrations
                self.logger.info("database_schema_missing_running_migrations")
                await self._run_database_migrations(config, project_info)
            else:
                # Other connection issue - debug with AI
                self.logger.info("postgres_running_but_connection_failed")
                await self._ai_debug_connection(event, config, project_info)
            return

        if container_status == "exited":
            # Container exists but stopped - start it
            self.logger.info("starting_existing_postgres_container")
            success = await self._start_container()
        else:
            # No container - use AI to build optimal configuration
            self.logger.info("building_new_postgres_container_with_ai")
            success = await self._ai_build_database(config, project_info)

        if success:
            # Wait for PostgreSQL to be ready
            ready = await self._wait_for_postgres_ready(config)
            if ready:
                self.logger.info("postgres_ready")

                # Run initial migrations if needed
                if project_info.orm_type and not self._schema_applied:
                    await self._run_database_migrations(config, project_info)
                    self._schema_applied = True

                self._start_attempts = 0  # Reset on success

                # Publish DATABASE_READY event (triggers server restart)
                await self.event_bus.publish(Event(
                    type=EventType.DEPENDENCY_UPDATED,
                    source=self.name,
                    data={
                        "action": "database_ready",
                        "module": "postgresql",
                        "container": self._container_name,
                        "port": config.port,
                        "orm": project_info.orm_type,
                    },
                ))
            else:
                # Still failing - debug with AI
                await self._ai_debug_connection(event, config, project_info)
        else:
            await self._ai_debug_connection(event, config, project_info)

    async def _analyze_project_database(self) -> ProjectDatabaseInfo:
        """Analyze project to determine database requirements."""
        info = ProjectDatabaseInfo()
        working_dir = Path(self.working_dir)

        # Check for Prisma
        prisma_schema = working_dir / "prisma" / "schema.prisma"
        if prisma_schema.exists():
            info.orm_type = "prisma"
            info.schema_file = str(prisma_schema)
            info.migrations_dir = str(working_dir / "prisma" / "migrations")

            # Parse models from schema
            try:
                content = prisma_schema.read_text()
                models = re.findall(r'model\s+(\w+)\s*\{', content)
                info.models = models
            except Exception:
                pass

        # Check for Drizzle
        drizzle_config = working_dir / "drizzle.config.ts"
        if drizzle_config.exists():
            info.orm_type = "drizzle"
            info.migrations_dir = str(working_dir / "drizzle")

        # Check for TypeORM
        typeorm_config = working_dir / "ormconfig.json"
        if typeorm_config.exists():
            info.orm_type = "typeorm"

        # Check for seed file
        seed_files = [
            working_dir / "prisma" / "seed.ts",
            working_dir / "prisma" / "seed.js",
            working_dir / "src" / "db" / "seed.ts",
        ]
        info.has_seed = any(f.exists() for f in seed_files)

        self.logger.info(
            "project_database_analysis",
            orm=info.orm_type,
            models=len(info.models),
            has_seed=info.has_seed,
        )

        return info

    def _detect_database_requirement(self) -> bool:
        """
        Proactively check if project needs a database.

        Returns True if:
        - Prisma schema exists
        - requirements.txt contains sqlalchemy/psycopg2/asyncpg
        - .env or .env.example contains DATABASE_URL
        """
        working_dir = Path(self.working_dir)

        # Check for Prisma
        if (working_dir / "prisma" / "schema.prisma").exists():
            self.logger.info("db_requirement_detected", reason="prisma_schema")
            return True

        # Check for SQLAlchemy in requirements.txt
        requirements = working_dir / "requirements.txt"
        if requirements.exists():
            try:
                content = requirements.read_text().lower()
                db_packages = ["sqlalchemy", "psycopg2", "asyncpg", "databases", "tortoise-orm"]
                if any(pkg in content for pkg in db_packages):
                    self.logger.info("db_requirement_detected", reason="python_db_package")
                    return True
            except Exception:
                pass

        # Check for DATABASE_URL in .env or .env.example
        for env_file in [".env", ".env.example"]:
            env_path = working_dir / env_file
            if env_path.exists():
                try:
                    if "DATABASE_URL" in env_path.read_text():
                        self.logger.info("db_requirement_detected", reason=f"{env_file}_database_url")
                        return True
                except Exception:
                    pass

        # Check for package.json with Prisma or database deps
        package_json = working_dir / "package.json"
        if package_json.exists():
            try:
                import json
                pkg = json.loads(package_json.read_text())
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                db_deps = ["prisma", "@prisma/client", "typeorm", "sequelize", "knex", "drizzle-orm"]
                if any(dep in all_deps for dep in db_deps):
                    self.logger.info("db_requirement_detected", reason="node_db_package")
                    return True
            except Exception:
                pass

        return False

    def _detect_db_type(self) -> str:
        """Detect database type from project files (universal).

        Inspects Prisma schema, requirements.txt, package.json to determine
        which database engine the project uses.

        Returns:
            Database type key matching DATABASE_IMAGES registry.
        """
        working_dir = Path(self.working_dir)

        # Check Prisma schema for provider
        schema = working_dir / "prisma" / "schema.prisma"
        if schema.exists():
            try:
                content = schema.read_text()
                if "mysql" in content.lower():
                    return "mysql"
                if "mongodb" in content.lower():
                    return "mongodb"
                if "sqlite" in content.lower():
                    return "sqlite"
                return "postgresql"
            except Exception:
                return "postgresql"

        # Check Python requirements
        reqs = working_dir / "requirements.txt"
        if reqs.exists():
            try:
                content = reqs.read_text().lower()
                if "pymongo" in content or "motor" in content:
                    return "mongodb"
                if "mysql" in content or "pymysql" in content or "aiomysql" in content:
                    return "mysql"
                if "redis" in content or "aioredis" in content:
                    return "redis"
                if "psycopg" in content or "asyncpg" in content or "sqlalchemy" in content:
                    return "postgresql"
            except Exception:
                pass

        # Check package.json
        pkg = working_dir / "package.json"
        if pkg.exists():
            try:
                content = pkg.read_text().lower()
                if "mongoose" in content or "mongodb" in content:
                    return "mongodb"
                if "mysql2" in content or "mysql" in content:
                    return "mysql"
                if "ioredis" in content or "redis" in content:
                    return "redis"
                return "postgresql"
            except Exception:
                pass

        return "postgresql"  # Safe default

    def _get_db_image_config(self) -> Dict[str, Any]:
        """Get the Docker image config for the detected database type."""
        db_type = self._detect_db_type()
        return self.DATABASE_IMAGES.get(db_type, self.DATABASE_IMAGES["postgresql"])

    async def _ensure_database_running(self, config: DatabaseConfig) -> bool:
        """Ensure database container is running, create if needed."""
        container_status = self._get_container_status()

        if container_status == "running":
            self.logger.info("db_already_running", container=self._container_name)
            return True

        if container_status == "exited":
            self.logger.info("db_starting_existing", container=self._container_name)
            return await self._start_container()

        # No container exists - create new one
        self.logger.info("db_creating_new", container=self._container_name)
        success = await self._create_container(config)

        if success:
            # Wait for PostgreSQL to be ready
            ready = await self._wait_for_postgres_ready(config)
            if ready:
                self.logger.info("db_proactive_startup_complete", port=config.port)

                # Run migrations if ORM detected
                project_info = await self._analyze_project_database()
                if project_info.orm_type:
                    await self._run_database_migrations(config, project_info)

                return True

        return False

    async def _ai_build_database(
        self,
        config: DatabaseConfig,
        project_info: ProjectDatabaseInfo,
    ) -> bool:
        """Use AI to build optimal database configuration."""
        # Read schema if available
        schema_content = ""
        if project_info.schema_file:
            try:
                schema_content = Path(project_info.schema_file).read_text()
            except Exception:
                pass

        prompt = f"""Build a PostgreSQL Docker container for this project.

DATABASE CONFIGURATION:
- Host: {config.host}
- Port: {config.port}
- User: {config.user}
- Password: {config.password}
- Database: {config.database}
- Schema: {config.schema}

PROJECT ORM: {project_info.orm_type or 'Unknown'}
MODELS: {', '.join(project_info.models) if project_info.models else 'None detected'}

{f'SCHEMA FILE ({project_info.schema_file}):' if schema_content else ''}
{schema_content[:2000] if schema_content else ''}

Create and start a PostgreSQL Docker container with these exact commands:

1. First, remove any existing container:
   docker rm -f {self._container_name}

2. Create new container:
   docker run -d --name {self._container_name} \\
     -e POSTGRES_USER={config.user} \\
     -e POSTGRES_PASSWORD={config.password} \\
     -e POSTGRES_DB={config.database} \\
     -p {config.port}:5432 \\
     --health-cmd "pg_isready -U {config.user}" \\
     --health-interval 2s \\
     --health-timeout 5s \\
     --health-retries 10 \\
     {self.POSTGRES_IMAGE}

Execute these commands now.
"""

        self.logger.info("ai_building_database")
        result = await self.code_tool.execute(prompt, "", "infrastructure")

        if result.success:
            # Verify container was created
            await asyncio.sleep(2)  # Give Docker time to start
            status = self._get_container_status()
            if status == "running":
                self.logger.info("ai_database_build_success")
                return True

        # Fallback to direct creation
        return await self._create_container(config)

    async def _run_database_migrations(
        self,
        config: DatabaseConfig,
        project_info: ProjectDatabaseInfo,
    ) -> bool:
        """Run database migrations using AI to handle errors."""
        if not project_info.orm_type:
            return False

        prompt = f"""Run database migrations for this {project_info.orm_type} project.

DATABASE: postgresql://{config.user}:***@{config.host}:{config.port}/{config.database}
ORM: {project_info.orm_type}
WORKING DIRECTORY: {self.working_dir}

For Prisma, run:
1. npx prisma generate  (generate client)
2. npx prisma db push   (push schema to database, use --accept-data-loss if needed)

For Drizzle, run:
1. npx drizzle-kit push:pg

Execute the appropriate migration commands for {project_info.orm_type}.
If there are errors, analyze and fix them.
"""

        self.logger.info("running_database_migrations", orm=project_info.orm_type)
        result = await self.code_tool.execute(prompt, "", "database")

        if result.success:
            self.logger.info("migrations_complete")
            return True
        else:
            self.logger.warning("migrations_failed")
            return False

    async def _ai_debug_connection(
        self,
        event: Event,
        config: DatabaseConfig,
        project_info: ProjectDatabaseInfo,
    ) -> None:
        """Use Claude AI to analyze and fix database connection issues."""
        error_data = event.data or {}
        raw_error = error_data.get("raw_error", event.error_message or "")

        # Get container logs
        logs = self._get_container_logs()

        # Get Docker network info
        network_info = self._get_docker_network_info()

        # Read .env for context
        env_content = self._read_env_file()

        prompt = f"""Debug this database connection issue using AI analysis:

ERROR MESSAGE:
{raw_error}

DATABASE CONFIGURATION:
- Host: {config.host}
- Port: {config.port}
- User: {config.user}
- Database: {config.database}
- Schema: {config.schema}

PROJECT INFO:
- ORM: {project_info.orm_type or 'Not detected'}
- Models: {', '.join(project_info.models) if project_info.models else 'None'}
- Has migrations: {bool(project_info.migrations_dir)}

POSTGRESQL CONTAINER LOGS:
{logs}

DOCKER NETWORK INFO:
{network_info}

.ENV FILE:
{env_content}

CONTAINER STATUS: {self._get_container_status() or "Not running"}

Analyze the issue step by step:
1. Is the PostgreSQL container running and healthy?
2. Are the credentials correct?
3. Does the database exist?
4. Is there a port conflict?
5. Is there a network issue?

Then execute commands to fix the issue:
- If container not running: docker start {self._container_name}
- If credentials wrong: Update .env file
- If database missing: docker exec {self._container_name} createdb -U {config.user} {config.database}
- If schema missing: Run migrations (npx prisma db push for Prisma)

Execute the appropriate fix commands now.
"""

        self.logger.info("ai_debugging_database_connection")
        result = await self.code_tool.execute(prompt, "", "debugging")

        if result.success:
            self.logger.info(
                "ai_debug_complete",
                output_preview=result.output[:300] if result.output else "",
            )
        else:
            self.logger.warning("ai_debug_failed")

    async def _ai_create_database_config(self, event: Event) -> None:
        """Use AI to create appropriate database configuration."""
        # Check if we can detect ORM from package.json
        package_json = Path(self.working_dir) / "package.json"
        pkg_content = ""
        if package_json.exists():
            try:
                pkg_content = package_json.read_text()
            except Exception:
                pass

        prompt = f"""Create a DATABASE_URL configuration for this project.

The project's .env file is missing DATABASE_URL.

PACKAGE.JSON:
{pkg_content[:1500] if pkg_content else 'Not found'}

Create a .env file or update the existing one with:
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/app_db?schema=public"

Also create the PostgreSQL Docker container:
docker run -d --name {self._container_name} \\
  -e POSTGRES_USER=postgres \\
  -e POSTGRES_PASSWORD=postgres \\
  -e POSTGRES_DB=app_db \\
  -p 5432:5432 \\
  {self.POSTGRES_IMAGE}

Execute these commands to set up the database.
"""

        self.logger.info("ai_creating_database_config")
        result = await self.code_tool.execute(prompt, "", "infrastructure")

        if result.success:
            self.logger.info("ai_config_created")

    async def _ai_analyze_repeated_failures(self, event: Event) -> None:
        """Use AI to analyze why database setup keeps failing."""
        error_data = event.data or {}
        raw_error = error_data.get("raw_error", event.error_message or "")

        prompt = f"""The database setup has failed {self._max_start_attempts} times.
Perform a comprehensive analysis of why this keeps happening.

LAST ERROR:
{raw_error}

CONTAINER STATUS: {self._get_container_status()}
CONTAINER LOGS:
{self._get_container_logs()}

DOCKER INFO:
{self._get_docker_info()}

Check for:
1. Docker daemon running issues
2. Port conflicts with other services
3. Disk space issues
4. Permission problems
5. Network configuration issues
6. Resource constraints

Provide a detailed analysis and attempt alternative solutions:
- Try a different port if 5432 is blocked
- Check if another PostgreSQL instance is running
- Verify Docker has sufficient resources
"""

        self.logger.info("ai_analyzing_repeated_failures")
        await self.code_tool.execute(prompt, "", "debugging")

    def _read_database_config(self) -> Optional[DatabaseConfig]:
        """Read DATABASE_URL from project's .env file."""
        env_file = Path(self.working_dir) / ".env"
        if not env_file.exists():
            self.logger.warning("env_file_not_found", path=str(env_file))
            return None

        try:
            content = env_file.read_text()
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    url = line.split('=', 1)[1].strip().strip('"\'')
                    self.logger.debug("database_url_found", url=url[:50] + "...")
                    return DatabaseConfig.from_url(url)
        except Exception as e:
            self.logger.warning("env_parse_error", error=str(e))

        return None

    def _read_env_file(self) -> str:
        """Read .env file content."""
        env_file = Path(self.working_dir) / ".env"
        if env_file.exists():
            try:
                return env_file.read_text()
            except Exception:
                return "(Could not read .env file)"
        return "(No .env file found)"

    def _get_container_status(self) -> Optional[str]:
        """Check if PostgreSQL container exists and its status."""
        try:
            raw = self.tool_registry.call_tool(
                "docker.container_inspect", container=self._container_name
            )
            data = json.loads(raw) if isinstance(raw, str) else raw

            if "error" not in data:
                state = data.get("State", {})
                status = state.get("Status", "") if isinstance(state, dict) else str(state)
                if status:
                    self.logger.debug("container_status", status=status)
                    return status

            # Container not found with expected name - try to find existing one
            existing = self._find_existing_postgres_container()
            if existing:
                self._container_name = existing
                self.logger.info("using_existing_container", container=existing)

                raw2 = self.tool_registry.call_tool(
                    "docker.container_inspect", container=existing
                )
                data2 = json.loads(raw2) if isinstance(raw2, str) else raw2
                if "error" not in data2:
                    state2 = data2.get("State", {})
                    return state2.get("Status", "") if isinstance(state2, dict) else str(state2)

            return None
        except Exception as e:
            self.logger.debug("container_inspect_failed", error=str(e))
            return None

    def _get_container_logs(self) -> str:
        """Get PostgreSQL container logs."""
        try:
            raw = self.tool_registry.call_tool(
                "docker.container_logs", container=self._container_name
            )
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data.get("logs", str(data)) if isinstance(data, dict) else str(data)
        except Exception:
            return "(Could not retrieve container logs)"

    def _get_docker_network_info(self) -> str:
        """Get Docker network information."""
        try:
            raw = self.tool_registry.call_tool(
                "docker.container_inspect", container=self._container_name
            )
            data = json.loads(raw) if isinstance(raw, str) else raw
            if "error" not in data:
                networks = data.get("NetworkSettings", {}).get("Networks", {})
                for net_name, net_info in networks.items():
                    ip = net_info.get("IPAddress", "")
                    if ip:
                        return f"Container IP: {ip}"
            return ""
        except Exception:
            return ""

    def _get_docker_info(self) -> str:
        """Get general Docker system info."""
        try:
            raw = self.tool_registry.call_tool("docker.docker_info")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if "error" not in data:
                return f"Docker: {data.get('ServerVersion', 'unknown')}, Containers: {data.get('Containers', 0)}"
            return "(Could not get Docker info)"
        except Exception:
            return "(Docker not accessible)"

    async def _create_container(self, config: DatabaseConfig) -> bool:
        """Create a new PostgreSQL container."""
        try:
            # First, remove any existing container with the same name
            self.tool_registry.call_tool(
                "docker.remove_container",
                container_id=self._container_name,
                force=True,
            )

            # Run new postgres container
            env_vars = {
                "POSTGRES_USER": config.user,
                "POSTGRES_PASSWORD": config.password,
                "POSTGRES_DB": config.database,
            }
            ports = {f"{config.port}": "5432"}

            self.logger.info("running_docker_command", image=self.POSTGRES_IMAGE, port=config.port)
            raw = self.tool_registry.call_tool(
                "docker.run_container",
                image=self.POSTGRES_IMAGE,
                name=self._container_name,
                ports=ports,
                env=env_vars,
                detach=True,
            )
            data = json.loads(raw) if isinstance(raw, str) else raw

            if "error" not in data:
                container_id = data.get("container_id", data.get("id", "unknown"))[:12]
                self.logger.info(
                    "postgres_container_created",
                    container_id=container_id,
                    port=config.port,
                )
                return True
            else:
                self.logger.error(
                    "postgres_container_create_failed",
                    stderr=data.get("error", "")[:500],
                )
                return False

        except Exception as e:
            self.logger.error("docker_run_error", error=str(e))
            return False

    async def _start_container(self) -> bool:
        """Start existing PostgreSQL container."""
        try:
            raw = self.tool_registry.call_tool(
                "docker.start_container", container=self._container_name
            )
            data = json.loads(raw) if isinstance(raw, str) else raw

            if "error" not in data:
                self.logger.info("postgres_container_started")
                return True
            else:
                self.logger.error("container_start_failed", error=data.get("error", ""))
                return False
        except Exception as e:
            self.logger.error("container_start_exception", error=str(e))
            return False

    async def _wait_for_postgres_ready(
        self,
        config: DatabaseConfig,
        timeout: float = 30.0,
    ) -> bool:
        """Wait for PostgreSQL to accept connections."""
        import socket

        self.logger.info("waiting_for_postgres", host=config.host, port=config.port, timeout=timeout)
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1.0)
                    s.connect((config.host, config.port))
                    self.logger.info("postgres_port_reachable")
                    return True
            except (socket.error, socket.timeout):
                await asyncio.sleep(1.0)

        self.logger.warning("postgres_ready_timeout", timeout=timeout)
        return False

    # =========================================================================
    # LLM-Enhanced Database Error Diagnosis
    # =========================================================================

    async def diagnose_database_error_with_llm(
        self,
        error_output: str,
        schema_content: Optional[str] = None,
        env_content: Optional[str] = None,
        container_logs: Optional[str] = None,
    ) -> dict:
        """
        Use LLM to diagnose database errors with semantic understanding.

        This provides context-aware error analysis beyond regex patterns:
        1. Understands the actual root cause (not just pattern matching)
        2. Differentiates between connection, auth, schema, and data errors
        3. Provides specific actionable fixes
        4. Considers the full context (schema, env, logs)

        Args:
            error_output: The raw error message/output
            schema_content: Optional Prisma/Drizzle schema content
            env_content: Optional .env file content (sanitized)
            container_logs: Optional Docker container logs

        Returns:
            Dict with diagnosis, root_cause, fix_type, fix_commands, confidence
        """
        # Truncate inputs to avoid token issues
        error_truncated = error_output[:2000] if error_output else ""
        schema_truncated = schema_content[:1500] if schema_content else ""
        env_sanitized = self._sanitize_env_for_llm(env_content) if env_content else ""
        logs_truncated = container_logs[-1000:] if container_logs else ""

        prompt = f"""Diagnose this PostgreSQL/database error with full context:

ERROR OUTPUT:
{error_truncated}

PRISMA/DATABASE SCHEMA:
{schema_truncated if schema_truncated else "N/A"}

ENVIRONMENT CONFIG (sanitized):
{env_sanitized if env_sanitized else "N/A"}

CONTAINER LOGS (last 1000 chars):
{logs_truncated if logs_truncated else "N/A"}

## Analyze the error:

1. **Error Category** - What type of error is this?
   - CONNECTION: Can't reach database server (network, port, host)
   - AUTHENTICATION: Wrong credentials (user, password)
   - DATABASE_MISSING: Database doesn't exist
   - SCHEMA_MISMATCH: Table/column doesn't exist (needs migration)
   - DATA_INTEGRITY: Foreign key, unique constraint violations
   - PERMISSION: User lacks required permissions
   - CONFIGURATION: Misconfigured DATABASE_URL or settings
   - RESOURCE: Out of connections, memory, disk space

2. **Root Cause** - What's actually wrong? Be specific.

3. **Fix Type** - What action is needed?
   - START_CONTAINER: Docker container not running
   - CREATE_DATABASE: Database doesn't exist
   - RUN_MIGRATIONS: Schema out of sync
   - FIX_CREDENTIALS: Auth credentials wrong
   - FIX_URL: DATABASE_URL malformed
   - FIX_SCHEMA: Schema definition error
   - SEED_DATA: Missing required data
   - INCREASE_RESOURCES: Need more connections/memory

4. **Fix Commands** - Specific commands to run

Return ONLY valid JSON:
{{"category": "string", "root_cause": "string", "fix_type": "string", "fix_commands": ["string"], "schema_change_needed": false, "migration_command": "string|null", "confidence": 0.9, "severity": "critical|high|medium|low"}}"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context="Database error diagnosis",
                agent_type="database_diagnostician",
            )

            if result.success and result.output:
                # Parse JSON response
                json_match = re.search(
                    r'\{[^{}]*"category"[^{}]*\}',
                    result.output,
                    re.DOTALL
                )

                if json_match:
                    diagnosis = json.loads(json_match.group())
                    self.logger.info(
                        "llm_database_diagnosis_complete",
                        category=diagnosis.get("category"),
                        fix_type=diagnosis.get("fix_type"),
                        confidence=diagnosis.get("confidence", 0),
                    )
                    return diagnosis

            # Fallback if parsing fails
            self.logger.warning("llm_diagnosis_parse_failed")
            return self._fallback_error_diagnosis(error_output)

        except Exception as e:
            self.logger.warning("llm_database_diagnosis_failed", error=str(e))
            return self._fallback_error_diagnosis(error_output)

    def _fallback_error_diagnosis(self, error_output: str) -> dict:
        """
        Rule-based error diagnosis as fallback when LLM is unavailable.

        Maps known error patterns to categories and fix types.
        """
        error_lower = error_output.lower()

        # Connection errors
        if any(p in error_lower for p in ["econnrefused", "connection refused", "can't reach"]):
            return {
                "category": "CONNECTION",
                "root_cause": "Database server not reachable - container may not be running",
                "fix_type": "START_CONTAINER",
                "fix_commands": [f"docker start {self._container_name}"],
                "schema_change_needed": False,
                "migration_command": None,
                "confidence": 0.7,
                "severity": "critical",
            }

        # Authentication errors
        if any(p in error_lower for p in ["authentication failed", "password", "p1000"]):
            return {
                "category": "AUTHENTICATION",
                "root_cause": "Database credentials are incorrect",
                "fix_type": "FIX_CREDENTIALS",
                "fix_commands": ["Check DATABASE_URL in .env", "Verify POSTGRES_PASSWORD in container"],
                "schema_change_needed": False,
                "migration_command": None,
                "confidence": 0.7,
                "severity": "critical",
            }

        # Schema/migration errors
        if any(p in error_lower for p in ["does not exist", "relation", "column", "table"]):
            return {
                "category": "SCHEMA_MISMATCH",
                "root_cause": "Database schema doesn't match application - migration needed",
                "fix_type": "RUN_MIGRATIONS",
                "fix_commands": ["npx prisma db push --accept-data-loss", "npx prisma generate"],
                "schema_change_needed": True,
                "migration_command": "npx prisma db push --accept-data-loss",
                "confidence": 0.8,
                "severity": "high",
            }

        # Database missing
        if "database" in error_lower and ("not exist" in error_lower or "fatal" in error_lower):
            return {
                "category": "DATABASE_MISSING",
                "root_cause": "The specified database doesn't exist",
                "fix_type": "CREATE_DATABASE",
                "fix_commands": [f"docker exec {self._container_name} createdb -U postgres app_db"],
                "schema_change_needed": False,
                "migration_command": None,
                "confidence": 0.7,
                "severity": "high",
            }

        # Prisma initialization
        if "prismaclientinitializationerror" in error_lower:
            return {
                "category": "CONFIGURATION",
                "root_cause": "Prisma client not generated or DATABASE_URL invalid",
                "fix_type": "FIX_URL",
                "fix_commands": ["npx prisma generate", "Check DATABASE_URL format in .env"],
                "schema_change_needed": False,
                "migration_command": "npx prisma generate",
                "confidence": 0.7,
                "severity": "high",
            }

        # Default unknown error
        return {
            "category": "UNKNOWN",
            "root_cause": "Could not determine specific cause from error message",
            "fix_type": "START_CONTAINER",
            "fix_commands": [f"docker start {self._container_name}", "Check Docker logs"],
            "schema_change_needed": False,
            "migration_command": None,
            "confidence": 0.3,
            "severity": "medium",
        }

    def _sanitize_env_for_llm(self, env_content: str) -> str:
        """
        Sanitize .env content before sending to LLM.

        Masks sensitive values while preserving structure for diagnosis.
        """
        sanitized_lines = []
        for line in env_content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()

                # Mask passwords and secrets
                sensitive_keys = ["PASSWORD", "SECRET", "KEY", "TOKEN", "API_KEY"]
                if any(s in key.upper() for s in sensitive_keys):
                    sanitized_lines.append(f"{key}=***MASKED***")
                elif key == "DATABASE_URL":
                    # Mask password in DATABASE_URL but keep structure
                    masked_url = re.sub(r':([^:@]+)@', ':***@', value)
                    sanitized_lines.append(f"{key}={masked_url}")
                else:
                    sanitized_lines.append(line)

        return "\n".join(sanitized_lines)

    async def diagnose_and_fix(self, event: Event) -> bool:
        """
        High-level method: diagnose error with LLM and apply fix.

        Args:
            event: The error event to diagnose

        Returns:
            True if fix was applied successfully
        """
        error_data = event.data or {}
        raw_error = error_data.get("raw_error", event.error_message or "")

        # Gather context
        schema_content = None
        project_info = await self._analyze_project_database()
        if project_info.schema_file:
            try:
                schema_content = Path(project_info.schema_file).read_text()
            except Exception:
                pass

        env_content = self._read_env_file()
        container_logs = self._get_container_logs()

        # Get LLM diagnosis
        diagnosis = await self.diagnose_database_error_with_llm(
            error_output=raw_error,
            schema_content=schema_content,
            env_content=env_content,
            container_logs=container_logs,
        )

        self.logger.info(
            "database_diagnosis_result",
            category=diagnosis.get("category"),
            fix_type=diagnosis.get("fix_type"),
            confidence=diagnosis.get("confidence", 0),
        )

        # Apply fix based on diagnosis
        fix_type = diagnosis.get("fix_type", "")
        config = self._read_database_config()

        if fix_type == "START_CONTAINER":
            return await self._start_container()

        elif fix_type == "CREATE_DATABASE" and config:
            # Create database via docker exec
            try:
                raw = self.tool_registry.call_tool(
                    "docker.exec_container",
                    container=self._container_name,
                    command=f"createdb -U {config.user} {config.database}",
                )
                data = json.loads(raw) if isinstance(raw, str) else raw
                return "error" not in data
            except Exception as e:
                self.logger.warning("create_database_failed", error=str(e))
                return False

        elif fix_type == "RUN_MIGRATIONS" and config:
            return await self._run_database_migrations(config, project_info)

        elif fix_type in ("FIX_CREDENTIALS", "FIX_URL"):
            # Use AI to fix configuration
            await self._ai_create_database_config(event)
            return True

        # Default: try starting container
        return await self._start_container()

    def is_database_error(self, error_message: str) -> bool:
        """
        Quick check if an error message is database-related.

        Uses regex patterns for fast filtering before LLM analysis.

        Args:
            error_message: Error string to check

        Returns:
            True if this looks like a database error
        """
        for pattern in self.DATABASE_ERROR_PATTERNS:
            if re.search(pattern, error_message, re.IGNORECASE):
                return True
        return False

    async def is_database_error_with_llm(self, error_message: str) -> dict:
        """
        Use LLM to determine if an ambiguous error is database-related.

        For errors that don't match regex patterns but might still be DB issues.

        Args:
            error_message: Error string to analyze

        Returns:
            Dict with is_database_error, confidence, reason
        """
        # First try fast regex check
        if self.is_database_error(error_message):
            return {
                "is_database_error": True,
                "confidence": 0.9,
                "reason": "Matched known database error pattern",
                "detection_method": "regex",
            }

        # For ambiguous errors, use LLM
        prompt = f"""Is this error message related to a database issue?

ERROR:
{error_message[:1000]}

Database-related errors include:
- Connection failures to PostgreSQL/MySQL/etc
- Authentication/credential errors
- Missing tables, columns, or schemas
- Migration failures
- ORM errors (Prisma, TypeORM, Sequelize)
- Query errors

Return ONLY valid JSON:
{{"is_database_error": true, "confidence": 0.8, "reason": "explanation"}}"""

        try:
            result = await self.code_tool.execute(
                prompt=prompt,
                context="Database error classification",
                agent_type="error_classifier",
            )

            if result.success and result.output:
                json_match = re.search(r'\{[^{}]*"is_database_error"[^{}]*\}', result.output)
                if json_match:
                    parsed = json.loads(json_match.group())
                    parsed["detection_method"] = "llm"
                    return parsed

        except Exception as e:
            self.logger.debug("llm_error_classification_failed", error=str(e))

        return {
            "is_database_error": False,
            "confidence": 0.5,
            "reason": "No database error patterns detected",
            "detection_method": "fallback",
        }
