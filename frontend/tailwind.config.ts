import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "engine-bg": "#0a0a0f",
        "engine-surface": "#12121a",
        "engine-border": "#1e1e2e",
        "engine-accent": "#6C63FF",
        "engine-teal": "#00D4AA",
        "engine-text": "#E8E8F0",
        "engine-muted": "#6B6B80",
        "engine-danger": "#FF4757",
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(108, 99, 255, 0.4)" },
          "50%": { boxShadow: "0 0 0 8px rgba(108, 99, 255, 0)" },
        },
        typing: {
          "0%, 100%": { transform: "translateY(0)", opacity: "0.35" },
          "50%": { transform: "translateY(-4px)", opacity: "1" },
        },
      },
      animation: {
        "pulse-glow": "pulse-glow 2.4s ease-in-out infinite",
        typing: "typing 1.1s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
