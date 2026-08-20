/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        // 语义令牌（诊断书 P0-01）：深色模式仅切换 index.css 里的变量值
        primary: "var(--c-primary)",
        deep: "var(--c-primary-deep)",
        surface: { DEFAULT: "var(--c-surface)", 2: "var(--c-surface-2)" },
        // 用到的色阶重映射为变量，使既有工具类整体随主题切换
        slate: {
          50: "var(--slate-50)", 100: "var(--slate-100)", 200: "var(--slate-200)",
          300: "var(--slate-300)", 400: "var(--slate-400)", 500: "var(--slate-500)",
          600: "var(--slate-600)", 700: "var(--slate-700)", 800: "var(--slate-800)",
          900: "var(--slate-900)",
        },
        sky: {
          50: "var(--sky-50)", 100: "var(--sky-100)", 200: "var(--sky-200)",
          300: "var(--sky-300)", 400: "var(--sky-400)", 500: "var(--sky-500)",
          600: "var(--sky-600)", 700: "var(--sky-700)",
        },
        emerald: {
          50: "var(--emerald-50)", 100: "var(--emerald-100)", 200: "var(--emerald-200)",
          500: "var(--emerald-500)", 600: "var(--emerald-600)", 700: "var(--emerald-700)",
        },
        green: {
          50: "var(--emerald-50)", 200: "var(--emerald-200)", 700: "var(--emerald-700)",
        },
        red: {
          50: "var(--red-50)", 100: "var(--red-100)", 200: "var(--red-200)",
          400: "var(--red-400)", 500: "var(--red-500)", 600: "var(--red-600)",
          700: "var(--red-700)",
        },
        amber: {
          50: "var(--amber-50)", 100: "var(--amber-100)", 200: "var(--amber-200)",
          300: "var(--amber-300)", 400: "var(--amber-400)", 500: "var(--amber-500)",
          600: "var(--amber-600)", 700: "var(--amber-700)", 800: "var(--amber-800)",
          900: "var(--amber-900)",
        },
        blue: {
          50: "var(--blue-50)", 100: "var(--blue-100)", 600: "var(--blue-600)",
          700: "var(--blue-700)",
        },
        zinc: {
          50: "var(--zinc-50)", 100: "var(--zinc-100)", 200: "var(--zinc-200)",
          400: "var(--zinc-400)", 600: "var(--zinc-600)", 700: "var(--zinc-700)",
        },
        violet: {
          50: "var(--violet-50)", 100: "var(--violet-100)", 600: "var(--violet-600)",
          700: "var(--violet-700)",
        },
      },
    },
  },
  plugins: [],
};
