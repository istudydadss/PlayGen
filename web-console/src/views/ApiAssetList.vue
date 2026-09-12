<template>
  <div>
    <div class="page-header"><h2>接口资产</h2></div>
    <el-form inline style="margin-bottom:16px">
      <el-form-item label="项目"><el-select v-model="projectId" placeholder="选择项目" @change="fetchApis" style="width:200px">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select></el-form-item>
      <el-form-item label="方法"><el-select v-model="method" clearable @change="fetchApis" style="width:100px">
        <el-option label="GET" value="GET" /><el-option label="POST" value="POST" /><el-option label="PUT" value="PUT" /><el-option label="DELETE" value="DELETE" />
      </el-select></el-form-item>
      <el-form-item><el-input v-model="search" placeholder="搜索接口" clearable @change="fetchApis" style="width:200px" /></el-form-item>
    </el-form>
    <el-table :data="apis" v-loading="loading" stripe>
      <el-table-column prop="method" label="Method" width="80"><template #default="{ row }"><el-tag size="small" :type="({ GET:'', POST:'success', PUT:'warning', DELETE:'danger' }[row.method]||'') as any">{{ row.method }}</el-tag></template></el-table-column>
      <el-table-column prop="normalized_path" label="路径" min-width="350" show-overflow-tooltip />
      <el-table-column prop="name" label="名称" width="200" show-overflow-tooltip />
      <el-table-column prop="risk_level" label="风险" width="100"><template #default="{ row }"><el-tag :type="({ SAFE:'success', CONTROLLED:'warning', DANGEROUS:'danger' }[row.risk_level]||'') as any" size="small">{{ row.risk_level }}</el-tag></template></el-table-column>
      <el-table-column prop="sample_count" label="样本" width="70" />
      <el-table-column prop="lifecycle" label="状态" width="100" />
    </el-table>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apisApi, projectApi } from '@/api'
const projects = ref<any[]>([]); const apis = ref<any[]>([]); const loading = ref(false)
const projectId = ref(''); const method = ref(''); const search = ref('')
const fetchProjects = async () => { const r = await projectApi.list() as any; projects.value = r.items || [] }
const fetchApis = async () => { if (!projectId.value) return; loading.value = true; try { const r = await apisApi.list(projectId.value, { method: method.value, search: search.value }) as any; apis.value = r.items || [] } finally { loading.value = false } }
onMounted(fetchProjects)
</script>
<style scoped>.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; } .page-header h2 { margin: 0; }</style>
