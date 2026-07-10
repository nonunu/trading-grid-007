<template>
  <el-container class="app-container">
    <el-aside width="200px" class="app-aside">
      <div class="logo">
        <h2>Trading Grid</h2>
        <p class="subtitle">统一网格交易系统</p>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="app-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><TrendCharts /></el-icon>
          <span>策略信息</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <span>管理维护</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <span class="page-title">{{ pageTitle }}</span>
        </div>
        <div class="header-right">
          <EngineControl />
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis, TrendCharts, Setting } from '@element-plus/icons-vue'
import EngineControl from '@/components/EngineControl.vue'
import { useWebSocket } from '@/composables/useWebSocket'

// 建立 WebSocket 连接用于实时数据
useWebSocket()

const route = useRoute()
const activeMenu = computed(() => route.path)

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/dashboard': 'Dashboard',
    '/strategy': '策略信息',
    '/config': '管理维护',
  }
  return titles[route.path] || 'Trading Grid'
})
</script>

<style>
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
#app {
  height: 100%;
}
.app-container {
  height: 100vh;
}
.app-aside {
  background-color: #1d1e1f;
  border-right: 1px solid #363637;
}
.logo {
  padding: 20px 16px;
  text-align: center;
  border-bottom: 1px solid #363637;
}
.logo h2 {
  color: #409eff;
  margin: 0;
  font-size: 18px;
}
.logo .subtitle {
  color: #909399;
  font-size: 11px;
  margin: 4px 0 0;
}
.app-menu {
  border-right: none;
  background-color: #1d1e1f;
}
.app-menu .el-menu-item {
  color: #bfcbd9;
}
.app-menu .el-menu-item:hover {
  background-color: #263445;
}
.app-menu .el-menu-item.is-active {
  color: #409eff;
  background-color: #263445;
}
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  background-color: #fff;
  height: 56px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
}
.app-main {
  background-color: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}
</style>
