<template>
  <div v-if="viewMode === 'grouped'" class="space-y-2">
    <div
      v-for="i in 5"
      :key="i"
      class="rounded-lg border p-3 space-y-3"
    >
      <div class="flex items-center gap-3">
        <div class="flex-1 space-y-2">
          <div class="h-4 w-32 bg-muted rounded animate-pulse" />
          <div class="h-3 w-24 bg-muted rounded animate-pulse" />
        </div>
        <div class="flex gap-1">
          <div class="h-8 w-8 bg-muted rounded animate-pulse" />
          <div class="h-8 w-8 bg-muted rounded animate-pulse" />
          <div class="h-8 w-8 bg-muted rounded animate-pulse" />
        </div>
      </div>
    </div>
  </div>
  <div v-else class="rounded-lg border overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b bg-muted/50">
          <th class="h-10 px-3 w-16" />
          <th class="h-10 px-3" />
          <th class="h-10 px-3 hidden md:table-cell" />
          <th class="h-10 px-3 w-20" />
          <th class="h-10 px-3 w-24" />
          <th class="h-10 px-3 w-24 hidden sm:table-cell" />
          <th class="h-10 px-3 w-16" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in 5" :key="i" class="border-b">
          <td class="px-3 py-2.5"><div class="h-3 w-6 bg-muted rounded animate-pulse" /></td>
          <td class="px-3 py-2.5">
            <div class="h-4 w-24 bg-muted rounded animate-pulse mb-1" />
            <div class="h-3 w-48 bg-muted rounded animate-pulse" />
          </td>
          <td class="px-3 py-2.5 hidden md:table-cell"><div class="h-4 w-16 bg-muted rounded animate-pulse" /></td>
          <td class="px-3 py-2.5 text-center"><div class="h-4 w-10 bg-muted rounded animate-pulse inline-block" /></td>
          <td class="px-3 py-2.5 text-center"><div class="h-4 w-12 bg-muted rounded animate-pulse inline-block" /></td>
          <td class="px-3 py-2.5 text-center hidden sm:table-cell"><div class="h-4 w-12 bg-muted rounded animate-pulse inline-block" /></td>
          <td class="px-3 py-2.5 text-center">
            <div class="flex items-center justify-center gap-1">
              <div class="h-8 w-8 bg-muted rounded animate-pulse" />
              <div class="h-8 w-8 bg-muted rounded animate-pulse" />
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  viewMode: { type: String, default: 'grouped' },
})
</script>
