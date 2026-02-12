/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gray: {
          950: '#010810',
          900: '#020e1a',
          800: '#081631',
          700: '#162d50',
          600: '#1e4976',
          500: '#3a6a9a',
          400: '#7ba3c4',
          300: '#a8c8e0',
          200: '#cbd5e1',
          100: '#e8f0f6',
          50:  '#f8fbfd',
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
