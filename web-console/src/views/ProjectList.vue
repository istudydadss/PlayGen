<template>
  <div class="project-list">
    <div class="page-header">
      <h2>项目管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon> 新建项目
      </el-button>
    </div>

    <el-table :data="projects" v-loading="loading" stripe>
      <el-table-column prop="name" label="项目名称" min-width="200">
        <template #default="{ row }">
          <router-link :to="`/projects/${row.id}`" class="link">{{ row.name }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="300" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === 'active' ? '活跃' : '已归档' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="editProject(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="archiveProject(row.id)">归档</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="showCreateDialog" :title="editingProject ? '编辑项目' : '新建项目'" width="600px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" placeholder="输入项目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="项目描述" />
        </el-form-item>
        <el-form-item label="域名白名单">
          <el-input v-model="domainInclude" placeholder="api.example.com, 多个用逗号分隔" />
        </el-form-item>
        <el-form-item label="排除路径">
          <el-input v-model="excludePaths" placeholder="/track, /heartbeat, 多个用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveProject" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { projectApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const projects = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreateDialog = ref(false)
const editingProject = ref<any>(null)
const form = ref({ name: '', description: '', config: {} as any })
const domainInclude = ref('')
const excludePaths = ref('')

const formatDate = (date: string) => new Date(date).toLocaleString('zh-CN')

const fetchProjects = async () => {
  loading.value = true
  try {
    const res = await projectApi.list() as any
    projects.value = res.items || []
  } catch (e) {
    ElMessage.error('加载项目失败')
  } finally {
    loading.value = false
  }
}

const editProject = (project: any) => {
  editingProject.value = project
  form.value = { name: project.name, description: project.description || '', config: project.config || {} }
  domainInclude.value = project.config?.domains?.include?.join(', ') || ''
  excludePaths.value = project.config?.filters?.exclude_paths?.join(', ') || ''
  showCreateDialog.value = true
}

const saveProject = async () => {
  if (!form.value.name) {
    ElMessage.warning('请输入项目名称')
    return
  }
  saving.value = true
  const config = {
    domains: { include: domainInclude.value.split(',').map(s => s.trim()).filter(Boolean) },
    filters: { exclude_paths: excludePaths.value.split(',').map(s => s.trim()).filter(Boolean) },
  }
  try {
    if (editingProject.value) {
      await projectApi.update(editingProject.value.id, { ...form.value, config })
      ElMessage.success('项目已更新')
    } else {
      await projectApi.create({ ...form.value, config })
      ElMessage.success('项目已创建')
    }
    showCreateDialog.value = false
    editingProject.value = null
    form.value = { name: '', description: '', config: {} }
    fetchProjects()
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const archiveProject = async (id: string) => {
  await ElMessageBox.confirm('确定归档该项目？', '提示', { type: 'warning' })
  await projectApi.delete(id)
  ElMessage.success('已归档')
  fetchProjects()
}

onMounted(fetchProjects)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 { margin: 0; }
.link { color: #409eff; text-decoration: none; }
</style>
