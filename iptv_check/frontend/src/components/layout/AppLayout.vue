<template>
  <div class="flex h-screen flex-col bg-background">
    <AppHeader />
    <main class="flex-1 overflow-auto p-4 lg:p-6 pb-20 lg:pb-6">
      <slot />
    </main>
  </div>
</template>

<script setup>
import AppHeader from './AppHeader.vue'
</script>
