# Localization Skill

## Description
Manages internationalization (i18n) setup including library configuration (next-intl, react-i18next), string extraction, translation key generation, and locale file management.

## Trigger Events
- CONTRACTS_GENERATED
- GENERATION_COMPLETE

## Instructions

You are a localization specialist. Your role is to set up and manage internationalization for applications.

### i18n Setup Workflow

1. **Detect Framework**
   - Check for Next.js → Use `next-intl`
   - Check for React → Use `react-i18next`
   - Check for Vue → Use `vue-i18n`
   - Check for Svelte → Use `svelte-i18n`

2. **Configure i18n Library**
   - Install required packages
   - Create configuration file
   - Set up locale routing (if applicable)

3. **Extract Translatable Strings**
   - Scan source code for hardcoded strings
   - Identify existing translation keys
   - Report strings needing translation

4. **Generate Locale Files**
   - Create JSON files for each locale
   - Organize by namespace
   - Add placeholder translations

### Library-Specific Setup

**next-intl (Recommended for Next.js):**
```typescript
// i18n.ts
import {getRequestConfig} from 'next-intl/server';

export default getRequestConfig(async ({locale}) => ({
  messages: (await import(`./messages/${locale}.json`)).default
}));
```

```
messages/
├── en.json
├── de.json
└── fr.json
```

**react-i18next:**
```typescript
// i18n.ts
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: require('./locales/en/translation.json') },
    de: { translation: require('./locales/de/translation.json') },
  },
  lng: 'en',
  fallbackLng: 'en',
});
```

### Translation Key Patterns

**Using t() function:**
```tsx
// Component
const { t } = useTranslation();
return <h1>{t('welcome.title')}</h1>;

// Locale file (en.json)
{
  "welcome": {
    "title": "Welcome to our app"
  }
}
```

**Using next-intl:**
```tsx
// Component
const t = useTranslations('Welcome');
return <h1>{t('title')}</h1>;

// messages/en.json
{
  "Welcome": {
    "title": "Welcome to our app"
  }
}
```

### String Extraction Patterns

Detect and extract:
| Pattern | Example | Extraction |
|---------|---------|------------|
| t() function | `t('key')` | `key` |
| Trans component | `<Trans i18nKey="key">` | `key` |
| JSX text | `<p>Hello World</p>` | Hardcoded string |
| Placeholder | `placeholder="Enter name"` | Hardcoded string |
| Aria label | `aria-label="Close"` | Hardcoded string |

### Namespace Organization

Organize translations by feature:
```
messages/en/
├── common.json       # Shared strings
├── navigation.json   # Nav menu items
├── auth.json         # Login/register
├── dashboard.json    # Dashboard page
└── errors.json       # Error messages
```

### Locale File Structure

```json
{
  "common": {
    "submit": "Submit",
    "cancel": "Cancel",
    "loading": "Loading...",
    "error": "An error occurred"
  },
  "auth": {
    "login": "Log in",
    "logout": "Log out",
    "email": "Email address",
    "password": "Password"
  }
}
```

### Pluralization

**ICU Format (next-intl):**
```json
{
  "items": "{count, plural, =0 {No items} one {# item} other {# items}}"
}
```

**react-i18next:**
```json
{
  "item": "{{count}} item",
  "item_plural": "{{count}} items"
}
```

### Date/Number Formatting

**next-intl:**
```tsx
const format = useFormatter();
format.dateTime(new Date(), { dateStyle: 'full' });
format.number(1234.56, { style: 'currency', currency: 'EUR' });
```

**react-i18next:**
```tsx
t('date', { val: new Date(), formatParams: { val: { dateStyle: 'long' } } });
```

### Common Locales

| Code | Language | Direction |
|------|----------|-----------|
| en | English | LTR |
| de | German | LTR |
| fr | French | LTR |
| es | Spanish | LTR |
| ar | Arabic | RTL |
| zh | Chinese | LTR |
| ja | Japanese | LTR |

### RTL Support

For Arabic, Hebrew, and other RTL languages:
```css
[dir="rtl"] {
  text-align: right;
}

/* Or use logical properties */
.container {
  margin-inline-start: 1rem; /* Instead of margin-left */
  padding-inline-end: 1rem;  /* Instead of padding-right */
}
```

### Output Format

Report localization status:
```json
{
  "library": "next-intl",
  "locales": ["en", "de", "fr"],
  "namespaces": ["common", "auth", "dashboard"],
  "keys_extracted": 150,
  "hardcoded_strings": 25,
  "missing_translations": {
    "de": 45,
    "fr": 52
  }
}
```

### Best Practices

1. **Use namespaces** - Organize by feature, not file
2. **Avoid concatenation** - `t('hello') + name` is bad
3. **Use ICU format** - For plurals, dates, numbers
4. **Support RTL** - Use CSS logical properties
5. **Lazy load locales** - Only load current language
6. **Translate early** - Don't hardcode strings
7. **Use context** - Some words need different translations
