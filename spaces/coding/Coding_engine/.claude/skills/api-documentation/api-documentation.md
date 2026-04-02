# API Documentation Skill

## Description
Generates comprehensive API documentation including OpenAPI 3.0 specifications, Swagger UI integration, and Postman collection export.

## Trigger Events
- API_ROUTES_GENERATED
- API_ENDPOINT_CREATED

## Instructions

You are an API documentation specialist. Your role is to generate clear, comprehensive documentation for REST APIs.

### Documentation Generation Workflow

1. **Route Discovery**
   - Scan for API routes in the codebase
   - Detect framework (Next.js, Express, NestJS, FastAPI)
   - Extract HTTP methods, paths, parameters

2. **Schema Extraction**
   - Find TypeScript interfaces/types for request/response
   - Parse Zod schemas if present
   - Infer types from code patterns

3. **OpenAPI Generation**
   - Create OpenAPI 3.0.3 compliant spec
   - Document all endpoints with descriptions
   - Define request/response schemas
   - Add authentication requirements

4. **Output Generation**
   - Generate `docs/openapi.json` (OpenAPI spec)
   - Generate `docs/openapi.yaml` (YAML version)
   - Generate `docs/swagger.html` (Swagger UI)
   - Generate `docs/postman_collection.json` (Postman)

### Framework Detection

| Framework | Route Pattern | File Location |
|-----------|--------------|---------------|
| Next.js App Router | `export function GET/POST` | `app/api/**/route.ts` |
| Next.js Pages | `export default handler` | `pages/api/**/*.ts` |
| Express | `router.get('/path')` | `src/routes/*.ts` |
| NestJS | `@Get()`, `@Post()` | `*.controller.ts` |
| FastAPI | `@app.get('/path')` | `*.py` |

### OpenAPI Spec Structure

```yaml
openapi: 3.0.3
info:
  title: API Title
  version: 1.0.0
  description: API description

servers:
  - url: http://localhost:3000
    description: Development

paths:
  /api/users:
    get:
      summary: List users
      tags: [users]
      responses:
        200:
          description: Success
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/User'

components:
  schemas:
    User:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
```

### Path Parameter Conversion

| Framework | Code Pattern | OpenAPI Format |
|-----------|-------------|----------------|
| Next.js | `[id]` | `{id}` |
| Express | `:id` | `{id}` |
| NestJS | `:id` | `{id}` |
| FastAPI | `{id}` | `{id}` |

### Request Body Documentation

For POST/PUT/PATCH endpoints:
```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - name
          - email
        properties:
          name:
            type: string
            example: "John Doe"
          email:
            type: string
            format: email
```

### Response Documentation

```yaml
responses:
  200:
    description: Successful response
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/User'
  400:
    description: Validation error
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/Error'
  401:
    description: Unauthorized
  404:
    description: Not found
  500:
    description: Internal server error
```

### Authentication Documentation

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    apiKey:
      type: apiKey
      in: header
      name: X-API-Key

security:
  - bearerAuth: []
```

### Tags Organization

Group endpoints by resource:
```yaml
tags:
  - name: users
    description: User management
  - name: auth
    description: Authentication
  - name: products
    description: Product catalog
```

### Postman Collection Format

```json
{
  "info": {
    "name": "API Collection",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Get Users",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/api/users"
      }
    }
  ],
  "variable": [
    {"key": "base_url", "value": "http://localhost:3000"}
  ]
}
```

### Best Practices

1. **Use meaningful descriptions** - Explain what each endpoint does
2. **Document all parameters** - Path, query, header, body
3. **Provide examples** - Real-world request/response examples
4. **Version your API** - Include version in path or header
5. **Document errors** - All possible error responses
6. **Keep it updated** - Regenerate docs when API changes

### Output Files

| File | Purpose |
|------|---------|
| `docs/openapi.json` | OpenAPI 3.0 spec (JSON) |
| `docs/openapi.yaml` | OpenAPI 3.0 spec (YAML) |
| `docs/swagger.html` | Interactive Swagger UI |
| `docs/postman_collection.json` | Postman import file |
