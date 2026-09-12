<template>
  <div>
    <div class="page-header">
      <h2>录制管理</h2>
      <el-button type="primary" @click="showStartDialog = true">
        <el-icon><VideoCamera /></el-icon> 新建录制
      </el-button>
    </div>
    <el-table :data="recordings" v-loading="loading" stripe>
      <el-table-column prop="name" label="名称" min-width="200">
        <template #default="{ row }">
          <router-link :to="`/recordings/${row.id}`" class="link">{{ row.name || '未命名录制' }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="browser" label="浏览器" width="100" />
      <el-table-column prop="total_requests" label="请求数" width="100" />
      <el-table-column prop="total_actions" label="操作数" width="100" />
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button v-if="row.status === 'recording'" size="small" @click="pauseRecording(row.id)">暂停</el-button>
          <el-button v-if="row.status === 'paused'" size="small" @click="resumeRecording(row.id)">继续</el-button>
          <el-button v-if="['recording','paused'].includes(row.status)" size="small" type="warning" @click="stopRecording(row.id)">停止</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="showStartDialog" title="新建录制" width="500px">
      <el-form :model="startForm" label-width="80px">
        <el-form-item label="项目" required>
          <el-select v-model="startForm.project_id" placeholder="选择项目" style="width:100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="startForm.name" /></el-form-item>
        <el-form-item label="起始URL"><el-input v-model="startForm.start_url" placeholder="https://example.com" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStartDialog = false">取消</el-button>
        <el-button type="primary" @click="startRecording">开始录制</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { recordingApi, projectApi } from '@/api'
import { ElMessage } from 'element-plus'
const router = useRouter()
const recordings = ref<any[]>([])
const projects = ref<any[]>([])
const loading = ref(false)
const showStartDialog = ref(false)
const startForm = ref({ project_id: '', name: '', start_url: '' })
const statusLabel = (s: string) => ({ idle:'待开始', recording:'录制中', paused:'已暂停', stopped:'已停止', analyzing:'分析中', analyzed:'已分析', error:'错误' }[s] || s)
const statusType = (s: string) => ({ idle:'info', recording:'danger', paused:'warning', stopped:'', analyzing:'warning', analyzed:'success', error:'danger' }[s] || '') as any
const fetchData = async () => { loading.value = true; try { const r = await recordingApi.list() as any; recordings.value = r.items || [] } finally { loading.value = false } }
const fetchProjects = async () => { const r = await projectApi.list() as any; projects.value = r.items || [] }
const startRecording = async () => {
  const result = await recordingApi.start(startForm.value) as any
  ElMessage.success('录制已创建，正在启动浏览器...')
  showStartDialog.value = false
  // 跳转到录制详情页，可以看到实时流量和 CDP 地址
  router.push(`/recordings/${result.id}`)
}
const pauseRecording = async (id: string) => { await recordingApi.pause(id); fetchData() }
const resumeRecording = async (id: string) => { await recordingApi.resume(id); fetchData() }
const stopRecording = async (id: string) => { await recordingApi.stop(id); ElMessage.success('已停止'); fetchData() }
onMounted(() => { fetchData(); fetchProjects() })
</script>
<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
.link { color: #409eff; text-decoration: none; }
</style>
