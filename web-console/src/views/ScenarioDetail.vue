<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>{{ scenario?.name || '场景详情' }}</h2>
      <div>
        <el-select v-model="envId" placeholder="选择环境" style="width:180px;margin-right:8px">
          <el-option v-for="e in envs" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
        <el-button type="success" @click="runScenario" :disabled="!envId">执行</el-button>
        <el-button @click="generateCode">生成代码</el-button>
        <el-button type="primary" @click="saveDsl">保存 DSL</el-button>
      </div>
    </div>
    <el-row :gutter="16">
      <el-col :span="12">
        <h3>DSL 编辑器</h3>
        <el-input v-model="dslContent" type="textarea" :rows="25" style="font-family:monospace" />
      </el-col>
      <el-col :span="12">
        <h3>生成代码</h3>
        <el-input v-model="generatedCode" type="textarea" :rows="25" readonly style="font-family:monospace" />
      </el-col>
    </el-row>
    <el-dialog v-model="showResult" title="执行结果" width="700px">
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="状态"><el-tag :type="execResult.status === 'passed' ? 'success' : 'danger'">{{ execResult.status }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="耗时">{{ execResult.total_duration_ms?.toFixed(0) }}ms</el-descriptions-item>
        <el-descriptions-item label="通过/失败">{{ execResult.summary?.passed }}/{{ execResult.summary?.failed }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="execResult.steps" stripe size="small" style="margin-top:12px">
        <el-table-column prop="sequence" label="#" width="50" />
        <el-table-column prop="name" label="步骤" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }"><el-tag :type="row.status === 'passed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'" size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" width="100"><template #default="{ row }">{{ row.duration_ms?.toFixed(0) }}ms</template></el-table-column>
        <el-table-column prop="error_message" label="错误" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { scenarioApi, executionApi, environmentApi } from '@/api'
import { ElMessage } from 'element-plus'
const route = useRoute(); const scenarioId = route.params.id as string
const scenario = ref<any>(null); const dslContent = ref(''); const generatedCode = ref(''); const loading = ref(false)
const envId = ref(''); const envs = ref<any[]>([]); const showResult = ref(false); const execResult = ref<any>({})
const fetchScenario = async () => {
  loading.value = true
  try {
    scenario.value = await scenarioApi.get(scenarioId) as any
    const dsl = await scenarioApi.getDsl(scenarioId) as any
    dslContent.value = dsl.dsl || ''
    const envRes = await environmentApi.list(scenario.value.project_id) as any
    envs.value = envRes.items || []
  } finally { loading.value = false }
}
const saveDsl = async () => { await scenarioApi.saveDsl(scenarioId, { dsl: dslContent.value }); ElMessage.success('DSL 已保存') }
const generateCode = async () => { const r = await scenarioApi.generateCode(scenarioId) as any; generatedCode.value = r.code }
const runScenario = async () => {
  const r = await executionApi.create({ scenario_id: scenarioId, environment_id: envId.value }) as any
  ElMessage.success('执行已创建'); showResult.value = true
  execResult.value = { status: 'running', steps: [], summary: { passed: 0, failed: 0 }, total_duration_ms: 0 }
  // 轮询结果
  const poll = setInterval(async () => {
    const detail = await executionApi.get(r.id) as any
    if (detail.task.status !== 'pending' && detail.task.status !== 'running') {
      clearInterval(poll); execResult.value = { ...detail.task, steps: detail.step_results }
    }
  }, 2000)
}
onMounted(fetchScenario)
</script>
<style scoped>.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; } .page-header h2 { margin: 0; }</style>
