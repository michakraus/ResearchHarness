<script setup lang="ts">
// The edit link of the home page. VitePress's home layout shows no doc footer, so the page draws
// the link itself, from the `editLink` pattern of config.mts.
import { computed } from 'vue'
import { useData } from 'vitepress'

const { theme, page } = useData()
const url = computed(() => theme.value.editLink.pattern.replace(/:path/g, page.value.relativePath))
</script>

<template>
  <p class="home-edit-link">
    <a :href="url" target="_blank" rel="noreferrer"><span class="vpi-square-pen home-edit-icon" />Edit this page on GitHub</a>
  </p>
</template>

<style scoped>
.home-edit-link {
  margin-top: 48px;
  font-size: 14px;
}

.home-edit-link a {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--vp-c-brand-1);
  font-weight: 500;
  text-decoration: none;
}

.home-edit-icon {
  width: 14px;
  height: 14px;
}
</style>
