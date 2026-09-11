<script setup lang="ts">
import AppSidebar from '@/components/layout/AppSidebar.vue'
import SiteHeader from '@/components/layout/SiteHeader.vue'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset>
      <SiteHeader />
      <!-- 内容区：自适应宽屏工控布局 -->
      <main class="flex flex-1 flex-col gap-4 px-4 sm:px-6 pb-6 pt-0">
        <RouterView />
      </main>
    </SidebarInset>
  </SidebarProvider>
</template>
