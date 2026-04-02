"""Deterministic Skeleton Generator — Prio 2 of Pipeline Improvements.

Generates NestJS code scaffolds from ParsedSpec without any LLM calls.
Every endpoint, entity, and service gets its files — guaranteed.

Spec: docs/superpowers/specs/2026-03-16-pipeline-improvements-design.md
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.engine.spec_parser import (
    ParsedSpec, ParsedService, ParsedEndpoint, ParsedEntity, Field, Relation,
)

logger = logging.getLogger(__name__)

PRISMA_TYPE_MAP = {
    "uuid": "String", "string": "String", "text": "String",
    "int": "Int", "integer": "Int", "boolean": "Boolean",
    "datetime": "DateTime", "decimal": "Decimal", "float": "Float",
    "json": "Json", "enum": "String",
}


def _to_pascal(name: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[-_]", name))


def _to_camel(name: str) -> str:
    pascal = _to_pascal(name)
    return pascal[0].lower() + pascal[1:] if pascal else ""


class SkeletonGenerator:
    """Generates deterministic NestJS code scaffolds from ParsedSpec."""

    def __init__(self, spec: ParsedSpec, output_dir: str | Path):
        self.spec = spec
        self.output_dir = Path(output_dir)

    def generate_all(self) -> dict[str, Path]:
        results: dict[str, Path] = {}
        for svc_name in self.spec.generation_order:
            svc = self.spec.services[svc_name]
            svc_dir = self.output_dir / svc_name
            self.generate_service(svc, svc_dir)
            results[svc_name] = svc_dir
        return results

    def generate_service(self, svc: ParsedService, svc_dir: Path) -> None:
        svc_dir.mkdir(parents=True, exist_ok=True)
        self._generate_prisma_schema(svc, svc_dir)
        self._generate_package_json(svc, svc_dir)
        self._generate_tsconfig(svc_dir)
        self._generate_nest_cli(svc_dir)
        self._generate_main_ts(svc, svc_dir)
        self._generate_feature_modules(svc, svc_dir)
        self._generate_app_module(svc, svc_dir)
        self._generate_dockerfile(svc, svc_dir)
        self._generate_test_stubs(svc, svc_dir)
        logger.info("Skeleton generated for %s: %d endpoints, %d entities",
                     svc.name, len(svc.endpoints), len(svc.entities))

    def _generate_prisma_schema(self, svc: ParsedService, svc_dir: Path) -> None:
        prisma_dir = svc_dir / "prisma"
        prisma_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "generator client {", '  provider = "prisma-client-js"', "}", "",
            "datasource db {", '  provider = "postgresql"', '  url      = env("DATABASE_URL")', "}", "",
        ]
        for entity in svc.entities:
            model_name = _to_pascal(entity.name)
            lines.append(f"model {model_name} {{")
            for field in entity.fields:
                prisma_type = PRISMA_TYPE_MAP.get(field.type, "String")
                attrs = []
                if field.name.lower() == "id":
                    attrs.append("@id")
                    if field.type == "uuid":
                        attrs.append("@default(uuid())")
                if field.unique:
                    attrs.append("@unique")
                if field.default and "@default" not in " ".join(attrs):
                    attrs.append(f"@default({field.default})")
                optional = "?" if field.nullable else ""
                attr_str = " ".join(attrs)
                lines.append(f"  {field.name} {prisma_type}{optional} {attr_str}".rstrip())

            field_names = [f.name for f in entity.fields]
            if "createdAt" not in field_names and "created_at" not in field_names:
                lines.append("  createdAt DateTime @default(now())")
            if "updatedAt" not in field_names and "updated_at" not in field_names:
                lines.append("  updatedAt DateTime @updatedAt")
            lines.append("}")
            lines.append("")
        (prisma_dir / "schema.prisma").write_text("\n".join(lines), encoding="utf-8")

    def _generate_feature_modules(self, svc: ParsedService, svc_dir: Path) -> None:
        groups: dict[str, list[ParsedEndpoint]] = {}
        for ep in svc.endpoints:
            m = re.match(r"/api/v\d+/([^/]+)", ep.path)
            feature = m.group(1).replace("-", "_") if m else "default"
            groups.setdefault(feature, []).append(ep)
        if not groups:
            feature = svc.name.replace("-service", "").replace("-worker", "").replace("-", "_")
            groups[feature] = []

        for feature, endpoints in groups.items():
            feature_dir = svc_dir / "src" / feature
            feature_dir.mkdir(parents=True, exist_ok=True)
            (feature_dir / "dto").mkdir(exist_ok=True)
            self._generate_controller(feature, endpoints, svc, feature_dir)
            self._generate_service_file(feature, endpoints, svc, feature_dir)
            self._generate_dtos(feature, endpoints, feature_dir)
            self._generate_module(feature, feature_dir)

    def _generate_controller(self, feature, endpoints, svc, feature_dir):
        class_name = _to_pascal(feature) + "Controller"
        service_name = _to_pascal(feature) + "Service"
        service_var = _to_camel(feature) + "Service"
        lines = [
            f"import {{ Controller, Get, Post, Put, Delete, Patch, Body, Param, Query }} from '@nestjs/common';",
            f"import {{ {service_name} }} from './{feature}.service';",
            "",
            f"@Controller('{feature.replace('_', '-')}')",
            f"export class {class_name} {{",
            f"  constructor(private readonly {service_var}: {service_name}) {{}}",
            "",
        ]
        for ep in endpoints:
            method_decorator = ep.method.capitalize()
            sub_path = re.sub(r"^/api/v\d+/[^/]+/?", "", ep.path)
            method_name = self._endpoint_to_method_name(ep)
            req_dto = ep.request_dto or "any"
            resp_dto = ep.response_dto or "any"
            lines.append(f"  // {ep.method} {ep.path}")
            lines.append(f"  @{method_decorator}('{sub_path}')")
            if ep.method in ("POST", "PUT", "PATCH") and req_dto != "any":
                lines.append(f"  async {method_name}(@Body() dto: {req_dto}): Promise<{resp_dto}> {{")
            elif ":id" in sub_path or "{" in sub_path:
                param = re.search(r":(\w+)|{{(\w+)}}", sub_path)
                param_name = (param.group(1) or param.group(2)) if param else "id"
                lines.append(f"  async {method_name}(@Param('{param_name}') {param_name}: string): Promise<{resp_dto}> {{")
            else:
                lines.append(f"  async {method_name}(): Promise<{resp_dto}> {{")
            lines.append(f"    // TODO: Agent fills implementation")
            lines.append(f"    return this.{service_var}.{method_name}();")
            lines.append(f"  }}")
            lines.append("")
        lines.append("}")
        (feature_dir / f"{feature}.controller.ts").write_text("\n".join(lines), encoding="utf-8")

    def _generate_service_file(self, feature, endpoints, svc, feature_dir):
        service_name = _to_pascal(feature) + "Service"
        lines = [
            "import { Injectable, NotImplementedException } from '@nestjs/common';",
            "import { PrismaService } from '../prisma/prisma.service';",
            "",
            "@Injectable()",
            f"export class {service_name} {{",
            "  constructor(private readonly prisma: PrismaService) {}",
            "",
        ]
        for ep in endpoints:
            method_name = self._endpoint_to_method_name(ep)
            lines.append(f"  async {method_name}(): Promise<any> {{")
            lines.append(f"    // TODO: Agent fills implementation")
            lines.append(f"    throw new NotImplementedException('{method_name}');")
            lines.append(f"  }}")
            lines.append("")
        lines.append("}")
        (feature_dir / f"{feature}.service.ts").write_text("\n".join(lines), encoding="utf-8")

    def _generate_dtos(self, feature, endpoints, feature_dir):
        seen: set[str] = set()
        for ep in endpoints:
            for dto_name in [ep.request_dto, ep.response_dto]:
                if not dto_name or dto_name == "any" or dto_name in seen:
                    continue
                seen.add(dto_name)
                class_name = _to_pascal(dto_name)
                file_name = re.sub(r"(?<!^)(?=[A-Z])", "-", class_name).lower()
                content = (
                    f"import {{ IsString, IsOptional }} from 'class-validator';\n\n"
                    f"export class {class_name} {{\n"
                    f"  // TODO: Add fields from OpenAPI spec\n"
                    f"}}\n"
                )
                (feature_dir / "dto" / f"{file_name}.dto.ts").write_text(content, encoding="utf-8")

    def _generate_module(self, feature, feature_dir):
        controller = _to_pascal(feature) + "Controller"
        service = _to_pascal(feature) + "Service"
        module = _to_pascal(feature) + "Module"
        content = (
            f"import {{ Module }} from '@nestjs/common';\n"
            f"import {{ {controller} }} from './{feature}.controller';\n"
            f"import {{ {service} }} from './{feature}.service';\n\n"
            f"@Module({{\n"
            f"  controllers: [{controller}],\n"
            f"  providers: [{service}],\n"
            f"  exports: [{service}],\n"
            f"}})\n"
            f"export class {module} {{}}\n"
        )
        (feature_dir / f"{feature}.module.ts").write_text(content, encoding="utf-8")

    def _generate_main_ts(self, svc, svc_dir):
        src_dir = svc_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "import { NestFactory } from '@nestjs/core';\n"
            "import { ValidationPipe } from '@nestjs/common';\n"
            "import { AppModule } from './app.module';\n\n"
            "async function bootstrap() {\n"
            "  const app = await NestFactory.create(AppModule);\n"
            "  app.useGlobalPipes(new ValidationPipe({ whitelist: true }));\n"
            f"  await app.listen({svc.port});\n"
            "}\n"
            "bootstrap();\n"
        )
        (src_dir / "main.ts").write_text(content, encoding="utf-8")

    def _generate_app_module(self, svc, svc_dir):
        src_dir = svc_dir / "src"
        feature_dirs = [d for d in src_dir.iterdir() if d.is_dir() and (d / f"{d.name}.module.ts").exists()]
        imports = []
        import_names = []
        for fd in sorted(feature_dirs):
            mod_name = _to_pascal(fd.name) + "Module"
            imports.append(f"import {{ {mod_name} }} from './{fd.name}/{fd.name}.module';")
            import_names.append(mod_name)
        content = (
            "import { Module } from '@nestjs/common';\n"
            + "\n".join(imports)
            + "\n\n@Module({\n"
            + f"  imports: [{', '.join(import_names)}],\n"
            + "})\n"
            + "export class AppModule {}\n"
        )
        (src_dir / "app.module.ts").write_text(content, encoding="utf-8")

    def _generate_package_json(self, svc, svc_dir):
        pkg = {
            "name": svc.name, "version": "0.0.1",
            "scripts": {"build": "nest build", "start": "nest start", "start:dev": "nest start --watch", "test": "jest", "test:e2e": "jest --config ./test/jest-e2e.json"},
            "dependencies": {
                "@nestjs/common": "^10.3.2", "@nestjs/core": "^10.3.2", "@nestjs/platform-express": "^10.3.2",
                "@prisma/client": "^5.10.0", "class-validator": "^0.14.0", "class-transformer": "^0.5.1",
                "reflect-metadata": "^0.2.0", "rxjs": "^7.8.1",
            },
            "devDependencies": {
                "@nestjs/cli": "^10.3.2", "@nestjs/testing": "^10.3.2", "@types/node": "^20.11.0",
                "jest": "^29.7.0", "prisma": "^5.10.0", "ts-jest": "^29.1.0", "typescript": "^5.5.4",
            },
        }
        (svc_dir / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")

    def _generate_tsconfig(self, svc_dir):
        tsconfig = {
            "compilerOptions": {
                "module": "commonjs", "declaration": True, "removeComments": True,
                "emitDecoratorMetadata": True, "experimentalDecorators": True,
                "allowSyntheticDefaultImports": True, "target": "ES2021",
                "sourceMap": True, "outDir": "./dist", "baseUrl": "./",
                "incremental": True, "strict": True, "esModuleInterop": True,
            },
        }
        (svc_dir / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2), encoding="utf-8")

    def _generate_nest_cli(self, svc_dir):
        config = {"$schema": "https://json.schemastore.org/nest-cli", "collection": "@nestjs/schematics", "sourceRoot": "src"}
        (svc_dir / "nest-cli.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _generate_dockerfile(self, svc, svc_dir):
        content = (
            "FROM node:20-alpine AS builder\nWORKDIR /app\n"
            "COPY package*.json ./\nRUN npm ci\nCOPY . .\nRUN npm run build\n\n"
            "FROM node:20-alpine\nWORKDIR /app\n"
            "COPY --from=builder /app/dist ./dist\n"
            "COPY --from=builder /app/node_modules ./node_modules\n"
            "COPY --from=builder /app/package.json ./\n"
            f"EXPOSE {svc.port}\n"
            'CMD ["node", "dist/main.js"]\n'
        )
        (svc_dir / "Dockerfile").write_text(content, encoding="utf-8")

    def _generate_test_stubs(self, svc, svc_dir):
        test_dir = svc_dir / "test"
        test_dir.mkdir(exist_ok=True)
        feature = svc.name.replace("-service", "").replace("-worker", "")
        lines = [
            "import { Test, TestingModule } from '@nestjs/testing';",
            "import { INestApplication } from '@nestjs/common';",
            "import * as request from 'supertest';",
            "import { AppModule } from '../src/app.module';",
            "",
            f"describe('{svc.name} (e2e)', () => {{",
            "  let app: INestApplication;",
            "",
            "  beforeAll(async () => {",
            "    const moduleFixture: TestingModule = await Test.createTestingModule({",
            "      imports: [AppModule],",
            "    }).compile();",
            "    app = moduleFixture.createNestApplication();",
            "    await app.init();",
            "  });",
            "",
        ]
        for ep in svc.endpoints:
            method = ep.method.lower()
            lines.append(f"  it('{ep.method} {ep.path} should respond', () => {{")
            lines.append(f"    return request(app.getHttpServer()).{method}('{ep.path}').expect(/* TODO */);")
            lines.append(f"  }});")
            lines.append("")
        lines.append("  afterAll(async () => { await app.close(); });")
        lines.append("});")
        (test_dir / f"{feature}.e2e-spec.ts").write_text("\n".join(lines), encoding="utf-8")

    def _endpoint_to_method_name(self, ep: ParsedEndpoint) -> str:
        prefix_map = {"GET": "get", "POST": "create", "PUT": "update", "DELETE": "delete", "PATCH": "patch"}
        prefix = prefix_map.get(ep.method, ep.method.lower())
        parts = [p for p in ep.path.split("/") if p and not p.startswith("{") and not p.startswith(":") and p not in ("api", "v1", "v2")]
        if parts:
            name = _to_pascal(parts[-1])
        else:
            name = "Default"
        return f"{prefix}{name}"
