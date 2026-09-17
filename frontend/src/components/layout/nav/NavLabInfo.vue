<script setup lang="ts">
import { ref } from 'vue'
import { Info } from '@lucide/vue'

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
      <!-- 左下角团队标识与弹窗触发按钮 -->
      <SidebarMenuButton
        size="lg"
        tooltip="开发团队 · 软件信息"
        @click="handleOpenDialog"
      >
        <!-- 企业品牌简称标识 (株齿 ZC) -->
        <div class="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-accent text-sidebar-accent-foreground font-bold text-xs tracking-tight shrink-0 select-none">
          ZC
        </div>

        <!-- 机构团队名称（侧边栏折叠时自动由 group-data-[collapsible=icon] 隐藏） -->
        <div class="flex flex-1 items-center text-left group-data-[collapsible=icon]:hidden">
          <span class="truncate font-semibold text-sm text-sidebar-foreground">电驱系统研究所</span>
        </div>

        <!-- 信息指引图标 -->
        <Info class="ml-auto text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden" />
      </SidebarMenuButton>
    </SidebarMenuItem>
  </SidebarMenu>

  <!-- 软件信息对话框 -->
  <SoftwareInfoDialog v-model:open="isDialogOpen" />
</template>
