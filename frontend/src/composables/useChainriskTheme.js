import { computed, ref } from 'vue'

const theme = ref(document.documentElement.getAttribute('data-theme') || 'light')

export function useChainriskTheme() {
  const themeLabel = computed(() => (theme.value === 'dark' ? 'Light' : 'Dark'))

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', theme.value)
    localStorage.setItem('chainrisk-theme', theme.value)
  }

  return { theme, themeLabel, toggleTheme }
}
