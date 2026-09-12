<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <h2>PlayGen</h2>
        <span>接口采集与用例生成</span>
      </div>
      <el-menu :default-active="activeMenu" router class="sidebar-menu">
        <el-menu-item index="/projects">
          <el-icon><Folder /></el-icon>
          <span>项目管理</span>
        </el-menu-item>
        <el-menu-item index="/recordings">
          <el-icon><VideoCamera /></el-icon>
          <span>录制管理</span>
        </el-menu-item>
        <el-menu-item index="/apis">
          <el-icon><Connection /></el-icon>
          <span>接口资产</span>
        </el-menu-item>
        <el-menu-item index="/scenarios">
          <el-icon><Document /></el-icon>
          <span>场景管理</span>
        </el-menu-item>
        <el-menu-item index="/executions">
          <el-icon><CaretRight /></el-icon>
          <span>执行记录</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
          <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
        </el-breadcrumb>
      </el-header>
      <el-main class="content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
const currentTitle = computed(() => (route.meta?.title as string) || '首页')
</script>

<style scoped>
.main-layout {
  height: 100vh;
}
.sidebar {
  background: #304156;
  color: #fff;
}
.logo {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.logo h2 {
  color: #409eff;
  margin-bottom: 4px;
}
.logo span {
  font-size: 12px;
  color: #909399;
}
.sidebar-menu {
  border-right: none;
  background: #304156;
}
.sidebar-menu .el-menu-item {
  color: #bfcbd9;
}
.sidebar-menu .el-menu-item:hover,
.sidebar-menu .el-menu-item.is-active {
  background: #263445;
  color: #409eff;
}
.header {
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  padding: 0 20px;
}
.content {
  background: #f0f2f5;
  padding: 20px;
}
</style>
