<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'

import {
  Radio,
  ShieldCheck,
  Sliders,
  Zap,
} from '@lucide/vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import NavLabInfo from '@/components/layout/nav/NavLabInfo.vue'
import NavMain from '@/components/layout/nav/NavMain.vue'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'

const props = withDefaults(defineProps<SidebarProps>(), {
  collapsible: 'icon',
})

const route = useRoute()

// ---------------------------------------------------------------------------
// 侧边栏导航：通讯、控制与上位机安全策略
// ---------------------------------------------------------------------------
const navItems = [
  {
    title: 'CAN 通讯诊断',
    url: '/can',
    icon: Radio,
  },
  {
    title: '电驱桥控制台',
    url: '/axle',
    icon: Sliders,
  },
  {
    title: '安全配置',
    url: '/safety',
    icon: ShieldCheck,
  },
]

/** 菜单激活状态跟随当前路由自动更新 */
const navMain = computed(() =>
  navItems.map((item) => ({
    ...item,
    isActive: route.path === item.url || (item.url !== '/' && route.path.startsWith(item.url)),
  })),
)
</script>

<template>
  <Sidebar v-bind="props">
    <!-- 系统品牌标识 -->
    <SidebarHeader class="p-3 border-b border-sidebar-border">
      <div class="flex items-center gap-3">
        <div class="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shrink-0 shadow-xs">
          <Zap class="size-4" />
        </div>
        <div class="flex flex-1 items-center text-left group-data-[collapsible=icon]:hidden">
          <span class="truncate font-bold text-sm text-sidebar-foreground">电驱桥测控系统</span>
        </div>
      </div>
    </SidebarHeader>

    <!-- 主导航菜单 -->
    <SidebarContent>
      <NavMain :items="navMain" />
    </SidebarContent>

    <!-- 底部：电驱系统研究所 & 软件信息弹窗 -->
    <SidebarFooter class="p-2 border-t border-sidebar-border/50">
      <NavLabInfo />
    </SidebarFooter>

    <SidebarRail />
  </Sidebar>
</template>
