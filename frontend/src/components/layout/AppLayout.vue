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
      <!-- 内容区：以后只需要把页面注册到路由，就会自动渲染在这里。 -->
      <main class="flex flex-1 flex-col gap-4 p-4 pt-0 lg:px-6">
        <RouterView />
      </main>
    </SidebarInset>
  </SidebarProvider>
</template>
