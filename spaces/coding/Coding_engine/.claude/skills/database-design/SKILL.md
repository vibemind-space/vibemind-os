---
name: database-design
description: Generate Prisma/PostgreSQL database schemas
tier_tokens:
  minimal: 120
  standard: 300
  full: 600
---

# Database Design

## Purpose
Generate complete Prisma schema from enriched requirements.

## Output Format
Valid Prisma schema with:
- Models with proper field types
- Relations (1:1, 1:N, N:M)
- Indexes for query optimization
- Enums for fixed value sets

## MUST
- Use PostgreSQL-compatible types
- Include `id`, `createdAt`, `updatedAt` on all models
- Define both sides of relations
- Add indexes for foreign keys and frequently queried fields
- Use UUIDs for primary keys: `@id @default(uuid())`

## MUST NOT
- Use `any` or loose types
- Create circular dependencies without explicit handling
- Miss foreign key indexes
- Forget `@updatedAt` on updatedAt field
- Use auto-increment IDs (use UUIDs)

## Common Patterns

```prisma
model Entity {
  id        String   @id @default(uuid())
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  // Foreign key
  parentId  String
  parent    Parent   @relation(fields: [parentId], references: [id], onDelete: Cascade)

  @@index([parentId])
}
```

<!-- END_TIER_MINIMAL -->

## Field Type Mapping

| Concept | Prisma Type | Attributes |
|---------|-------------|------------|
| Identifier | String | @id @default(uuid()) |
| Created timestamp | DateTime | @default(now()) |
| Updated timestamp | DateTime | @updatedAt |
| Email | String | @unique |
| Large text | String | @db.Text |
| Money | Decimal | @db.Decimal(10, 2) |
| JSON data | Json | |
| Coordinates | Float | (latitude, longitude) |
| Status | Enum | Define enum type |
| Boolean flag | Boolean | @default(false) |

## Relation Patterns

### One-to-Many
```prisma
model User {
  id    String @id @default(uuid())
  posts Post[]
}

model Post {
  id       String @id @default(uuid())
  userId   String
  user     User   @relation(fields: [userId], references: [id])
  @@index([userId])
}
```

### Many-to-Many (Explicit)
```prisma
model Post {
  id       String     @id @default(uuid())
  tags     PostTag[]
}

model Tag {
  id    String    @id @default(uuid())
  posts PostTag[]
}

model PostTag {
  postId String
  tagId  String
  post   Post   @relation(fields: [postId], references: [id])
  tag    Tag    @relation(fields: [tagId], references: [id])
  @@id([postId, tagId])
}
```

<!-- END_TIER_STANDARD -->

## Advanced Patterns

### Soft Delete
```prisma
model Entity {
  id        String    @id @default(uuid())
  deletedAt DateTime?
  isDeleted Boolean   @default(false)

  @@index([isDeleted])
}
```

### Polymorphic Relations
```prisma
model Comment {
  id            String @id @default(uuid())
  commentableId String
  commentableType String // "Post" | "Photo"

  @@index([commentableId, commentableType])
}
```

### Audit Trail
```prisma
model AuditLog {
  id         String   @id @default(uuid())
  entityType String
  entityId   String
  action     String   // CREATE, UPDATE, DELETE
  changes    Json
  userId     String
  createdAt  DateTime @default(now())

  @@index([entityType, entityId])
  @@index([userId])
}
```

### Versioning
```prisma
model Document {
  id        String   @id @default(uuid())
  version   Int      @default(1)

  @@unique([id, version])
}
```

## Index Strategy

| Query Pattern | Index Type |
|--------------|------------|
| WHERE field = value | Single column |
| WHERE a = x AND b = y | Composite @@index([a, b]) |
| ORDER BY field | Single column |
| Full-text search | Use pg_trgm extension |
| Geo queries | PostGIS GIST index |
