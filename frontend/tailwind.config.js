/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#F4EFE4",
          50: "#FCF9F2",
          100: "#F8F3E9",
          200: "#EDE6D8",
          300: "#E4DCCB",
        },
        surface: "#FBF8F1",
        ink: {
          DEFAULT: "#1E2724",
          950: "#18211F",
          900: "#1E2724",
          800: "#2F3A36",
          700: "#46524C",
          600: "#5F6B64",
          500: "#7A847C",
          400: "#98A299",
          300: "#C4C7BA",
        },
        line: {
          DEFAULT: "#D8CFBD",
          soft: "#E5DDCE",
          strong: "#BFB4A0",
        },
        accent: {
          DEFAULT: "#C8552B",
          dark: "#A8431F",
          soft: "#F2DCD1",
        },
        pine: {
          DEFAULT: "#1F5A4A",
          dim: "#174437",
          soft: "#DCE8E2",
        },
        ochre: {
          DEFAULT: "#A9771F",
          dim: "#7A5514",
          soft: "#F1E7CE",
        },
        brick: {
          DEFAULT: "#A33A32",
          dim: "#7C2A24",
          soft: "#F2DAD6",
        },
        steel: {
          DEFAULT: "#2E5A74",
          dim: "#22455A",
          soft: "#DCE7ED",
        },
        fog: "#6C7870",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        serif: ["Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Georgia", "serif"],
        mono: ["ui-monospace", "Cascadia Code", "Consolas", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        xl: "0.5rem",
        "2xl": "0.625rem",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(30,39,36,0.04), 0 12px 24px -20px rgba(30,39,36,0.35)",
        lift: "0 10px 30px -18px rgba(30,39,36,0.45)",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.8)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(5px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(220%)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 2.4s ease-in-out infinite",
        "fade-up": "fade-up 0.3s ease-out both",
        sweep: "sweep 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};