import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import logoFavicon from '../image/logo.png'

const favicon = document.querySelector("link[rel='icon']") || document.createElement('link')
favicon.rel = 'icon'
favicon.type = 'image/png'
favicon.sizes = '384x384'
favicon.href = `${logoFavicon}?v=3`
if (!favicon.parentNode) document.head.appendChild(favicon)

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')
