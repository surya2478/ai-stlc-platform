/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // The reference palette, verbatim. Raw hex rather than hsl(var(--x))
        // because these are fixed brand values: they do not flip with the
        // theme the way the semantic tokens above do.
        app: {
          brand: {
            950: "#4D0507",
            900: "#65080A",
            800: "#7A0B0D",
            700: "#941216",
            600: "#B71920",
            500: "#D52B31",
            300: "#F1A4A6",
            200: "#F6D4D5",
            100: "#FDEBEC",
            75: "#FFF5F5",
            50: "#FFF8F8",
          },
          sidebar: {
            DEFAULT: "#65080A",
            top: "#7A0B0D",
            bottom: "#4D0507",
            hover: "rgba(255,255,255,0.08)",
            active: "#B71920",
            text: "#FFFFFF",
            muted: "rgba(255,255,255,0.62)",
            border: "rgba(255,255,255,0.08)",
          },
          canvas: "#F8F9FB",
          surface: "#FFFFFF",
          "surface-subtle": "#FCFCFD",
          "surface-muted": "#F4F5F7",
          border: "#E8EAEE",
          "border-soft": "#F1D4D4",
          strong: "#E6B4B4",
          primary: "#1F2937",
          secondary: "#6B7280",
          muted: "#9CA3AF",
          success: "#15803D",
          "success-bg": "#EAF7EF",
          warning: "#D97706",
          "warning-bg": "#FFF4E5",
          danger: "#DC2626",
          "danger-bg": "#FEEBEC",
          info: "#2563EB",
          "info-bg": "#EFF6FF",
        },
      },
      // `border-app` as the reference spells it, so its markup ports verbatim.
      borderColor: {
        app: "#E8EAEE",
      },
      boxShadow: {
        "app-card": "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
        "app-card-lg":
          "0 8px 24px -12px rgba(16,24,40,0.12), 0 4px 12px -6px rgba(16,24,40,0.08)",
        "app-sidebar": "2px 0 16px -8px rgba(77, 5, 7, 0.35)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        "app-sm": "8px",
        app: "12px",
        "app-lg": "16px",
        "app-xl": "20px",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
