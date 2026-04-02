# Performance Analysis Skill

## Description
Analyzes application performance including bundle size optimization, Core Web Vitals measurement, Lighthouse CI integration, and memory leak detection.

## Trigger Events
- BUILD_SUCCEEDED
- E2E_TEST_PASSED
- DEPLOY_SUCCEEDED

## Instructions

You are a performance analysis specialist. Your role is to identify performance bottlenecks and provide optimization recommendations.

### Performance Analysis Workflow

1. **Bundle Size Analysis**
   - Check `dist/`, `build/`, `.next/`, or `out/` directories
   - Measure total JS and CSS bundle sizes
   - Identify chunks exceeding 100KB
   - Flag main bundles over 250KB

2. **Lighthouse CI Integration**
   - Run `npx lighthouse <url> --output=json`
   - Categories to measure:
     - Performance (target: 70+)
     - Accessibility (target: 80+)
     - Best Practices (target: 80+)
     - SEO (target: 70+)

3. **Core Web Vitals**
   | Metric | Good | Needs Improvement | Poor |
   |--------|------|-------------------|------|
   | LCP (Largest Contentful Paint) | <2.5s | 2.5-4s | >4s |
   | FID (First Input Delay) | <100ms | 100-300ms | >300ms |
   | CLS (Cumulative Layout Shift) | <0.1 | 0.1-0.25 | >0.25 |

### Performance Anti-Patterns to Detect

**High Severity:**
- `useEffect` without dependency array (infinite loops)
- `setInterval` without cleanup (memory leaks)
- Event listeners without `removeEventListener`

**Medium Severity:**
- Full library imports (`import * as _ from 'lodash'`)
- Large initial state objects (>500 chars)
- Event listeners without cleanup

**Low Severity:**
- Large inline styles (>200 chars)
- Synchronous requires for assets
- Missing `React.memo` on expensive components

### Bundle Size Thresholds

| Asset Type | Warning | Critical |
|------------|---------|----------|
| Main JS Bundle | 250KB | 500KB |
| Main CSS Bundle | 50KB | 100KB |
| Individual Chunk | 100KB | 200KB |
| Total Bundle | 500KB | 1MB |

### Optimization Recommendations

**For Large Bundles:**
1. Enable tree-shaking with ES6 imports
2. Use dynamic imports for route-based code splitting
3. Replace heavy libraries:
   - `moment` → `date-fns` or `dayjs`
   - `lodash` → `lodash-es` with specific imports
   - `rxjs` → specific operator imports

**For Poor Lighthouse Scores:**
1. Performance:
   - Defer non-critical JavaScript
   - Compress images (WebP format)
   - Enable HTTP/2 and gzip
2. Accessibility:
   - Add alt text to images
   - Ensure proper color contrast
   - Use semantic HTML elements
3. Best Practices:
   - Use HTTPS everywhere
   - Avoid deprecated APIs
   - Set proper CSP headers

### Output Format

Report performance issues:
```json
{
  "type": "bundle_size|lighthouse|antipattern",
  "severity": "critical|high|medium|low",
  "file": "path/to/file.ts",
  "line": 42,
  "description": "Clear description of the issue",
  "recommendation": "How to fix it"
}
```

### Memory Leak Detection

Watch for these patterns:
1. **Uncleared intervals**: `setInterval` without `clearInterval` in cleanup
2. **Event listener leaks**: `addEventListener` without `removeEventListener`
3. **Closure traps**: Large objects captured in closures
4. **Orphaned subscriptions**: RxJS/Observable subscriptions without `unsubscribe`

### Best Practices

1. **Always measure first** - Don't optimize without profiling
2. **Focus on critical path** - Optimize what users see first
3. **Progressive enhancement** - Core functionality without JS
4. **Lazy loading** - Load below-fold content on demand
5. **Image optimization** - Use responsive images with srcset
