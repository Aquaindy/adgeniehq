/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand
        grape: {
          DEFAULT: "#3E2F84", // Grape Jelly — primary
          50: "#F4F1FB",
          100: "#EEEAFE", // Soft Lavender
          200: "#D9CFF6",
          300: "#B6A3EA",
          400: "#8C72D9",
          500: "#6244C2",
          600: "#4E36A3",
          700: "#3E2F84", // Grape Jelly
          800: "#312468",
          900: "#241A4D",
        },
        violet: {
          electric: "#7C3AED",
        },
        // Semantic
        ink: "#111827", // Deep Night
        cloud: "#F9FAFB",
        slate: {
          text: "#334155",
        },
        success: "#16A34A", // Growth Green
        warning: "#F59E0B", // Warning Amber
        danger: "#DC2626", // Danger Red
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(17,24,39,0.04), 0 4px 16px rgba(17,24,39,0.06)",
        elevate: "0 8px 24px rgba(62,47,132,0.12)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      backgroundImage: {
        "grape-gradient":
          "linear-gradient(135deg, #3E2F84 0%, #6244C2 50%, #7C3AED 100%)",
        "grape-soft":
          "linear-gradient(135deg, #EEEAFE 0%, #F4F1FB 100%)",
      },
    },
  },
  plugins: [],
};
