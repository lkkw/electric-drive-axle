<script setup lang="ts">
import { MapPinIcon, NavigationIcon } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'

defineProps<{
  title: string
  description: string
}>()

const route = useRoute()
const router = useRouter()

/** 跳转目标：以后新增页面时在这里补一项即可。 */
const links = [
  { label: '仪表盘', to: '/' },
  { label: 'SSE 实时消息', to: '/realtime' },
  { label: '示例页面一', to: '/pages/one' },
  { label: '示例页面二', to: '/pages/two' },
]
</script>

<template>
  <div class="flex flex-col gap-4 md:gap-6">
    <header class="flex flex-col gap-2">
      <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">{{ title }}</h1>
      <p class="max-w-3xl text-muted-foreground">{{ description }}</p>
    </header>

    <Card>
      <CardHeader>
        <div class="flex items-start gap-3">
          <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
            <MapPinIcon class="size-5" aria-hidden="true" />
          </div>
          <div class="flex min-w-0 flex-1 flex-col gap-1">
            <CardTitle>当前路由信息</CardTitle>
            <CardDescription>
              通过 <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">useRoute()</code>
              读取，路由跳转后这里会自动更新。
            </CardDescription>
          </div>
          <Badge variant="secondary">路由测试</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <dl class="grid gap-3 text-sm md:grid-cols-2">
          <div class="grid gap-1">
            <dt class="text-muted-foreground">路径 path</dt>
            <dd class="font-mono text-xs">{{ route.path }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground">完整地址 fullPath</dt>
            <dd class="font-mono text-xs">{{ route.fullPath }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground">路由名称 name</dt>
            <dd class="font-mono text-xs">{{ route.name ?? '—' }}</dd>
          </div>
          <div class="grid gap-1">
            <dt class="text-muted-foreground">页面标题 meta.title</dt>
            <dd class="font-mono text-xs">{{ route.meta.title ?? '—' }}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div class="flex items-start gap-3">
          <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
            <NavigationIcon class="size-5" aria-hidden="true" />
          </div>
          <div class="flex min-w-0 flex-1 flex-col gap-1">
            <CardTitle>路由跳转测试</CardTitle>
            <CardDescription>点击按钮切换到其他页面，观察地址栏、面包屑与菜单高亮的变化。</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-2">
        <Button
          v-for="link in links"
          :key="link.to"
          variant="outline"
          size="sm"
          @click="router.push(link.to)"
        >
          {{ link.label }}
        </Button>
      </CardContent>
    </Card>

    <Separator />

    <p class="text-sm text-muted-foreground">
      本页面由
      <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">src/components/demo/RouteTestPanel.vue</code>
      渲染，属于示例测试界面。开发时直接用业务内容替换
      <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">src/views/</code>
      下对应页面即可。
    </p>
  </div>
</template>
