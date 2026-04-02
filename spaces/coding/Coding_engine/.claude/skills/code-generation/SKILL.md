---
name: code-generation
description: Generate/fix TypeScript+React code
tier_tokens:
  minimal: 80
  standard: 200
  full: 400
---

# Code Generation

## MUST

- TypeScript strict mode, proper types (no `any`)
- React functional components + hooks
- Minimal changes - fix only what's broken
- Write files using Write tool
- Run build to verify fix

## MUST NOT

- No mocks or placeholder data
- No unused imports/variables
- No refactoring unrelated code
- No TODOs or placeholder comments

## Error Patterns

| Error                                 | Fix                                    |
| ------------------------------------- | -------------------------------------- |
| `Property 'x' does not exist`         | Add to interface or fix typo           |
| `Cannot find module`                  | Create file or install package         |
| `Type 'X' not assignable to 'Y'`      | Fix type definition or cast            |
| `Cannot read property of undefined`   | Add `?.` optional chaining             |
| `'X' declared but never used`         | Remove or use the variable             |

<!-- END_TIER_MINIMAL -->

## Standard Patterns

### Import Errors

- Missing default export: Add `export default` or use named import
- Circular dependency: Restructure imports or use lazy loading

### Type Errors

- Generic constraint: Add `extends` constraint to type parameter
- Union narrowing: Add type guard or discriminant check

### Runtime Errors

- Async/await: Add try/catch, handle promise rejections
- Event handlers: Bind context or use arrow functions

<!-- END_TIER_STANDARD -->

## VibeMind Space Theme (Default)

All generated React projects use the VibeMind Space Theme:

**Color Variables:**
- `--neon-purple: #a855f7` - Primary accent (buttons, links, focus)
- `--neon-cyan: #22d3ee` - Secondary accent
- `--bg-space-dark: #0a0a0f` - Dark background
- `--glass-border: rgba(255, 255, 255, 0.1)` - Card borders

**Component Classes:**
- `.glass-card` - Glassmorphism card with blur
- `.glass-card-hover` - Add hover effects to cards
- `.btn-primary` - Primary action button
- `.btn-secondary` - Secondary/ghost button
- `.input-field` - Styled input fields
- `.gradient-text` - Purple gradient text

**Example Component:**
```tsx
<div className="glass-card glass-card-hover p-6">
  <h2 className="text-xl font-bold text-white mb-4">Title</h2>
  <p className="text-slate-400">Content</p>
  <button className="btn-primary mt-4">Action</button>
</div>
```

## Agent Type Guidelines

### Frontend Agent

- Components in `src/components/`
- Hooks in `src/hooks/`
- Types in `src/types/`
- **Use VibeMind theme classes** (glass-card, btn-primary, etc.)

### Backend Agent

- Routes in `src/api/` or `src/routes/`
- Services in `src/services/`
- Models in `src/models/`

### Database Services (Fullstack Projects)

**CRITICAL: For fullstack projects, ALWAYS use Prisma for data persistence.**

Check for `prisma/schema.prisma` - if it exists, services MUST use Prisma:

```typescript
// CORRECT - Use Prisma
import { prisma } from '../lib/prisma'

export class TransportService {
  async create(data: CreateTransportInput) {
    return prisma.transport.create({ data })
  }
  async findById(id: string) {
    return prisma.transport.findUnique({ where: { id } })
  }
  async findAll() {
    return prisma.transport.findMany()
  }
  async update(id: string, data: UpdateTransportInput) {
    return prisma.transport.update({ where: { id }, data })
  }
  async delete(id: string) {
    return prisma.transport.delete({ where: { id } })
  }
}
```

**NEVER use in-memory storage:**
```typescript
// WRONG - Do NOT use Map for data storage
const store = new Map<string, Transport>()  // ❌ FORBIDDEN

// WRONG - Do NOT use arrays as data store
const transports: Transport[] = []  // ❌ FORBIDDEN
```

Prisma query mapping:
| Operation | Prisma Method |
|-----------|---------------|
| Create | `prisma.model.create({ data })` |
| Find one | `prisma.model.findUnique({ where: { id } })` |
| Find many | `prisma.model.findMany({ where, orderBy })` |
| Update | `prisma.model.update({ where: { id }, data })` |
| Delete | `prisma.model.delete({ where: { id } })` |
| Count | `prisma.model.count({ where })` |

## Validation

After code generation:

1. `npm run build` - verify compilation
2. `npm run typecheck` - verify types
3. `npm run test` - verify tests pass
