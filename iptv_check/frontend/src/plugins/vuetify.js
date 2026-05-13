import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import zhHans from 'vuetify/locale/zh-Hans'

const theme = {
  colors: {
    primary: '#1976D2',
    secondary: '#424242',
    accent: '#82B1FF',
    error: '#FF5252',
    success: '#4CAF50',
    warning: '#FB8C00',
    info: '#2196F3',
    background: '#F5F5F5',
    surface: '#FFFFFF',
  },
}

export default createVuetify({
  components,
  directives,
  locale: { locale: 'zhHans', messages: { zhHans } },
  theme: {
    defaultTheme: 'light',
    themes: { light: theme },
  },
})
