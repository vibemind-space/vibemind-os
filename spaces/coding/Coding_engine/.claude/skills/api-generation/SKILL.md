---
name: api-generation
description: Generate REST APIs from TypeScript contracts with CRUD operations
tier_tokens:
  minimal: 80
  standard: 200
  full: 400
---

# API Generation

## MUST

- Generate real Prisma/DB queries (no mocks)
- Use Zod for input validation
- Return proper HTTP status codes
- Include complete error handling
- Type-safe request/response

## MUST NOT

- No hardcoded response data
- No in-memory arrays as data source
- No TODO comments or stubs
- No empty function bodies

## CRUD Mapping

| Method   | Endpoint         | Action      | Prisma           |
| -------- | ---------------- | ----------- | ---------------- |
| `GET`    | `/api/users`     | List all    | `findMany()`     |
| `GET`    | `/api/users/:id` | Get single  | `findUnique()`   |
| `POST`   | `/api/users`     | Create      | `create()`       |
| `PUT`    | `/api/users/:id` | Full update | `update()`       |
| `PATCH`  | `/api/users/:id` | Partial     | `update()`       |
| `DELETE` | `/api/users/:id` | Delete      | `delete()`       |

<!-- END_TIER_MINIMAL -->

## Status Codes

| Code | Meaning       | When                    |
| ---- | ------------- | ----------------------- |
| 200  | Success       | GET, PUT returns data   |
| 201  | Created       | POST new resource       |
| 204  | No Content    | DELETE success          |
| 400  | Bad Request   | Validation error        |
| 401  | Unauthorized  | Missing/invalid token   |
| 404  | Not Found     | Resource doesn't exist  |
| 409  | Conflict      | Duplicate unique field  |
| 500  | Server Error  | Database/internal error |

## Validation Rules

- Required fields: 400 if missing
- Email fields: Validate format
- String length: min/max constraints
- Enum values: Validate against allowed
- Foreign keys: Validate existence

<!-- END_TIER_STANDARD -->

## File Structure

```
src/
├── api/ or app/api/
│   └── users/
│       ├── route.ts      # GET (list), POST
│       └── [id]/route.ts # GET, PUT, DELETE
├── lib/
│   └── validators/       # Zod schemas
└── middleware.ts         # Auth
```

## Frameworks

- **Express.js**: TypeScript/Node standalone APIs
- **Next.js API Routes**: React/Next.js apps
- **FastAPI**: Python backends
