<template>
  <div class="project-detail" v-loading="loading">
    <div class="page-header">
      <h2>{{ project?.name || '项目详情' }}</h2>
    </div>
    <el-descriptions :column="2" border v-if="project">
      <el-descriptions-item label="项目ID">{{ project.id }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="project.status === 'active' ? 'success' : 'info'">{{ project.status }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">{{ project.description || '-' }}</el-descriptions-item>
    </el-descriptions>

    <el-divider />
    <h3>环境管理</h3>
    <el-button type="primary" size="small" @click="showEnvDialog = true" style="margin-bottom: 12px">添加环境</el-button>
    <el-table :data="environments" stripe size="small">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="env_type" label="类型" width="120" />
      <el-table-column prop="base_url" label="Base URL" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="deleteEnv(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showEnvDialog" title="添加环境" width="500px">
      <el-form :model="envForm" label-width="80px">
        <el-form-item label="名称" required><el-input v-model="envForm.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="envForm.env_type">
            <el-option label="开发" value="development" />
            <el-option label="测试" value="test" />
            <el-option label="预发布" value="staging" />
            <el-option label="生产" value="production" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" required><el-input v-model="envForm.base_url" placeholder="https://api.example.com" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEnvDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEnv">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { projectApi, environmentApi } from '@/api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const projectId = route.params.id as string
const project = ref<any>(null)
const environments = ref<any[]>([])
const loading = ref(false)
const showEnvDialog = ref(false)
const envForm = ref({ name: '', env_type: 'test', base_url: '' })

const fetchData = async () => {
  loading.value = true
  try {
    project.value = await projectApi.get(projectId)
    const envRes = await environmentApi.list(projectId) as any
    environments.value = envRes.items || []
  } finally { loading.value = false }
}

const saveEnv = async () => {
  if (!envForm.value.name || !envForm.value.base_url) { ElMessage.warning('请填写必填项'); return }
  await environmentApi.create(projectId, envForm.value)
  ElMessage.success('环境已添加')
  showEnvDialog.value = false
  envForm.value = { name: '', env_type: 'test', base_url: '' }
  fetchData()
}

const deleteEnv = async (id: string) => {
  await environmentApi.delete(id)
  ElMessage.success('已删除')
  fetchData()
}

onMounted(fetchData)
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
</style>
