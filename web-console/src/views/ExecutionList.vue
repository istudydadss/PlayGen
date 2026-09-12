<template>
  <div>
    <div class="page-header"><h2>执行记录</h2></div>
    <el-table :data="executions" v-loading="loading" stripe>
      <el-table-column prop="execution_id" label="执行ID" width="180" />
      <el-table-column prop="scenario_id" label="场景ID" width="300" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="({ passed:'success', failed:'danger', running:'', pending:'info', cancelled:'warning' }[row.status]||'') as any" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="trigger_type" label="触发方式" width="100" />
      <el-table-column label="步骤" width="120">
        <template #default="{ row }">{{ row.passed_steps }}/{{ row.total_steps }}</template>
      </el-table-column>
      <el-table-column prop="total_duration_ms" label="耗时" width="100">
        <template #default="{ row }">{{ row.total_duration_ms?.toFixed(0) }}ms</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button v-if="['pending','running'].includes(row.status)" size="small" type="danger" @click="cancelExec(row.id)">取消</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { executionApi } from '@/api'
import { ElMessage } from 'element-plus'
const executions = ref<any[]>([]); const loading = ref(false)
const fetchData = async () => { loading.value = true; try { const r = await executionApi.list() as any; executions.value = r.items || [] } finally { loading.value = false } }
const cancelExec = async (id: string) => { await executionApi.cancel(id); ElMessage.success('已取消'); fetchData() }
onMounted(fetchData)
</script>
<style scoped>.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; } .page-header h2 { margin: 0; }</style>
