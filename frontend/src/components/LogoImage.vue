<template>
  <div ref="containerRef" class="inline-flex items-center justify-center" :class="containerClass">
    <img
      v-if="logoSrc && !loadError"
      :src="logoSrc"
      :alt="channelName"
      class="object-contain"
      :style="{ width: `${size}px`, height: `${size}px`, maxWidth: `${size}px` }"
      @error="onError"
    />
    <div
      v-else
      class="flex items-center justify-center rounded bg-muted text-muted-foreground font-medium"
      :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.max(size / 3, 10)}px` }"
    >
      {{ fallbackText }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getLogo } from '../api'

const props = defineProps({
  channelName: { type: String, default: '' },
  tvgLogo: { type: String, default: '' },
  sourceId: { type: String, default: '' },
  size: { type: Number, default: 32 },
  containerClass: { type: String, default: '' },
})

const containerRef = ref(null)
const logoSrc = ref('')
const loadError = ref(false)
const isVisible = ref(false)
let observer = null

const fallbackText = computed(() => {
  const name = props.channelName
  if (!name) return '?'
  return name.charAt(0).toUpperCase()
})

function onError() {
  loadError.value = true
}

const _pendingRequests = new Map()
const _requestTimers = new Map()

async function loadLogo() {
  if (!isVisible.value) return
  loadError.value = false
  if (props.tvgLogo) {
    logoSrc.value = props.tvgLogo
    return
  }
  if (!props.channelName) return

  const key = props.channelName
  if (_pendingRequests.has(key)) {
    const { data } = await _pendingRequests.get(key)
    if (data && data.size > 0) {
      logoSrc.value = URL.createObjectURL(data)
    }
    return
  }

  const promise = getLogo(props.channelName, { tvg_logo: props.tvgLogo, source_id: props.sourceId })
  _pendingRequests.set(key, promise)
  try {
    const { data } = await promise
    if (data && data.size > 0) {
      logoSrc.value = URL.createObjectURL(data)
    }
  } catch {
    loadError.value = true
  } finally {
    _pendingRequests.delete(key)
  }
}

function setupObserver() {
  if (!containerRef.value) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) {
        isVisible.value = true
        loadLogo()
        observer?.disconnect()
      }
    },
    { rootMargin: '200px' }
  )
  observer.observe(containerRef.value)
}

watch(() => [props.channelName, props.tvgLogo], () => {
  if (isVisible.value) loadLogo()
})

onMounted(() => {
  if (props.tvgLogo) {
    logoSrc.value = props.tvgLogo
    isVisible.value = true
    return
  }
  setupObserver()
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>
