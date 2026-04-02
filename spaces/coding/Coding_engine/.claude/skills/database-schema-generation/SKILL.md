---
name: database-schema-generation
description: Generates database schemas (Prisma, SQLAlchemy, Drizzle) from TypeScript contracts and requirements
trigger_events: [CONTRACTS_GENERATED, SCHEMA_UPDATE_NEEDED, DATABASE_MIGRATION_NEEDED]
---

# Database Schema Generation Skill

## Purpose

Generate complete, production-ready database schemas from TypeScript interfaces and requirements.
This skill transforms contracts into Prisma/SQLAlchemy/Drizzle schemas with proper relationships,
indexes, and constraints.

## Supported ORMs

| ORM | Language | Primary Use Case |
|-----|----------|-----------------|
| **Prisma** | TypeScript/Node.js | React, Next.js, Node backends |
| **SQLAlchemy** | Python | FastAPI, Flask, Django |
| **Drizzle** | TypeScript | Lightweight, SQL-first |
| **TypeORM** | TypeScript | Enterprise Node.js |

## Trigger Events

| Event | Action |
|-------|--------|
| `CONTRACTS_GENERATED` | Generate initial schema from contracts |
| `SCHEMA_UPDATE_NEEDED` | Update schema when models change |
| `DATABASE_MIGRATION_NEEDED` | Generate and apply migration |

## Schema Generation Rules

### 1. Entity Detection
- Each `interface` with `id` field becomes a model
- Nested objects become separate models with relations
- Arrays of primitives become JSON fields
- Arrays of objects become 1:n relations

### 2. Field Mapping

| TypeScript | Prisma | SQLAlchemy |
|------------|--------|------------|
| `string` | `String` | `String` |
| `number` | `Int` or `Float` | `Integer` or `Float` |
| `boolean` | `Boolean` | `Boolean` |
| `Date` | `DateTime` | `DateTime` |
| `string?` | `String?` | `String, nullable=True` |
| `enum` | `enum` | `Enum` |

### 3. Relationship Detection

```typescript
// 1:1 - User has one Profile
interface User {
  profile: Profile;
}

// 1:n - User has many Posts
interface User {
  posts: Post[];
}

// n:m - Post has many Tags, Tag has many Posts
interface Post {
  tags: Tag[];
}
interface Tag {
  posts: Post[];
}
```

## Example Transformation

### Input: TypeScript Contract

```typescript
interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  posts: Post[];
  profile?: Profile;
  createdAt: Date;
  updatedAt: Date;
}

enum UserRole {
  ADMIN = "admin",
  USER = "user",
  GUEST = "guest"
}

interface Post {
  id: string;
  title: string;
  content: string;
  published: boolean;
  authorId: string;
  author: User;
  tags: Tag[];
}

interface Tag {
  id: string;
  name: string;
  posts: Post[];
}

interface Profile {
  id: string;
  bio?: string;
  avatar?: string;
  userId: string;
  user: User;
}
```

### Output: Prisma Schema

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

enum UserRole {
  ADMIN
  USER
  GUEST
}

model User {
  id        String    @id @default(uuid())
  email     String    @unique
  name      String
  role      UserRole  @default(USER)
  posts     Post[]
  profile   Profile?
  createdAt DateTime  @default(now())
  updatedAt DateTime  @updatedAt

  @@index([email])
  @@index([role])
}

model Post {
  id        String   @id @default(uuid())
  title     String
  content   String   @db.Text
  published Boolean  @default(false)
  author    User     @relation(fields: [authorId], references: [id], onDelete: Cascade)
  authorId  String
  tags      Tag[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  @@index([authorId])
  @@index([published])
}

model Tag {
  id    String @id @default(uuid())
  name  String @unique
  posts Post[]
}

model Profile {
  id     String  @id @default(uuid())
  bio    String? @db.Text
  avatar String?
  user   User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  userId String  @unique
}
```

## Migration Strategy

### Initial Migration
```bash
npx prisma migrate dev --name init
```

### Safe Migrations (preserve data)
1. Add new columns as nullable first
2. Migrate existing data
3. Add NOT NULL constraint

### Migration Workflow
```
Schema Change Detected
       ↓
Generate Migration SQL
       ↓
Review for Data Loss
       ↓
Apply Migration
       ↓
DATABASE_MIGRATION_COMPLETE Event
```

## Seed Data Generation

Generate seed data from requirements or sample data:

```typescript
// prisma/seed.ts
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  // Create admin user
  const admin = await prisma.user.upsert({
    where: { email: 'admin@example.com' },
    update: {},
    create: {
      email: 'admin@example.com',
      name: 'Admin User',
      role: 'ADMIN',
      profile: {
        create: {
          bio: 'System administrator',
        },
      },
    },
  });

  console.log({ admin });
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
```

## Database Client Setup

```typescript
// src/lib/prisma.ts
// CRITICAL: Load env vars BEFORE PrismaClient initialization (ESM hoisting fix)
import 'dotenv/config';
import { PrismaClient } from '@prisma/client';

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma = globalForPrisma.prisma ?? new PrismaClient({
  log: process.env.NODE_ENV === 'development'
    ? ['query', 'error', 'warn']
    : ['error'],
});

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma;
}
```

## Anti-Mock Policy

### NIEMALS generieren:
- [ ] Hardcoded Daten-Arrays als "Datenbank-Ersatz"
- [ ] In-Memory SQLite ohne Persistenz
- [ ] Mock-Datenbank-Clients
- [ ] Fake-Queries die keine echte DB ansprechen

### IMMER generieren:
- [x] Echtes Prisma/SQLAlchemy Schema
- [x] Funktionierende Migrations
- [x] Seed-Dateien mit echten Daten
- [x] Prisma Client mit echten Queries

## Output Files

```
output/
├── prisma/
│   ├── schema.prisma       # Database schema
│   ├── migrations/         # Auto-generated migrations
│   └── seed.ts            # Seed data script
├── src/
│   ├── lib/
│   │   └── prisma.ts      # Prisma client singleton
│   └── db/
│       └── queries.ts     # Common query helpers
└── package.json           # prisma, @prisma/client deps
```

## Environment Requirements

```env
# .env.local
DATABASE_URL="postgresql://user:password@localhost:5432/mydb?schema=public"
```

## Docker Integration

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-dev}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-dev}
      POSTGRES_DB: ${POSTGRES_DB:-app}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-dev}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```
