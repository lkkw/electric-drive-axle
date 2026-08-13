<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import {
  ActivityIcon,
  ArrowRightIcon,
  RadioIcon,
  ServerIcon,
  ZapIcon,
} from '@lucide/vue'
import { RouterLink } from 'vue-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { useDemoStore } from '@/stores/useDemoStore'

const demoStore = useDemoStore()
const { demo, loading, error } = storeToRefs(demoStore)

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
})

onMounted(() => {
  void demoStore.fetchDemo()
})
</script>

<template>
  <div class="flex flex-col gap-4 md:gap-6">
    <div class="flex flex-col gap-2">
      <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">仪表盘</h1>
      <p class="max-w-3xl text-muted-foreground">
        欢迎使用 FastAPI + Vue 3 全栈模板。左侧侧边栏已搭好导航框架，右侧内容区用于承载
        你的业务页面。
      </p>
    </div>

    <!-- 后端状态概览卡片 -->
    <div class="grid gap-4 md:grid-cols-3">
      <Card>
        <CardHeader>
          <div class="flex items-start gap-3">
            <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
              <ServerIcon class="size-5" aria-hidden="true" />
            </div>
            <div class="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle>REST API</CardTitle>
              <CardDescription>通过 Alova 请求后端演示数据。</CardDescription>
            </div>
          </div>
          <CardAction>
            <Badge :variant="demo ? 'default' : 'outline'">
              {{ demo ? '数据已同步' : '等待数据' }}
            </Badge>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <p class="text-sm font-medium">{{ demo?.message ?? (loading ? '请求中…' : '尚无数据') }}</p>
          <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div class="flex items-start gap-3">
            <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
              <RadioIcon class="size-5" aria-hidden="true" />
            </div>
            <div class="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle>SSE 实时推送</CardTitle>
              <CardDescription>浏览器原生 EventSource 长连接。</CardDescription>
            </div>
          </div>
          <CardAction>
            <Badge variant="secondary">示例</Badge>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <p class="text-sm text-muted-foreground">
            前往「实时演示」页面查看每秒推送的消息与实时曲线。
          </p>
        </CardContent>
        <CardFooter>
          <Button as-child variant="outline" size="sm">
            <RouterLink to="/realtime">
              查看实时演示
              <ArrowRightIcon data-icon="inline-end" />
            </RouterLink>
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <div class="flex items-start gap-3">
            <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
              <ActivityIcon class="size-5" aria-hidden="true" />
            </div>
            <div class="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle>服务器状态</CardTitle>
              <CardDescription>健康检查与响应元数据。</CardDescription>
            </div>
          </div>
          <CardAction>
            <Badge variant="default">运行中</Badge>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-2 text-sm text-muted-foreground">
          <div class="flex items-center justify-between gap-3">
            <span>服务器时间</span>
            <span class="font-medium text-foreground">
              {{ demo ? dateFormatter.format(new Date(demo.server_time)) : '—' }}
            </span>
          </div>
          <Separator />
          <div class="flex items-center justify-between gap-3">
            <span>请求 ID</span>
            <span class="truncate font-mono text-xs text-foreground">
              {{ demo?.request_id ?? '—' }}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 快速开始 -->
    <Card>
      <CardHeader>
        <div class="flex items-start gap-3">
          <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
            <ZapIcon class="size-5" aria-hidden="true" />
          </div>
          <div class="flex min-w-0 flex-1 flex-col gap-1">
            <CardTitle>开始开发</CardTitle>
            <CardDescription>
              布局框架已经就绪：侧边栏菜单在
              <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">src/components/layout/AppSidebar.vue</code>
              中配置，页面路由在
              <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">src/router/index.ts</code>
              中注册，内容直接写在
              <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">src/views/</code>
              下即可。
            </CardDescription>
          </div>
        </div>
      </CardHeader>
    </Card>
  </div>
</template>
