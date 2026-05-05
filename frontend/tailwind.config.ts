import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "jarvis-bg": "#0a0a0f",
        "jarvis-surface": "#12121a",
        "jarvis-border": "#1e1e2e",
        "jarvis-accent": "#6C63FF",
        "jarvis-teal": "#00D4AA",
        "jarvis-text": "#E8E8F0",
        "jarvis-muted": "#6B6B80",
        "jarvis-danger": "#FF4757",
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
