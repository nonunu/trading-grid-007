<template>
  <div class="engine-control">
    <el-tag :type="engineStore.running ? 'success' : 'info'" class="status-tag">
      {{ engineStore.running ? '运行中' : '已停止' }}
    </el-tag>
    <el-tag type="warning" class="status-tag">
      策略: {{ engineStore.strategiesCount }}
    </el-tag>
    <el-button
      :type="engineStore.running ? 'danger' : 'success'"
      size="small"
      @click="toggleEngine"
      :loading="loading"
    >
      {{ engineStore.running ? '停止' : '启动' }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useEngineStore } from '@/stores/engine'

const engineStore = useEngineStore()
const loading = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  engineStore.fetchStatus()
  timer = setInterval(() => engineStore.fetchStatus(), 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

async function toggleEngine() {
  const action = engineStore.running ? '停止' : '启动'
  try {
    await ElMessageBox.confirm(
      `确定要${action}网格交易系统吗？`,
      `确认${action}`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    loading.value = true
    if (engineStore.running) {
      await engineStore.stop()
      ElMessage.success('交易系统已停止')
    } else {
      await engineStore.start()
      ElMessage.success('交易系统启动中...')
    }
  } catch {
    // cancelled
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.engine-control {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-tag {
  font-size: 12px;
}
</style>
