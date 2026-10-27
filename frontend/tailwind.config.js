/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#05080c",
          900: "#080d13",
          850: "#0b121a",
          800: "#0e1721",
          750: "#12202c",
          700: "#162633",
        },
        line: {
          DEFAULT: "#1b2a38",
          soft: "#15212c",
        },
        mint: {
          DEFAULT: "#38e3ab",
          dim: "#1f8f6e",
        },
        amber: {
          DEFAULT: "#f5b84c",
          dim: "#8a6420",
        },
        coral: {
          DEFAULT: "#ff7272",
          dim: "#8f3a3a",
        },
        sky: {
          DEFAULT: "#72a9ff",
          dim: "#315a91",
        },
        fog: "#8b9dae",
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
        mono: ["ui-monospace", "Cascadia Code", "Consolas", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.03) inset, 0 18px 40px -32px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(56,227,171,0.25), 0 0 28px -8px rgba(56,227,171,0.35)",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.35", transform: "scale(0.8)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(220%)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 2.4s ease-in-out infinite",
        "fade-up": "fade-up 0.35s ease-out both",
        sweep: "sweep 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};