---
name: design-system
description: Professional soft-tone UI design system
tier_tokens:
  minimal: 100
  standard: 300
  full: 600
---

# Design System

Professional soft-tone UI design system for consistent, aesthetically pleasing interfaces.

## MUST

- Use Tailwind CSS utility classes exclusively
- Apply consistent color palette (slate for neutrals, blue for primary)
- Use proper border-radius (rounded-lg for cards, rounded-md for buttons)
- Apply shadow-sm for cards, shadow-md for dropdowns/modals
- Use Inter font family for clean readability
- Maintain consistent spacing (p-4, p-6 for containers)

## MUST NOT

- Hard-coded hex colors (use Tailwind classes)
- Inconsistent border-radius between similar elements
- Missing hover/focus states on interactive elements
- Overly saturated or harsh colors
- Missing transition animations on state changes
- Inconsistent spacing between components

## Color Philosophy

**Soft-Tone Palette**: Easy on the eyes, professional appearance

| Use Case | Color | Tailwind Class |
|----------|-------|----------------|
| App Background | #f8fafc | `bg-slate-50` |
| Card Background | #ffffff | `bg-white` |
| Primary Text | #0f172a | `text-slate-900` |
| Secondary Text | #475569 | `text-slate-600` |
| Muted Text | #94a3b8 | `text-slate-400` |
| Primary Action | #3b82f6 | `bg-blue-500` |
| Success | #10b981 | `text-emerald-500` |
| Warning | #f59e0b | `text-amber-500` |
| Error | #ef4444 | `text-red-500` |
| Border | #e2e8f0 | `border-slate-200` |

<!-- END_TIER_MINIMAL -->

## Component Patterns

### Card Component
```tsx
<div className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 hover:shadow-md transition-shadow">
  <h2 className="text-slate-900 text-xl font-semibold mb-4">Card Title</h2>
  <p className="text-slate-600 leading-relaxed">Card content goes here.</p>
</div>
```

### Primary Button
```tsx
<button className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
  Primary Action
</button>
```

### Secondary Button
```tsx
<button className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg font-medium transition-colors">
  Secondary Action
</button>
```

### Ghost Button
```tsx
<button className="hover:bg-slate-100 text-slate-600 px-4 py-2 rounded-lg font-medium transition-colors">
  Ghost Action
</button>
```

### Outline Button
```tsx
<button className="border border-slate-300 hover:border-slate-400 text-slate-700 px-4 py-2 rounded-lg font-medium transition-colors">
  Outline Action
</button>
```

### Form Input
```tsx
<input
  type="text"
  className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all placeholder:text-slate-400"
  placeholder="Enter value..."
/>
```

### Select Dropdown
```tsx
<select className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all bg-white">
  <option>Select option...</option>
</select>
```

### Status Badge
```tsx
// Success
<span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
  Active
</span>

// Warning
<span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
  Pending
</span>

// Error
<span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
  Failed
</span>
```

<!-- END_TIER_STANDARD -->

## Layout Patterns

### Page Container
```tsx
<div className="min-h-screen bg-slate-50">
  <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    {/* Page content */}
  </main>
</div>
```

### Section with Header
```tsx
<section className="mb-8">
  <div className="flex items-center justify-between mb-6">
    <h2 className="text-2xl font-semibold text-slate-900">Section Title</h2>
    <button className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors">
      Action
    </button>
  </div>
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    {/* Grid items */}
  </div>
</section>
```

### Modal/Dialog
```tsx
<div className="fixed inset-0 z-50 flex items-center justify-center">
  {/* Backdrop */}
  <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" />

  {/* Modal */}
  <div className="relative bg-white rounded-2xl shadow-xl max-w-md w-full mx-4 p-6">
    <h3 className="text-xl font-semibold text-slate-900 mb-4">Modal Title</h3>
    <p className="text-slate-600 mb-6">Modal content goes here.</p>
    <div className="flex justify-end gap-3">
      <button className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
        Cancel
      </button>
      <button className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors">
        Confirm
      </button>
    </div>
  </div>
</div>
```

### Sidebar Navigation
```tsx
<nav className="w-64 bg-white border-r border-slate-200 h-screen">
  <div className="p-6">
    <h1 className="text-xl font-bold text-slate-900">App Name</h1>
  </div>
  <ul className="px-3 space-y-1">
    <li>
      <a href="#" className="flex items-center px-3 py-2 rounded-lg bg-blue-50 text-blue-600 font-medium">
        Dashboard
      </a>
    </li>
    <li>
      <a href="#" className="flex items-center px-3 py-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors">
        Settings
      </a>
    </li>
  </ul>
</nav>
```

### Data Table
```tsx
<div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
  <table className="w-full">
    <thead className="bg-slate-50 border-b border-slate-200">
      <tr>
        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
          Name
        </th>
        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
          Status
        </th>
      </tr>
    </thead>
    <tbody className="divide-y divide-slate-100">
      <tr className="hover:bg-slate-50 transition-colors">
        <td className="px-6 py-4 text-sm text-slate-900">Item Name</td>
        <td className="px-6 py-4">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
            Active
          </span>
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

### Empty State
```tsx
<div className="text-center py-12">
  <div className="mx-auto h-12 w-12 text-slate-400">
    {/* Icon */}
  </div>
  <h3 className="mt-4 text-lg font-medium text-slate-900">No items yet</h3>
  <p className="mt-2 text-sm text-slate-500">Get started by creating your first item.</p>
  <button className="mt-6 bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors">
    Create Item
  </button>
</div>
```

## Accessibility

- All interactive elements must have visible focus states
- Use `focus:ring-2 focus:ring-blue-500 focus:ring-offset-2` for focus indication
- Maintain sufficient color contrast (WCAG AA minimum)
- Include `aria-label` on icon-only buttons
- Use semantic HTML elements (button, nav, main, section)

## Animation Guidelines

- Use `transition-colors` for color changes (150ms)
- Use `transition-shadow` for elevation changes (200ms)
- Use `transition-all` sparingly for complex animations
- Avoid animations that last longer than 300ms
- Respect `prefers-reduced-motion` media query
