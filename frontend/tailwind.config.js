/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // One source of truth: the CSS variables in src/index.css (light and dark palettes).
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        alt: 'var(--alt)',
        line: 'var(--line)',
        fg: 'var(--fg)',
        muted: 'var(--muted)',
        accent: 'var(--accent)',
        up: 'var(--up)',
        down: 'var(--down)',
        warn: 'var(--warn)',
      },
      fontSize: {
        xs: 'var(--fs-xs)',
        sm: 'var(--fs-sm)',
        base: 'var(--fs-base)',
        lg: 'var(--fs-lg)',
        xl: 'var(--fs-xl)',
        '2xl': 'var(--fs-2xl)',
      },
    },
  },
  plugins: [],
}
