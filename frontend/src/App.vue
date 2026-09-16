<script setup lang="ts">
import 'vue-sonner/style.css'

import { Toaster } from '@/components/ui/sonner'

// 根组件只渲染路由出口；应用布局由路由根组件 AppLayout 提供。
</script>

<template>
  <RouterView />
  <Toaster position="top-right" rich-colors :duration="2500" />
</template>
