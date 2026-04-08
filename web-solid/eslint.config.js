import js from '@eslint/js'
import solid from 'eslint-plugin-solid/configs/recommended.js'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 2020,
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    ...solid,
    rules: {
      ...solid.rules,
      'solid/reactivity': 'error',
      'solid/no-destructure': 'error',
      'solid/jsx-no-undef': 'error',
    },
  },
])
