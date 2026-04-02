# VibeMind Space Theme

A modern, dark "Space" design system for React/Vite applications with Purple/Violet as the dominant accent color.

## Trigger Events
- `PROJECT_SCAFFOLDED` - Apply theme to new projects
- `GENERATION_COMPLETE` - Ensure theme consistency
- `UX_ISSUE_FOUND` - Fix styling issues with theme

## Design Vision
- **Dark Mode** as default
- **Purple/Violet** (#a855f7) as dominant accent
- Cosmic Nebula-Gradient backgrounds
- Glassmorphism & Blur effects
- Animated gradients & glow effects
- Modern, futuristic aesthetic

<!-- END_TIER_MINIMAL -->

## Color Palette (CSS Variables)

```css
:root {
  /* Space Background */
  --bg-space-dark: #0a0a0f;
  --bg-space-mid: #12121a;
  --bg-space-light: #1a1a2e;
  --bg-card: rgba(20, 20, 35, 0.8);
  --bg-card-hover: rgba(30, 30, 50, 0.9);
  --bg-card-solid: #14141f;

  /* Neon Accents - Purple Dominant */
  --neon-purple: #a855f7;
  --neon-purple-dim: #7c3aed;
  --neon-cyan: #22d3ee;
  --neon-pink: #ec4899;
  --neon-blue: #3b82f6;

  /* Gradients */
  --gradient-cosmic: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #a855f7 100%);
  --gradient-aurora: linear-gradient(135deg, #22d3ee 0%, #a855f7 100%);
  --gradient-nebula: linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 50%, #0a0a0f 100%);
  --gradient-glow: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

  /* Text */
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --text-dim: #475569;

  /* Status Colors */
  --status-success: #22c55e;
  --status-success-bg: rgba(34, 197, 94, 0.15);
  --status-warning: #f59e0b;
  --status-warning-bg: rgba(245, 158, 11, 0.15);
  --status-error: #ef4444;
  --status-error-bg: rgba(239, 68, 68, 0.15);
  --status-info: #3b82f6;
  --status-info-bg: rgba(59, 130, 246, 0.15);

  /* Glassmorphism */
  --glass-bg: rgba(255, 255, 255, 0.05);
  --glass-border: rgba(255, 255, 255, 0.1);
  --glass-border-hover: rgba(168, 85, 247, 0.3);

  /* Shadows */
  --shadow-glow: 0 0 20px rgba(168, 85, 247, 0.3);
  --shadow-glow-strong: 0 0 30px rgba(168, 85, 247, 0.5);
  --shadow-card: 0 8px 32px rgba(0, 0, 0, 0.4);

  /* Transitions */
  --transition-fast: 0.2s ease;
  --transition-normal: 0.3s ease;
  --transition-slow: 0.5s ease;

  /* Border Radius */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
}
```

## Tailwind Configuration

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        space: {
          dark: '#0a0a0f',
          mid: '#12121a',
          light: '#1a1a2e',
        },
        neon: {
          purple: '#a855f7',
          'purple-dim': '#7c3aed',
          cyan: '#22d3ee',
          pink: '#ec4899',
          blue: '#3b82f6',
        },
        glass: {
          bg: 'rgba(255, 255, 255, 0.05)',
          border: 'rgba(255, 255, 255, 0.1)',
        },
      },
      backgroundImage: {
        'gradient-cosmic': 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #a855f7 100%)',
        'gradient-aurora': 'linear-gradient(135deg, #22d3ee 0%, #a855f7 100%)',
        'gradient-nebula': 'linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 50%, #0a0a0f 100%)',
      },
      boxShadow: {
        'glow': '0 0 20px rgba(168, 85, 247, 0.3)',
        'glow-strong': '0 0 30px rgba(168, 85, 247, 0.5)',
        'card': '0 8px 32px rgba(0, 0, 0, 0.4)',
      },
      animation: {
        'shimmer': 'shimmer 2s linear infinite',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'fade-in': 'fadeIn 0.5s ease forwards',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 5px currentColor' },
          '50%': { boxShadow: '0 0 20px currentColor, 0 0 30px currentColor' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
```

<!-- END_TIER_STANDARD -->

## Component Patterns

### Card (Glassmorphism)
```tsx
<div className="bg-space-mid/80 backdrop-blur-xl border border-glass-border rounded-xl p-6 shadow-card hover:border-neon-purple/30 hover:shadow-glow transition-all duration-300">
  <h3 className="text-lg font-semibold text-white mb-2">Card Title</h3>
  <p className="text-slate-400">Card content with glass effect</p>
</div>
```

### Button (Primary)
```tsx
<button className="bg-gradient-cosmic px-6 py-3 rounded-lg font-semibold text-white shadow-glow hover:shadow-glow-strong transition-all duration-300 hover:scale-105">
  Primary Action
</button>
```

### Button (Secondary/Ghost)
```tsx
<button className="bg-transparent border border-glass-border px-6 py-3 rounded-lg font-medium text-slate-300 hover:border-neon-purple hover:text-neon-purple hover:shadow-glow transition-all duration-300">
  Secondary Action
</button>
```

### Input Field
```tsx
<input
  type="text"
  className="w-full bg-space-dark/50 border border-glass-border rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:border-neon-purple focus:ring-2 focus:ring-neon-purple/20 focus:outline-none transition-all"
  placeholder="Enter text..."
/>
```

### Navigation (Glassmorphism)
```tsx
<nav className="bg-space-dark/80 backdrop-blur-xl border-b border-glass-border sticky top-0 z-50">
  <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
    <h1 className="text-xl font-bold bg-gradient-cosmic bg-clip-text text-transparent">
      VibeMind
    </h1>
    <div className="flex gap-4">
      <a href="#" className="text-slate-400 hover:text-neon-purple transition-colors">Link</a>
    </div>
  </div>
</nav>
```

### Progress Bar (Animated)
```tsx
<div className="h-2 bg-space-dark rounded-full overflow-hidden">
  <div
    className="h-full bg-gradient-aurora animate-shimmer bg-[length:200%_100%] rounded-full shadow-[0_0_10px_rgba(168,85,247,0.5)]"
    style={{ width: '75%' }}
  />
</div>
```

### Status Badge
```tsx
// Success
<span className="px-3 py-1 rounded-full text-sm font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
  Active
</span>

// Warning
<span className="px-3 py-1 rounded-full text-sm font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
  Pending
</span>

// Error
<span className="px-3 py-1 rounded-full text-sm font-medium bg-red-500/15 text-red-400 border border-red-500/30">
  Error
</span>
```

### Table
```tsx
<div className="bg-space-mid/80 backdrop-blur-xl border border-glass-border rounded-xl overflow-hidden">
  <table className="w-full">
    <thead className="bg-space-dark/50">
      <tr>
        <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">Name</th>
        <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">Status</th>
      </tr>
    </thead>
    <tbody className="divide-y divide-glass-border">
      <tr className="hover:bg-space-light/30 transition-colors">
        <td className="px-6 py-4 text-white">Item</td>
        <td className="px-6 py-4">
          <span className="text-emerald-400">Active</span>
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

### Modal
```tsx
<div className="fixed inset-0 bg-space-dark/80 backdrop-blur-sm flex items-center justify-center z-50">
  <div className="bg-space-mid border border-glass-border rounded-2xl p-8 max-w-md w-full mx-4 shadow-2xl animate-fade-in">
    <h2 className="text-2xl font-bold text-white mb-4">Modal Title</h2>
    <p className="text-slate-400 mb-6">Modal content goes here.</p>
    <div className="flex gap-3 justify-end">
      <button className="px-4 py-2 rounded-lg text-slate-400 hover:text-white transition-colors">
        Cancel
      </button>
      <button className="bg-gradient-cosmic px-4 py-2 rounded-lg font-medium text-white">
        Confirm
      </button>
    </div>
  </div>
</div>
```

## Global CSS Template

```css
/* VibeMind Space Theme - Global Styles */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* CSS Variables defined above */
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    background: var(--gradient-nebula);
    background-attachment: fixed;
    color: var(--text-primary);
    min-height: 100vh;
  }

  /* Scrollbar Styling */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: var(--bg-space-dark);
  }

  ::-webkit-scrollbar-thumb {
    background: var(--neon-purple-dim);
    border-radius: 4px;
  }

  ::-webkit-scrollbar-thumb:hover {
    background: var(--neon-purple);
  }

  /* Selection */
  ::selection {
    background: rgba(168, 85, 247, 0.3);
    color: var(--text-primary);
  }
}

@layer components {
  .glass-card {
    @apply bg-space-mid/80 backdrop-blur-xl border border-glass-border rounded-xl shadow-card;
  }

  .glass-card-hover {
    @apply hover:border-neon-purple/30 hover:shadow-glow transition-all duration-300;
  }

  .btn-primary {
    @apply bg-gradient-cosmic px-6 py-3 rounded-lg font-semibold text-white shadow-glow hover:shadow-glow-strong transition-all duration-300 hover:scale-105;
  }

  .btn-secondary {
    @apply bg-transparent border border-glass-border px-6 py-3 rounded-lg font-medium text-slate-300 hover:border-neon-purple hover:text-neon-purple hover:shadow-glow transition-all duration-300;
  }

  .input-field {
    @apply w-full bg-space-dark/50 border border-glass-border rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:border-neon-purple focus:ring-2 focus:ring-neon-purple/20 focus:outline-none transition-all;
  }

  .text-glow {
    text-shadow: 0 0 10px rgba(168, 85, 247, 0.5);
  }

  .border-glow {
    box-shadow: var(--shadow-glow);
  }
}

@layer utilities {
  .animate-shimmer {
    animation: shimmer 2s linear infinite;
  }

  .animate-pulse-glow {
    animation: pulse-glow 2s ease-in-out infinite;
  }
}
```

## Usage Notes

1. **Always use dark backgrounds** - Never use white or light backgrounds
2. **Purple is primary accent** - Use `neon-purple` for primary actions and focus states
3. **Glassmorphism for cards** - Use `backdrop-blur` with semi-transparent backgrounds
4. **Glow effects on hover** - Add `shadow-glow` on interactive elements
5. **Gradient text for headings** - Use `bg-gradient-cosmic bg-clip-text text-transparent`
6. **Status colors** - Use emerald/amber/red with 15% opacity backgrounds
