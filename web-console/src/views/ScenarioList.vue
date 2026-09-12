<template>
  <div>
    <div class="page-header"><h2>场景管理</h2>
      <el-button type="primary" @click="showCreate = true">新建场景</el-button>
    </div>
    <el-table :data="scenarios" v-loading="loading" stripe>
      <el-table-column prop="name" label="名称" min-width="250">
        <template #default="{ row }"><router-link :to="`/scenarios/${row.id}`" class="link">{{ row.name }}</router-link></template>
      </el-table-column>
      <el-table-column prop="risk_level" label="风险等级" width="120">
        <template #default="{ row }"><el-tag :type="({ SAFE:'success', CONTROLLED:'warning', DANGEROUS:'danger' }[row.risk_level]||'') as any" size="small">{{ row.risk_level }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="dsl_version" label="DSL版本" width="90" />
      <el-table-column prop="updated_at" label="更新时间" width="180"><template #default="{ row }">{{ new Date(row.updated_at).toLocaleString('zh-CN') }}</template></el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="$router.push(`/scenarios/${row.id}`)">编辑</el-button>
          <el-button size="small" type="success" @click="executeScenario(row.id)">执行</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="showCreate" title="新建场景" width="500px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="项目" required><el-select v-model="form.project_id" style="width:100%">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select></el-form-item>
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showCreate=false">取消</el-button><el-button type="primary" @click="createScenario">创建</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { scenarioApi, projectApi, executionApi } from '@/api'
import { ElMessage } from 'element-plus'
const scenarios = ref<any[]>([]); const projects = ref<any[]>([]); const loading = ref(false); const showCreate = ref(false)
const form = ref({ project_id: '', name: '' })
const fetchData = async () => { loading.value = true; try { const r = await scenarioApi.list() as any; scenarios.value = r.items || [] } finally { loading.value = false } }
const fetchProjects = async () => { const r = await projectApi.list() as any; projects.value = r.items || [] }
const createScenario = async () => { await scenarioApi.create(form.value); ElMessage.success('已创建'); showCreate.value = false; fetchData() }
const executeScenario = async (id: string) => { ElMessage.info('请在场景详情页选择环境后执行') }
onMounted(() => { fetchData(); fetchProjects() })
</script>
<style scoped>.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; } .page-header h2 { margin: 0; } .link { color: #409eff; text-decoration: none; }</style>
