<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>录制详情 - {{ session?.name || session?.id }}</h2>
      <div>
        <el-button v-if="isActive" type="warning" @click="pauseRecording">暂停</el-button>
        <el-button v-if="session?.status === 'paused'" type="success" @click="resumeRecording">继续</el-button>
        <el-button v-if="isActive || session?.status === 'paused'" type="danger" @click="stopRecording">停止录制</el-button>
        <el-button type="success" @click="createScenario" :disabled="!hasBusinessTraffic">生成场景</el-button>
        <el-button @click="fetchTraffic">刷新</el-button>
      </div>
    </div>

    <!-- 录制状态信息 -->
    <el-descriptions :column="4" border size="small" style="margin-bottom:16px">
      <el-descriptions-item label="状态">
        <el-tag :type="statusType" size="small">{{ statusLabel }}</el-tag>
        <span v-if="isActive" class="recording-indicator">● 录制中</span>
      </el-descriptions-item>
      <el-descriptions-item label="请求总数">{{ session?.total_requests || traffic.length }}</el-descriptions-item>
      <el-descriptions-item label="浏览器">{{ session?.browser }}</el-descriptions-item>
      <el-descriptions-item label="业务接口">
        <el-tag type="success" size="small">{{ businessCount }}</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <!-- CDP 调试信息 -->
    <el-alert
      v-if="cdpUrl"
      type="info"
      :closable="false"
      style="margin-bottom:16px"
    >
      <template #title>
        <span>浏览器远程调试地址: </span>
        <code>{{ cdpUrl }}</code>
        <span style="margin-left:8px;color:#909399;font-size:12px">
          （在 Chrome 地址栏输入 chrome://inspect 可远程查看浏览器内容）
        </span>
      </template>
    </el-alert>

    <!-- 实时流量表格 -->
    <el-table :data="traffic" stripe size="small">
      <el-table-column prop="method" label="Method" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="methodType(row.method)">{{ row.method }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="url" label="URL" min-width="400" show-overflow-tooltip />
      <el-table-column prop="status_code" label="状态码" width="80">
        <template #default="{ row }">
          <span v-if="row.status_code" :style="{ color: row.status_code >= 400 ? 'red' : 'green' }">
            {{ row.status_code }}
          </span>
          <span v-else style="color:#909399">...</span>
        </template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时(ms)" width="100">
        <template #default="{ row }">
          {{ row.duration_ms != null ? row.duration_ms.toFixed(0) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="resource_type" label="类型" width="80" />
      <el-table-column prop="is_business" label="业务" width="70">
        <template #default="{ row }">
          <el-tag v-if="row.is_business" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="business_score" label="评分" width="70" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { recordingApi, scenarioApi } from '@/api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const recordingId = route.params.id as string

const session = ref<any>(null)
const traffic = ref<any[]>([])
const loading = ref(false)
const cdpUrl = ref<string | null>(null)
const isActive = ref(false)
let ws: WebSocket | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null

const methodType = (m: string) =>
  ({ GET: '', POST: 'success', PUT: 'warning', DELETE: 'danger' }[m] || '') as any

const businessCount = computed(() => traffic.value.filter((t: any) => t.is_business).length)
const hasBusinessTraffic = computed(() => businessCount.value > 0)

const statusLabel = computed(() => {
  if (isActive.value) return '录制中'
  return ({ idle: '待开始', recording: '录制中', paused: '已暂停', stopped: '已停止', analyzing: '分析中', analyzed: '已分析', error: '错误' } as any)[session.value?.status] || session.value?.status
})

const statusType = computed(() => {
  if (isActive.value) return 'danger'
  return ({ idle: 'info', recording: 'danger', paused: 'warning', stopped: '', analyzing: 'warning', analyzed: 'success', error: 'danger' } as any)[session.value?.status] || ''
})

// 获取录制状态
const fetchStatus = async () => {
  try {
    const status = await recordingApi.getStatus(recordingId) as any
    isActive.value = status.is_active
    cdpUrl.value = status.cdp_url
  } catch {
    isActive.value = false
  }
}

// 获取流量数据
const fetchTraffic = async () => {
  loading.value = true
  try {
    const list = await recordingApi.list() as any
    session.value = list.items?.find((r: any) => r.id === recordingId)
    const t = await recordingApi.getTraffic(recordingId) as any
    traffic.value = t.items || []
    await fetchStatus()
  } finally {
    loading.value = false
  }
}

// WebSocket 连接
const connectWebSocket = () => {
  if (ws) return

  const wsUrl = recordingApi.getWsUrl(recordingId)
  ws = new WebSocket(wsUrl)

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'network_event' && msg.data) {
        // 实时添加新捕获的请求
        traffic.value.push({
          ...msg.data,
          is_business: null,
          business_score: null,
        })
      } else if (msg.type === 'page_action') {
        // 可以扩展显示页面操作
      }
    } catch (e) {
      console.error('WebSocket 消息解析失败:', e)
    }
  }

  ws.onclose = () => {
    ws = null
    // 如果仍在录制中，尝试重连
    if (isActive.value) {
      setTimeout(connectWebSocket, 3000)
    }
  }

  ws.onerror = () => {
    ws?.close()
  }

  // 心跳保活
  heartbeatTimer = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send('ping')
    }
  }, 30000)
}

// 断开 WebSocket
const disconnectWebSocket = () => {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
}

// 轮询状态（当 WebSocket 不可用时作为后备）
const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    await fetchStatus()
    if (!isActive.value) {
      // 录制已结束，停止轮询并刷新数据
      stopPolling()
      disconnectWebSocket()
      await fetchTraffic()
    }
  }, 5000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 暂停 / 继续 / 停止
const pauseRecording = async () => {
  await recordingApi.pause(recordingId)
  ElMessage.success('已暂停')
  await fetchTraffic()
}

const resumeRecording = async () => {
  await recordingApi.resume(recordingId)
  ElMessage.success('已继续')
  await fetchTraffic()
}

const stopRecording = async () => {
  loading.value = true
  await recordingApi.stop(recordingId)
  ElMessage.success('已停止，正在分析流量...')
  isActive.value = false
  disconnectWebSocket()
  stopPolling()
  // 等待分析完成
  setTimeout(async () => {
    await fetchTraffic()
    loading.value = false
  }, 3000)
}

// 生成场景
const createScenario = async () => {
  const businessIds = traffic.value.filter((t: any) => t.is_business).map((t: any) => t.id)
  if (!businessIds.length) {
    ElMessage.warning('没有业务接口')
    return
  }
  await scenarioApi.createFromRecording(recordingId, {
    project_id: session.value.project_id,
    name: `场景-${session.value.name || recordingId.slice(0, 8)}`,
    network_record_ids: businessIds,
  })
  ElMessage.success('场景已创建')
  router.push('/scenarios')
}

// 监听录制状态变化
watch(isActive, (active: boolean) => {
  if (active) {
    connectWebSocket()
    startPolling()
  } else {
    disconnectWebSocket()
    stopPolling()
  }
})

onMounted(async () => {
  await fetchTraffic()
  // 如果录制正在进行，自动连接 WebSocket
  if (isActive.value || ['recording', 'paused'].includes(session.value?.status)) {
    connectWebSocket()
    startPolling()
  }
})

onBeforeUnmount(() => {
  disconnectWebSocket()
  stopPolling()
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
.recording-indicator { color: #f56c6c; margin-left: 8px; font-size: 12px; animation: blink 1s infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
