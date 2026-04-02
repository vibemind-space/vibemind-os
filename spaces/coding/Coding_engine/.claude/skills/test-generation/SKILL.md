---
name: test-generation
description: Generate Vitest/Jest test suites - NO MOCKS
tier_tokens:
  minimal: 100
  standard: 250
  full: 500
---

# Test Generation

## CRITICAL: NO MOCKS POLICY

All tests must be **real integration tests**. Tests are validated by `NoMockValidator` and **rejected** if mocking patterns detected.

## FORBIDDEN (validation failure)

- `vi.fn()`, `vi.mock()`, `vi.spyOn()`
- `jest.fn()`, `jest.mock()`, `jest.spyOn()`
- `.mockImplementation()`, `.mockReturnValue()`
- `sinon.stub()`, `sinon.mock()`
- `nock()`, `fetchMock`, `msw`
- `global.fetch = vi.fn()`

## REQUIRED Approach

| Instead of...        | Use...                              |
| -------------------- | ----------------------------------- |
| Mocking fetch        | Real HTTP to test server            |
| Mocking database     | SQLite in-memory or test container  |
| Mock functions       | Real callbacks with state tracking  |
| Mocking timers       | Real timers with short delays       |

<!-- END_TIER_MINIMAL -->

## Test Patterns

### Callback Tracking (NO vi.fn)

```tsx
let clickCount = 0;
const handleClick = () => { clickCount++; };
// Assert: expect(clickCount).toBe(1);
```

### Real Test Server

```typescript
// Start real Express server on port 0
const server = app.listen(0);
const port = (server.address() as any).port;
// Test against http://localhost:${port}
```

## Coverage Targets

| Metric     | Target |
| ---------- | ------ |
| Statements | 80%    |
| Branches   | 75%    |
| Functions  | 80%    |

<!-- END_TIER_STANDARD -->

## Test File Structure

- `tests/` or `__tests__/` directory
- `*.test.ts` or `*.test.tsx` extension
- One test file per source file

## Best Practices

- Test behavior, not implementation
- AAA pattern: Arrange, Act, Assert
- Descriptive names: "should display error when email invalid"
- Test edge cases: empty arrays, null, boundaries
