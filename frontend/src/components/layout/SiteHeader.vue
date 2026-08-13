<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'

const route = useRoute()

// 路由 -> 面包屑文案。以后新增页面时在这里补一行即可。
const pageTitles: Record<string, { group: string; page: string }> = {
  '/': { group: '概览', page: '仪表盘' },
  '/realtime': { group: '实时演示', page: 'SSE 实时消息' },
  '/pages/one': { group: '示例页面', page: '示例页面一' },
  '/pages/two': { group: '示例页面', page: '示例页面二' },
}

const currentPage = computed(
  () =>
    pageTitles[route.path] ?? {
      group: '应用',
      page: route.path === '/' ? '仪表盘' : '页面',
    },
)
</script>

<template>
  <header
    class="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12"
  >
    <div class="flex items-center gap-2 px-4">
      <SidebarTrigger class="-ml-1" />
      <Separator
        orientation="vertical"
        class="mr-2 data-[orientation=vertical]:h-4"
      />
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem class="hidden md:block">
            {{ currentPage.group }}
          </BreadcrumbItem>
          <BreadcrumbSeparator class="hidden md:block" />
          <BreadcrumbItem>
            <BreadcrumbPage>{{ currentPage.page }}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
    </div>
  </header>
</template>
