<script setup lang="ts">
import 'vue-sonner/style.css'

import { Toaster } from '@/components/ui/sonner'

// 根组件只渲染路由出口；应用布局由路由根组件 AppLayout 提供。
</script>

<template>
  <RouterView />
  <!-- 右下角弹出：避免遮挡顶部栏的紧急停机按钮与 CAN 状态 -->
  <Toaster position="bottom-right" rich-colors :duration="2500" />
</template>
