<script setup lang="ts">
import type { SidebarProps } from '@/components/ui/sidebar'

import {
  AudioWaveform,
  Command,
  Frame,
  GalleryVerticalEnd,
  LayoutDashboard,
  Map,
  PieChart,
  Radio,
} from '@lucide/vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import NavMain from '@/components/layout/nav/NavMain.vue'
import NavProjects from '@/components/layout/nav/NavProjects.vue'
import NavUser from '@/components/layout/nav/NavUser.vue'
import TeamSwitcher from '@/components/layout/nav/TeamSwitcher.vue'
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
// 布局配置：以后新增页面只需在 navMain / projects 中追加一项即可。
// ---------------------------------------------------------------------------
const data = {
  user: {
    name: 'FastAPI Vue',
    email: 'admin@example.com',
    avatar: '',
  },
  teams: [
    {
      name: 'Acme Inc',
      logo: GalleryVerticalEnd,
      plan: 'Enterprise',
    },
    {
      name: 'Acme Corp.',
      logo: AudioWaveform,
      plan: 'Startup',
    },
    {
      name: 'Evil Corp.',
      logo: Command,
      plan: 'Free',
    },
  ],
  navMain: [
    {
      title: '仪表盘',
      url: '/',
      icon: LayoutDashboard,
    },
    {
      title: '实时演示',
      url: '/realtime',
      icon: Radio,
      items: [
        {
          title: 'SSE 实时消息',
          url: '/realtime',
        },
      ],
    },
    {
      title: '示例页面',
      url: '/pages/one',
      icon: Command,
      items: [
        {
          title: '示例页面一',
          url: '/pages/one',
        },
        {
          title: '示例页面二',
          url: '/pages/two',
        },
      ],
    },
  ],
  projects: [
    {
      name: '示例项目 Alpha',
      url: '/pages/one',
      icon: PieChart,
    },
    {
      name: '示例项目 Beta',
      url: '/pages/two',
      icon: Frame,
    },
    {
      name: '接口文档',
      url: 'http://127.0.0.1:8000/docs',
      icon: Map,
    },
  ],
}

/** 菜单激活状态跟随当前路由自动更新。 */
const navMain = computed(() =>
  data.navMain.map((item) => {
    const subItems = item.items?.map((subItem) => ({
      ...subItem,
      isActive: route.path === subItem.url,
    }))
    return {
      ...item,
      isActive: route.path === item.url || (subItems?.some((subItem) => subItem.isActive) ?? false),
      items: subItems,
    }
  }),
)
</script>

<template>
  <Sidebar v-bind="props">
    <SidebarHeader>
      <TeamSwitcher :teams="data.teams" />
    </SidebarHeader>
    <SidebarContent>
      <NavMain :items="navMain" />
      <NavProjects :projects="data.projects" />
    </SidebarContent>
    <SidebarFooter>
      <NavUser :user="data.user" />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
