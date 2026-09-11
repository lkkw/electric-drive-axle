<script setup lang="ts">
import { ref } from 'vue'
import { Building2, Info } from '@lucide/vue'

import SoftwareInfoDialog from '@/components/layout/SoftwareInfoDialog.vue'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

/** 控制软件信息对话框打开状态 */
const isDialogOpen = ref(false)

/** 点击左下角卡片触发弹窗 */
function handleOpenDialog(): void {
  isDialogOpen.value = true
}
</script>

<template>
  <SidebarMenu>
    <SidebarMenuItem>
      <!-- 左下角机构标识与弹窗触发按钮 -->
      <SidebarMenuButton
        size="lg"
        tooltip="电驱系统研究所 · 软件信息"
        @click="handleOpenDialog"
      >
        <!-- 机构图标 -->
        <div class="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-accent text-sidebar-accent-foreground shrink-0">
          <Building2 class="size-4" />
        </div>

        <!-- 机构与软件概要说明（侧边栏折叠时自动由 group-data-[collapsible=icon] 隐藏） -->
        <div class="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
          <span class="truncate font-semibold text-sidebar-foreground">电驱系统研究所</span>
          <span class="truncate text-xs text-sidebar-foreground/70">软件信息 · v1.0.0</span>
        </div>

        <!-- 信息指引图标 -->
        <Info class="ml-auto text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden" />
      </SidebarMenuButton>
    </SidebarMenuItem>
  </SidebarMenu>

  <!-- 软件信息对话框 -->
  <SoftwareInfoDialog v-model:open="isDialogOpen" />
</template>
