module.exports = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Background layers
        "aion-bg": "#0c0c10",
        "aion-raised": "#111116",
        "aion-elevated": "#17171d",
        "aion-overlay": "#1c1c24",

        // Borders
        "aion-border": "rgba(255,255,255,0.07)",
        "aion-border-subtle": "rgba(255,255,255,0.04)",
        "aion-border-strong": "rgba(255,255,255,0.12)",

        // Text
        "aion-text": "#e8e6e1",
        "aion-text-secondary": "#a09d96",
        "aion-text-muted": "#6b6862",
        "aion-text-faint": "#4a4844",

        // Accents — organic palette
        "aion-moss": "#5a7a5a",
        "aion-moss-bright": "#7aaa6a",
        "aion-mineral": "#4a7a8a",
        "aion-mineral-bright": "#6aaabb",
        "aion-violet": "#7a5a8a",
        "aion-violet-bright": "#9a7aaa",
        "aion-clay": "#8a7a4a",
        "aion-clay-bright": "#bba85a",
        "aion-rose": "#8a5a6a",
        "aion-rose-bright": "#bb7a8a",
        "aion-acid": "#7a9a5a",
        "aion-acid-bright": "#9abb6a",

        // State
        "aion-success": "#5a7a5a",
        "aion-warning": "#8a7a4a",
        "aion-error": "#8a5a5a",
      },
      fontFamily: {
        display: ["Inter", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "SF Mono", "Fira Code", "monospace"],
      },
      borderRadius: {
        aion: "6px",
      },
      transitionDuration: {
        aion: "200ms",
        "aion-slow": "350ms",
      },
    },
  },
  plugins: [],
};
