import { useColorMode, useCycleList } from '@vueuse/core'

export function useDarkMode() {
  const mode = useColorMode({
    attribute: 'class',
    modes: {
      light: 'light',
      dark: 'dark',
      auto: 'auto',
    },
    emitAuto: true,
  })

  const { next } = useCycleList(['light', 'dark', 'auto'])

  function toggleTheme() {
    mode.value = next()
  }

  return {
    mode,
    toggleTheme,
  }
}
