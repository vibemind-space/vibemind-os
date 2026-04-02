---
name: ce-code-quality
description: Review quality of generated code. Checks for empty files, broken imports, missing modules, duplicate code, TypeScript errors, and rates overall quality. Identifies files that need regeneration.
trigger: When user asks to "review code quality", "check generated code", "is the code real", "any empty files", "code review the output"
---

# ce-code-quality — Generated Code Quality Audit

## Step 1: File Inventory

```bash
docker exec coding-engine-api bash -c "
cd /app/output/*/
echo '=== FILE COUNTS ==='
echo 'Controllers:' && find src/modules -name '*.controller.ts' 2>/dev/null | wc -l
echo 'Services:' && find src/modules -name '*.service.ts' 2>/dev/null | wc -l
echo 'DTOs:' && find src -name '*.dto.ts' 2>/dev/null | wc -l
echo 'Guards:' && find src -name '*.guard.ts' 2>/dev/null | wc -l
echo 'Validators:' && find src -name '*.validator.ts' 2>/dev/null | wc -l
echo 'Frontend Pages:' && find frontend/src -name '*.tsx' 2>/dev/null | grep -v node_modules | wc -l
echo 'Hooks:' && find src/hooks -name '*.ts' 2>/dev/null | wc -l
"
```

## Step 2: Empty File Detection

```bash
docker exec coding-engine-api bash -c "
cd /app/output/*/
echo '=== EMPTY OR TINY FILES (< 50 bytes) ==='
find src -type f -name '*.ts' -o -name '*.tsx' 2>/dev/null | grep -v node_modules | while read f; do
  size=\$(wc -c < \"\$f\")
  if [ \$size -lt 50 ]; then echo \"EMPTY: \$f (\${size}b)\"; fi
done
echo '=== PLACEHOLDER FILES (contain only imports/exports) ==='
find src -type f -name '*.ts' 2>/dev/null | grep -v node_modules | while read f; do
  lines=\$(wc -l < \"\$f\")
  if [ \$lines -lt 5 ]; then echo \"STUB: \$f (\${lines} lines)\"; fi
done | head -20
"
```

## Step 3: Import Health Check

```bash
docker exec coding-engine-api bash -c "
cd /app/output/*/
echo '=== BROKEN IMPORTS ==='
grep -rn 'from.*react-native' src/modules/ src/api/ 2>/dev/null | head -5 && echo '^^^ react-native in backend = BUG'
grep -rn 'from.*generated/prisma' src/modules/ 2>/dev/null | head -3 && echo '^^^ prisma import (check if client exists)'
echo '=== MISSING MODULE IMPORTS ==='
grep -rn \"Cannot find module\" /app/output/*/generation.log 2>/dev/null | tail -5
"
```

## Step 4: Code Substance Check (sample 5 files)

For each: read first 20 lines, check if it has real logic (not just boilerplate)

```bash
docker exec coding-engine-api bash -c "
cd /app/output/*/
echo '=== SAMPLE: auth.controller.ts ==='
head -25 src/modules/auth/auth.controller.ts 2>/dev/null || echo 'NOT FOUND'
echo '=== SAMPLE: messages service ==='
head -25 src/modules/messages/messages.service.ts 2>/dev/null || echo 'NOT FOUND'
echo '=== SAMPLE: contacts controller ==='
head -25 src/modules/contacts/contacts.controller.ts 2>/dev/null || echo 'NOT FOUND'
echo '=== SAMPLE: chats service ==='
head -25 src/modules/chats/chats.service.ts 2>/dev/null || echo 'NOT FOUND'
echo '=== SAMPLE: users controller ==='
head -25 src/modules/users/users.controller.ts 2>/dev/null || echo 'NOT FOUND'
"
```

## Step 5: Build Test

```bash
docker exec coding-engine-api bash -c "
cd /app/output/*/
npx tsc --noEmit 2>&1 | tail -20
echo '---EXIT CODE: '\$?
"
```

## Step 6: Rate and Report

Present findings as:

```
# 🔍 Code Quality Audit

## File Inventory
| Type | Count | With Real Logic | Empty/Stub |

## Quality Rating: X/10
- Real controllers with routes: X
- Services with business logic: X
- Empty/placeholder files: X
- Broken imports: X
- Build errors: X

## Issues Found
1. [CRITICAL] ...
2. [WARNING] ...

## Files That Need Regeneration
- path/to/file.ts — reason
```
