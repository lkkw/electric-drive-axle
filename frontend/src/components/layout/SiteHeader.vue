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

// 路由 -> 面包屑文案
const pageTitles: Record<string, { group: string; page: string }> = {
  '/': { group: '测控系统', page: 'CAN 通讯诊断' },
  '/can': { group: '测控系统', page: 'CAN 通讯诊断' },
  '/axle': { group: '测试台架', page: '电驱桥控制台' },
}

const currentPage = computed(
  () =>
    pageTitles[route.path] ?? {
      group: '测试台架',
      page: '控制系统',
    },
)
</script>

<template>
  <header
    class="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12"
  >
    <div class="flex items-center gap-2 px-4 sm:px-6">
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
