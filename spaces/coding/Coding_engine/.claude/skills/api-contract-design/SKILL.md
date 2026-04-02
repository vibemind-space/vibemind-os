---
name: api-contract-design
description: Design REST/WebSocket API contracts with TypeScript types
tier_tokens:
  minimal: 150
  standard: 300
  full: 400
---

# API Contract Design

## Task

Generate TypeScript interfaces from software requirements.

## Output Format

Return ONLY valid JSON:

```json
{
  "types": [{"name": "...", "fields": {...}, "description": "..."}],
  "endpoints": [{"path": "/api/...", "method": "GET", "response_type": "..."}],
  "components": [{"name": "...", "props": {...}}],
  "services": [{"name": "...", "methods": {...}}]
}
```

## Rules

- Domain-specific types (User, Order, Vehicle) NOT generic (Config, Result)
- Every entity needs CRUD endpoints (GET, POST, PUT, DELETE)
- No `any` types - be specific
- Include id, createdAt, updatedAt fields
- Infer relationships (Order.userId -> User)

<!-- END_TIER_MINIMAL -->

## Type Schema

```typescript
interface TypeDefinition {
  name: string
  fields: Record<string, string>  // fieldName: "TypeScript type"
  description: string
  optional_fields?: string[]
}
```

## Endpoint Schema

```typescript
interface APIEndpoint {
  path: string           // "/api/v1/users"
  method: "GET" | "POST" | "PUT" | "DELETE"
  request_type?: string  // Request body type
  response_type: string  // Response type
  auth_required: boolean
  tags: string[]
}
```

## Component Schema

```typescript
interface ComponentContract {
  name: string
  props: Record<string, string>
  description: string
  children?: boolean
  events?: string[]
}
```

<!-- END_TIER_STANDARD -->

## Anti-Patterns

- Generic types: Config, Result, Data, Item
- Empty interfaces
- Duplicate types
- Missing endpoints for data types
- Using `any` type

## CRUD Pattern

For each entity, generate:

| Method | Path | Action |
| ------ | ---- | ------ |
| GET | /api/v1/{resource}s | List all |
| GET | /api/v1/{resource}s/{id} | Get by ID |
| POST | /api/v1/{resource}s | Create |
| PUT | /api/v1/{resource}s/{id} | Update |
| DELETE | /api/v1/{resource}s/{id} | Delete |

## Service Schema

```typescript
interface ServiceContract {
  name: string
  methods: Record<string, {
    params: Record<string, string>
    return_type: string
    description: string
  }>
  description: string
}
```
