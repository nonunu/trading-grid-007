<template>
  <div class="strategy-page">
    <!-- 网格状态 -->
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="section-title">网格状态</span>
          <el-button type="primary" size="small" @click="loadGridStatus">
            <el-icon><Refresh /></el-icon>刷新网格状态
          </el-button>
        </div>
      </template>

      <el-empty v-if="!gridStatus.length" description="暂无活跃股票配置" />
      <el-row v-else :gutter="12">
        <el-col v-for="(stock, idx) in gridStatus" :key="stock.stock_code"
          :xs="24" :sm="12" :md="8" :lg="8">
          <div class="stock-card" :class="'card-color-' + (idx % 3)">
            <div class="card-title">{{ stock.stock_code }}</div>
            <div class="card-price">最新价格：{{ stock.last_price ? stock.last_price.toFixed(3) : '—' }}</div>
            <div class="card-metric">
              满仓数量：{{ stock.all_full_qty }}股 | 当前仓位：{{ stock.all_position_qty }}股，占比 {{ stock.all_position_pct }}%
            </div>
            <div class="card-sub">
              <div class="sub-title">做多网格：</div>
              <div class="sub-detail">
                满仓数量：{{ stock.multi_full_qty }}股 | 当前仓位：{{ stock.multi_position_qty }}股，占比 {{ stock.multi_position_pct }}%
              </div>
            </div>
            <div class="card-sub">
              <div class="sub-title">做空网格：</div>
              <div class="sub-detail">
                满仓数量：{{ stock.short_full_qty }}股 | 当前仓位：{{ stock.short_position_qty }}股，占比 {{ stock.short_position_pct }}%
              </div>
            </div>
            <div class="card-holding">
              <span>持仓数量：</span>
              <span :class="holdingClass(stock)">{{ stock.holding_qty !== null ? stock.holding_qty + '股' : '—' }}</span>
              <span> | 满仓数量：</span>
              <span :class="holdingClass(stock)">{{ stock.all_full_qty }}股</span>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'

interface GridStatusItem {
  stock_code: string
  last_price: number | null
  all_full_qty: number
  all_position_qty: number
  all_position_pct: number
  multi_full_qty: number
  multi_position_qty: number
  multi_position_pct: number
  short_full_qty: number
  short_position_qty: number
  short_position_pct: number
  holding_qty: number | null
}

const gridStatus = ref<GridStatusItem[]>([])

function holdingClass(stock: GridStatusItem) {
  if (stock.holding_qty === null) return ''
  return stock.holding_qty !== stock.all_full_qty ? 'holding-mismatch' : 'holding-match'
}

async function loadGridStatus() {
  try {
    const data = await api.get('/grid_status') as GridStatusItem[]
    gridStatus.value = data
  } catch {
    // API not ready
  }
}

onMounted(loadGridStatus)
</script>

<style scoped>
.strategy-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
}

.stock-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: #fff;
  border-left: 4px solid #409eff;
}
.card-color-0 { border-left-color: #409eff; }
.card-color-1 { border-left-color: #67c23a; }
.card-color-2 { border-left-color: #e6a23c; }

.card-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 6px;
  color: #303133;
}
.card-price {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}
.card-metric {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}
.card-sub {
  margin-bottom: 4px;
}
.sub-title {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
}
.sub-detail {
  font-size: 12px;
  color: #606266;
  padding-left: 12px;
}
.card-holding {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #e4e7ed;
  font-size: 12px;
  color: #606266;
}
.holding-value {
  color: #f56c6c;
  font-weight: 700;
}
.holding-mismatch {
  color: #f56c6c;
  font-weight: 700;
}
.holding-match {
  color: #303133;
  font-weight: 600;
}
</style>
