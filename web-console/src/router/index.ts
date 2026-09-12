import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/projects',
    children: [
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('@/views/ProjectList.vue'),
        meta: { title: '项目管理' },
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/ProjectDetail.vue'),
        meta: { title: '项目详情' },
      },
      {
        path: 'recordings',
        name: 'Recordings',
        component: () => import('@/views/RecordingList.vue'),
        meta: { title: '录制管理' },
      },
      {
        path: 'recordings/:id',
        name: 'RecordingDetail',
        component: () => import('@/views/RecordingDetail.vue'),
        meta: { title: '录制详情' },
      },
      {
        path: 'apis',
        name: 'ApiAssets',
        component: () => import('@/views/ApiAssetList.vue'),
        meta: { title: '接口资产' },
      },
      {
        path: 'scenarios',
        name: 'Scenarios',
        component: () => import('@/views/ScenarioList.vue'),
        meta: { title: '场景管理' },
      },
      {
        path: 'scenarios/:id',
        name: 'ScenarioDetail',
        component: () => import('@/views/ScenarioDetail.vue'),
        meta: { title: '场景详情' },
      },
      {
        path: 'executions',
        name: 'Executions',
        component: () => import('@/views/ExecutionList.vue'),
        meta: { title: '执行记录' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
