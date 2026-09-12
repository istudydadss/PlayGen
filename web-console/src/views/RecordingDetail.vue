<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>录制详情 - {{ session?.name || session?.id }}</h2>
      <div>
        <el-button type="success" @click="createScenario">生成场景</el-button>
        <el-button @click="fetchTraffic">刷新</el-button>
      </div>
    </div>
    <el-descriptions :column="3" border size="small" style="margin-bottom:16px">
      <el-descriptions-item label="状态"><el-tag size="small">{{ session?.status }}</el-tag></el-descriptions-item>
      <el-descriptions-item label="请求总数">{{ session?.total_requests }}</el-descriptions-item>
      <el-descriptions-item label="浏览器">{{ session?.browser }}</el-descriptions-item>
    </el-descriptions>
    <el-table :data="traffic" stripe size="small">
      <el-table-column prop="method" label="Method" width="80">
        <template #default="{ row }"><el-tag size="small" :type="methodType(row.method)">{{ row.method }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="url" label="URL" min-width="400" show-overflow-tooltip />
      <el-table-column prop="status_code" label="状态码" width="80">
        <template #default="{ row }"><span :style="{ color: row.status_code >= 400 ? 'red' : 'green' }">{{ row.status_code }}</span></template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时(ms)" width="100">
        <template #default="{ row }">{{ row.duration_ms?.toFixed(0) }}</template>
      </el-table-column>
      <el-table-column prop="resource_type" label="类型" width="80" />
      <el-table-column prop="is_business" label="业务" width="70">
        <template #default="{ row }"><el-tag v-if="row.is_business" type="success" size="small">是</el-tag><span v-else>-</span></template>
      </el-table-column>
      <el-table-column prop="business_score" label="评分" width="70" />
    </el-table>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { recordingApi, scenarioApi } from '@/api'
import { ElMessage } from 'element-plus'
const route = useRoute(); const router = useRouter()
const recordingId = route.params.id as string
const session = ref<any>(null); const traffic = ref<any[]>([]); const loading = ref(false)
const methodType = (m: string) => ({ GET: '', POST: 'success', PUT: 'warning', DELETE: 'danger' }[m] || '') as any
const fetchTraffic = async () => {
  loading.value = true
  try {
    const list = await recordingApi.list() as any
    session.value = list.items?.find((r: any) => r.id === recordingId)
    const t = await recordingApi.getTraffic(recordingId) as any
    traffic.value = t.items || []
  } finally { loading.value = false }
}
const createScenario = async () => {
  const businessIds = traffic.value.filter((t: any) => t.is_business).map((t: any) => t.id)
  if (!businessIds.length) { ElMessage.warning('没有业务接口'); return }
  await scenarioApi.createFromRecording(recordingId, {
    project_id: session.value.project_id, name: `场景-${session.value.name || recordingId.slice(0,8)}`,
    network_record_ids: businessIds,
  })
  ElMessage.success('场景已创建')
  router.push('/scenarios')
}
onMounted(fetchTraffic)
</script>
<style scoped>.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; } .page-header h2 { margin: 0; }</style>
