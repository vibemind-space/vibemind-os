# Design System Tokens

Professional soft-tone design tokens for consistent, aesthetically pleasing UI.

## Color Palette (Professional Soft-Tone)

### Base Colors
- **Background**: `#f8fafc` (slate-50) - Main app background
- **Surface**: `#ffffff` - Cards, modals, panels
- **Surface Hover**: `#f1f5f9` (slate-100) - Interactive surface states
- **Surface Alt**: `#f8fafc` (slate-50) - Alternate surface

### Text Colors
- **Primary**: `#0f172a` (slate-900) - Headings, important text
- **Secondary**: `#475569` (slate-600) - Body text, descriptions
- **Muted**: `#94a3b8` (slate-400) - Labels, placeholders, hints
- **Inverse**: `#ffffff` - Text on dark backgrounds

### Accent Colors
- **Primary**: `#3b82f6` (blue-500) - Primary actions, links
- **Primary Hover**: `#2563eb` (blue-600) - Primary hover state
- **Primary Light**: `#dbeafe` (blue-100) - Primary backgrounds
- **Success**: `#10b981` (emerald-500) - Success states
- **Success Light**: `#d1fae5` (emerald-100) - Success backgrounds
- **Warning**: `#f59e0b` (amber-500) - Warning states
- **Warning Light**: `#fef3c7` (amber-100) - Warning backgrounds
- **Error**: `#ef4444` (red-500) - Error states
- **Error Light**: `#fee2e2` (red-100) - Error backgrounds
- **Info**: `#0ea5e9` (sky-500) - Info states

### Border Colors
- **Default**: `#e2e8f0` (slate-200) - Standard borders
- **Muted**: `#f1f5f9` (slate-100) - Subtle borders
- **Focus**: `#3b82f6` (blue-500) - Focus rings

## Shadows

### Elevation Levels
- **xs**: `0 1px 2px 0 rgb(0 0 0 / 0.05)` - Subtle lift
- **sm**: `0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)` - Cards
- **md**: `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)` - Dropdowns
- **lg**: `0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)` - Modals
- **xl**: `0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)` - Floating
- **inner**: `inset 0 2px 4px 0 rgb(0 0 0 / 0.05)` - Inset elements

## Border Radius

- **none**: `0px` - Sharp corners
- **sm**: `4px` - Subtle rounding
- **md**: `6px` - Standard rounding
- **lg**: `8px` - Cards, buttons
- **xl**: `12px` - Large cards
- **2xl**: `16px` - Feature cards
- **full**: `9999px` - Pills, avatars

## Spacing Scale

- **0**: `0px`
- **px**: `1px`
- **0.5**: `2px`
- **1**: `4px`
- **1.5**: `6px`
- **2**: `8px`
- **2.5**: `10px`
- **3**: `12px`
- **3.5**: `14px`
- **4**: `16px`
- **5**: `20px`
- **6**: `24px`
- **7**: `28px`
- **8**: `32px`
- **9**: `36px`
- **10**: `40px`
- **12**: `48px`
- **14**: `56px`
- **16**: `64px`

## Typography

### Font Family
- **Sans**: `'Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif`
- **Mono**: `'JetBrains Mono', ui-monospace, 'Cascadia Code', monospace`

### Font Sizes
- **xs**: `12px` / `16px` line-height
- **sm**: `14px` / `20px` line-height
- **base**: `16px` / `24px` line-height
- **lg**: `18px` / `28px` line-height
- **xl**: `20px` / `28px` line-height
- **2xl**: `24px` / `32px` line-height
- **3xl**: `30px` / `36px` line-height
- **4xl**: `36px` / `40px` line-height

### Font Weights
- **normal**: `400` - Body text
- **medium**: `500` - Emphasized text
- **semibold**: `600` - Subheadings
- **bold**: `700` - Headings

### Letter Spacing
- **tighter**: `-0.05em` - Large headings
- **tight**: `-0.025em` - Headings
- **normal**: `0em` - Body text
- **wide**: `0.025em` - Labels
- **wider**: `0.05em` - Uppercase text

## Transitions

### Duration
- **fast**: `150ms` - Quick feedback
- **normal**: `200ms` - Standard transitions
- **slow**: `300ms` - Emphasis transitions
- **slower**: `500ms` - Significant changes

### Easing
- **default**: `cubic-bezier(0.4, 0, 0.2, 1)` - Standard
- **in**: `cubic-bezier(0.4, 0, 1, 1)` - Enter
- **out**: `cubic-bezier(0, 0, 0.2, 1)` - Exit
- **in-out**: `cubic-bezier(0.4, 0, 0.2, 1)` - Smooth

## Z-Index Scale

- **auto**: `auto`
- **0**: `0` - Base
- **10**: `10` - Dropdowns
- **20**: `20` - Sticky headers
- **30**: `30` - Fixed elements
- **40**: `40` - Modals backdrop
- **50**: `50` - Modals
- **60**: `60` - Popovers
- **70**: `70` - Tooltips
- **80**: `80` - Notifications
- **90**: `90` - Maximum

## Tailwind CSS Quick Reference

### Card Pattern
```
bg-white rounded-xl shadow-sm border border-slate-100 p-6
```

### Primary Button
```
bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors
```

### Secondary Button
```
bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg font-medium transition-colors
```

### Ghost Button
```
hover:bg-slate-100 text-slate-600 px-4 py-2 rounded-lg font-medium transition-colors
```

### Input Field
```
w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all
```

### Section Header
```
text-slate-900 text-xl font-semibold mb-4
```

### Body Text
```
text-slate-600 text-base leading-relaxed
```

### Label
```
text-slate-500 text-sm font-medium
```

### Status Badge (Success)
```
inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800
```

### Status Badge (Warning)
```
inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800
```

### Status Badge (Error)
```
inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800
```
