import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 响应拦截
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || error.message
    console.error('API Error:', msg)
    return Promise.reject(error)
  }
)

// ========== 项目 ==========
export const projectApi = {
  list: (params?: any) => api.get('/projects', { params }),
  get: (id: string) => api.get(`/projects/${id}`),
  create: (data: any) => api.post('/projects', data),
  update: (id: string, data: any) => api.put(`/projects/${id}`, data),
  delete: (id: string) => api.delete(`/projects/${id}`),
}

// ========== 环境 ==========
export const environmentApi = {
  list: (projectId: string, params?: any) => api.get(`/projects/${projectId}/environments`, { params }),
  create: (projectId: string, data: any) => api.post(`/projects/${projectId}/environments`, data),
  update: (id: string, data: any) => api.put(`/environments/${id}`, data),
  delete: (id: string) => api.delete(`/environments/${id}`),
}

// ========== 录制 ==========
export const recordingApi = {
  list: (params?: any) => api.get('/recordings', { params }),
  start: (data: any) => api.post('/recordings', data),
  pause: (id: string) => api.post(`/recordings/${id}/pause`),
  resume: (id: string) => api.post(`/recordings/${id}/resume`),
  stop: (id: string) => api.post(`/recordings/${id}/stop`),
  getTraffic: (id: string, params?: any) => api.get(`/recordings/${id}/traffic`, { params }),
  getTrafficDetail: (recordingId: string, recordId: string) => api.get(`/recordings/${recordingId}/traffic/${recordId}`),
  analyze: (id: string) => api.post(`/recordings/${id}/analyze`),
  getStatus: (id: string) => api.get(`/recordings/${id}/status`),
  /** 获取 WebSocket 连接 URL */
  getWsUrl: (id: string) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80')
    return `${protocol}//${host}:${port}/ws/recording/${id}`
  },
}

// ========== 接口资产 ==========
export const apisApi = {
  list: (projectId: string, params?: any) => api.get(`/projects/${projectId}/apis`, { params }),
  get: (id: string) => api.get(`/apis/${id}`),
  update: (id: string, data: any) => api.patch(`/apis/${id}`, data),
}

// ========== 场景 ==========
export const scenarioApi = {
  list: (params?: any) => api.get('/scenarios', { params }),
  get: (id: string) => api.get(`/scenarios/${id}`),
  create: (data: any) => api.post('/scenarios', data),
  createFromRecording: (recordingId: string, data: any) => api.post(`/scenarios/from-recording/${recordingId}`, data),
  getDsl: (id: string) => api.get(`/scenarios/${id}/dsl`),
  saveDsl: (id: string, data: any) => api.put(`/scenarios/${id}/dsl`, data),
  generateCode: (id: string, data?: any) => api.post(`/scenarios/${id}/generate-code`, data),
}

// ========== 执行 ==========
export const executionApi = {
  list: (params?: any) => api.get('/executions', { params }),
  create: (data: any) => api.post('/executions', data),
  get: (id: string) => api.get(`/executions/${id}`),
  cancel: (id: string) => api.post(`/executions/${id}/cancel`),
}

export default api
