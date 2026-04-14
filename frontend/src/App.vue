<template>
  <router-view />
</template>

<script setup>
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem('chainrisk-theme')
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  const theme = stored || (prefersDark ? 'dark' : 'light')
  document.documentElement.setAttribute('data-theme', theme)
}
</script>

<style>
/* Global reset */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --bg: #f6f7f9;
  --bg-elev: #ffffff;
  --bg-soft: #f1f3f5;
  --text: #0f1419;
  --muted: #667085;
  --border: #d9dde3;
  --nav-bg: #0b0b0b;
  --nav-text: #f8fafc;
  --accent: #7c3aed;
}

:root[data-theme='dark'] {
  --bg: #07090d;
  --bg-elev: #0f1318;
  --bg-soft: #161b22;
  --text: #e6ebf2;
  --muted: #9aa7b7;
  --border: #27303b;
  --nav-bg: #000000;
  --nav-text: #f8fafc;
  --accent: #9f67ff;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--text);
  background-color: var(--bg);
}

/* Scrollbars */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-soft);
}

::-webkit-scrollbar-thumb {
  background: var(--border);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}

/* Buttons inherit font */
button {
  font-family: inherit;
}
</style>
