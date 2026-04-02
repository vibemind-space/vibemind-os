---
name: component-design
description: Design React component hierarchy and hooks
tier_tokens:
  minimal: 120
  standard: 300
  full: 600
---

# Component Design

## Purpose
Design React component hierarchy, custom hooks, and page structure.

## Output
- Component definitions with props, state, hooks
- Custom hooks with API integration
- Page compositions with layouts
- File paths for each artifact

## MUST
- Use functional components with TypeScript
- Define clear props interfaces
- Map hooks to API endpoints
- Include loading/error states in hooks
- Use proper component composition

## MUST NOT
- Use class components
- Use `any` type for props
- Create hooks without error handling
- Mix data fetching with presentation
- Create deep component nesting (max 3 levels)

## Component Structure
```
src/
  components/
    features/       # Feature-specific components
    ui/             # Reusable UI primitives
  hooks/            # Custom hooks
  pages/            # Page components
  types/            # TypeScript types
```

## Visual Design Requirements

ALWAYS apply these design tokens for professional, soft-toned UI:

### Color Palette
- **Background**: `bg-slate-50` for app, `bg-white` for cards
- **Text**: `text-slate-900` for headings, `text-slate-600` for body
- **Primary**: `bg-blue-500` / `hover:bg-blue-600` for actions
- **Borders**: `border-slate-200` for subtle separation

### Component Patterns

**Card Component**
```tsx
<div className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 hover:shadow-md transition-shadow">
  <h2 className="text-slate-900 text-xl font-semibold mb-4">Title</h2>
  <p className="text-slate-600">Content</p>
</div>
```

**Primary Button**
```tsx
<button className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
  Action
</button>
```

**Secondary Button**
```tsx
<button className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg font-medium transition-colors">
  Secondary
</button>
```

**Form Input**
```tsx
<input
  className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all placeholder:text-slate-400"
  placeholder="Enter value..."
/>
```

**Status Badge**
```tsx
<span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
  Active
</span>
```

<!-- END_TIER_MINIMAL -->

## Component Patterns

### Props Interface
```typescript
interface ComponentProps {
  // Required props
  data: DataType;
  onAction: (id: string) => void;
  // Optional props
  className?: string;
  isLoading?: boolean;
}
```

### State Definitions
```typescript
// For useState
state: [
  { name: "isOpen", type: "boolean", initial: "false" },
  { name: "selectedId", type: "string | null", initial: "null" }
]
```

### Event Handlers
```typescript
events: {
  onClick: "(e: React.MouseEvent) => void",
  onSubmit: "(data: FormData) => Promise<void>",
  onChange: "(value: string) => void"
}
```

## Hook Patterns

### Data Fetching Hook
```typescript
function useResources(params?: QueryParams) {
  return {
    data: Resource[] | undefined,
    isLoading: boolean,
    error: Error | null,
    refetch: () => Promise<void>,
    // For mutations
    create: (data: CreateRequest) => Promise<Resource>,
    update: (id: string, data: UpdateRequest) => Promise<Resource>,
    remove: (id: string) => Promise<void>,
  };
}
```

### Real-time Hook
```typescript
function useLiveUpdates(resourceId: string) {
  return {
    lastUpdate: Update | null,
    isConnected: boolean,
    reconnect: () => void,
  };
}
```

<!-- END_TIER_STANDARD -->

## Page Composition

### Layout Pattern
```typescript
// pages/ResourcesPage.tsx
components: ["ResourceFilters", "ResourceList", "Pagination"],
layout: "MainLayout",
guards: ["AuthGuard"],
data_fetching: "client" // or "server" for SSR
```

### Feature Breakdown
| Feature | Components |
|---------|------------|
| List view | Filters, List, Pagination, EmptyState |
| Detail view | Header, Content, Actions, RelatedItems |
| Form view | FormFields, Validation, SubmitButton |
| Dashboard | Cards, Charts, Stats, Timeline |

## Component Categories

### UI Primitives (src/components/ui/)
- Button, Input, Select, Checkbox
- Card, Modal, Dropdown
- Table, DataGrid
- Toast, Alert, Badge

### Feature Components (src/components/features/)
- ResourceCard, ResourceForm
- FilterPanel, SearchBar
- StatusBadge, Timeline

### Layout Components
- MainLayout, AuthLayout
- Sidebar, Header, Footer
- PageContainer, Section

## State Management

### When to use local state
- UI state (open/closed, selected)
- Form values before submission
- Temporary calculations

### When to use global state (zustand)
- User authentication
- App-wide preferences
- Cross-component shared data

### Store Pattern
```typescript
// stores/resourceStore.ts
interface ResourceStore {
  resources: Resource[];
  selectedId: string | null;
  // Actions
  setResources: (resources: Resource[]) => void;
  selectResource: (id: string) => void;
}
```
