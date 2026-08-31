import { useColorMode } from '@vueuse/core'

export function useDarkMode() {
  const mode = useColorMode({
    attribute: 'class',
    modes: {
      light: 'light',
      dark: 'dark',
    },
  })

  function toggleTheme() {
    mode.value = mode.value === 'light' ? 'dark' : 'light'
  }

  return {
    mode,
    toggleTheme,
  }
}
