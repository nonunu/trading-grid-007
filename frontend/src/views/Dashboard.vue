<template>
  <div class="dashboard">
    <!-- 顶部筛选栏 -->
    <el-card shadow="hover" class="filter-bar">
      <el-form :inline="true" size="small">
        <el-form-item label="股票代码">
          <el-select v-model="filter.stockCode" placeholder="全部股票" clearable style="width: 150px">
            <el-option label="全部股票" value="" />
            <el-option v-for="s in stockList" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="filter.startDate" type="date" format="YYYY-MM-DD"
            value-format="YYYY-MM-DD" placeholder="开始日期" style="width: 150px" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="filter.endDate" type="date" format="YYYY-MM-DD"
            value-format="YYYY-MM-DD" placeholder="结束日期" style="width: 150px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">
            <el-icon><Search /></el-icon>应用筛选
          </el-button>
        </el-form-item>
        <el-form-item class="summary-info">
          <span class="profit-label">收益: </span>
          <span class="profit-value" :class="summary.total_profit >= 0 ? 'positive' : 'negative'">
            ¥{{ summary.total_profit.toFixed(2) }}
          </span>
          <span class="trade-label">; 成交次数: </span>
          <span class="trade-value">{{ summary.total_trades }}</span>
        </el-form-item>
        <el-form-item>
          <el-button @click="loadData">
            <el-icon><Refresh /></el-icon>刷新数据
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 每日收益趋势 -->
    <el-card shadow="hover" class="trend-card">
      <template #header><span class="section-title">每日收益趋势</span></template>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-table :data="trend.daily" stripe size="small" max-height="220">
            <el-table-column prop="period" label="日期" width="110" />
            <el-table-column label="收益" width="100">
              <template #default="{ row }">
                <span class="positive">¥{{ row.profit.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="交易次数" width="80" />
          </el-table>
        </el-col>
        <el-col :span="16">
          <v-chart :option="dailyChartOption" autoresize style="height: 220px" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 每周收益趋势 -->
    <el-card shadow="hover" class="trend-card">
      <template #header><span class="section-title">每周收益趋势</span></template>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-table :data="trend.weekly" stripe size="small" max-height="220">
            <el-table-column prop="period" label="周数" width="100" />
            <el-table-column label="收益" width="100">
              <template #default="{ row }">
                <span class="positive">¥{{ row.profit.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="交易次数" width="80" />
          </el-table>
        </el-col>
        <el-col :span="16">
          <v-chart :option="weeklyChartOption" autoresize style="height: 220px" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 每月收益趋势 -->
    <el-card shadow="hover" class="trend-card">
      <template #header><span class="section-title">每月收益趋势</span></template>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-table :data="trend.monthly" stripe size="small" max-height="220">
            <el-table-column prop="period" label="月份" width="100" />
            <el-table-column label="收益" width="110">
              <template #default="{ row }">
                <span class="positive">¥{{ row.profit.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="交易次数" width="80" />
          </el-table>
        </el-col>
        <el-col :span="16">
          <v-chart :option="monthlyChartOption" autoresize style="height: 220px" />
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, TitleComponent } from 'echarts/components'
import api from '@/api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, TitleComponent])

interface TrendItem {
  period: string
  profit: number
  count: number
}

const filter = reactive({
  stockCode: '',
  startDate: '',
  endDate: '',
})

const summary = reactive({
  total_profit: 0,
  total_trades: 0,
})

const stockList = ref<string[]>([])

const trend = reactive({
  daily: [] as TrendItem[],
  weekly: [] as TrendItem[],
  monthly: [] as TrendItem[],
})

function buildChartOption(data: TrendItem[], title: string, color: string) {
  return {
    title: { text: title, left: 'center', textStyle: { fontSize: 13 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number }>) => {
        const p = params[0]
        return `${p.name}<br/>收益: ¥${p.value.toFixed(2)}`
      },
    },
    grid: { left: 50, right: 20, top: 35, bottom: 30 },
    xAxis: {
      type: 'category',
      data: data.map(d => d.period),
      axisLabel: { fontSize: 10, rotate: data.length > 15 ? 45 : 0 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10 },
      name: '收益 (¥)',
      nameTextStyle: { fontSize: 10 },
    },
    series: [{
      type: 'line',
      data: data.map(d => d.profit),
      smooth: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
    }],
  }
}

const dailyChartOption = computed(() => buildChartOption(trend.daily, '每日收益趋势', '#409eff'))
const weeklyChartOption = computed(() => buildChartOption(trend.weekly, '每周收益趋势', '#67c23a'))
const monthlyChartOption = computed(() => buildChartOption(trend.monthly, '每月收益趋势', '#e6a23c'))

async function loadData() {
  const params: Record<string, string> = {}
  if (filter.stockCode) params.stock_code = filter.stockCode
  if (filter.startDate) params.start_date = filter.startDate
  if (filter.endDate) params.end_date = filter.endDate
  const query = new URLSearchParams(params).toString()

  try {
    const s = await api.get(`/dashboard/summary?${query}`) as {
      total_profit: number; total_trades: number; stocks: Array<{ stock_code: string }>
    }
    summary.total_profit = s.total_profit
    summary.total_trades = s.total_trades
    stockList.value = s.stocks.map(x => x.stock_code)
  } catch { /* */ }

  try {
    const t = await api.get(`/dashboard/profit_trend?${query}`) as {
      daily: TrendItem[]; weekly: TrendItem[]; monthly: TrendItem[]
    }
    trend.daily = t.daily
    trend.weekly = t.weekly
    trend.monthly = t.monthly
  } catch { /* */ }
}

onMounted(loadData)
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar :deep(.el-form-item) {
  margin-bottom: 0;
}
.summary-info {
  margin-left: 20px !important;
}
.profit-label, .trade-label {
  color: #606266;
  font-size: 13px;
}
.profit-value {
  font-weight: 700;
  font-size: 14px;
}
.trade-value {
  font-weight: 700;
  font-size: 14px;
  color: #303133;
}
.positive { color: #67c23a; font-weight: 600; }
.negative { color: #f56c6c; font-weight: 600; }
.trend-card {
  margin-top: 0;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
}
</style>
