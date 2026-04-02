import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "desktop-agent/**",
      "electron-app/**",
      "moire_server/**",
      "backend/**",
      "supabase/**",
      "playwright-report/**",
      "test-results/**",
      "node_modules/**",
      "scripts/**",
      "docker/**",
      "tests/**",
      "**/*.d.ts",
      "tailwind.config.ts",
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // === REACT HOOKS ===
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],

      // === TYPESCRIPT STRICT RULES (Phase 1: Warnings) ===
      // TODO: Nach Behebung der Probleme auf "error" setzen
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-unused-expressions": [
        "warn",
        {
          allowShortCircuit: true,
          allowTernary: true,
          allowTaggedTemplates: true,
        },
      ],
      "@typescript-eslint/no-explicit-any": "warn", // AKTIVIERT: Warnt bei any-Typen
      "@typescript-eslint/explicit-function-return-type": "off", // Später aktivieren
      "@typescript-eslint/no-non-null-assertion": "warn", // Warnt bei ! operator

      // === BEST PRACTICES ===
      "no-console": ["warn", { allow: ["warn", "error"] }], // AKTIVIERT: Warnt bei console.log
      "prefer-const": "warn",
      "no-var": "error",
      eqeqeq: ["warn", "always"], // AKTIVIERT: === statt ==
      curly: ["warn", "all"], // AKTIVIERT: Immer geschweifte Klammern

      // === CODE QUALITY ===
      "no-duplicate-imports": "error",
      "no-template-curly-in-string": "warn",
      "no-unreachable": "error",
      "no-constant-condition": "warn",
    },
  },
);
