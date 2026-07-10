<template>
  <div class="config-page">
    <el-row :gutter="12" style="height: calc(100vh - 150px)">
      <!-- 左侧: 股票列表 -->
      <el-col :span="5" style="height: 100%">
        <el-card shadow="hover" style="height: 100%; display: flex; flex-direction: column">
          <template #header>
            <span class="section-title">股票列表</span>
          </template>
          <el-table :data="configs" stripe size="small" highlight-current-row
            @current-change="onStockSelect" style="flex: 1">
            <el-table-column prop="stock_code" label="股票代码" width="110" />
            <el-table-column prop="direction" label="策略方向" width="70" />
            <el-table-column label="状态" width="50">
              <template #default="{ row }">
                <span :style="{ color: row.is_active ? '#67c23a' : '#909399' }">
                  {{ row.is_active ? '启用' : '禁用' }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="stock-actions">
            <el-button size="small" type="primary" @click="onAddStock">+ 添加股票</el-button>
            <el-button size="small" type="danger" @click="onDeleteStock">- 删除股票</el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧: Tab 面板 -->
      <el-col :span="19" style="height: 100%">
        <el-card shadow="hover" style="height: 100%">
          <el-tabs v-model="activeTab">
            <!-- Tab 1: 股票配置 -->
            <el-tab-pane label="股票配置" name="config">
              <div v-if="!currentStock" class="empty-hint">请在左侧选择一只股票</div>
              <div v-else class="stock-config-detail">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="股票代码">{{ currentConfig.stock_code }}</el-descriptions-item>
                  <el-descriptions-item label="市场">{{ currentConfig.market }}</el-descriptions-item>
                  <el-descriptions-item label="策略方向">{{ currentConfig.direction }}</el-descriptions-item>
                  <el-descriptions-item label="最新价格">{{ currentConfig.last_price || '—' }}</el-descriptions-item>
                  <el-descriptions-item label="买单网格数">{{ currentConfig.buy_cell_count }}</el-descriptions-item>
                  <el-descriptions-item label="卖单网格数">{{ currentConfig.sell_cell_count }}</el-descriptions-item>
                  <el-descriptions-item label="下单范围阈值">{{ currentConfig.place_order_scope }}</el-descriptions-item>
                  <el-descriptions-item label="最小交易单位">{{ currentConfig.min_lot_size }}</el-descriptions-item>
                </el-descriptions>
                <el-button size="small" style="margin-top: 12px" @click="onEditConfig">编辑配置</el-button>
              </div>
            </el-tab-pane>

            <!-- Tab 2: 网格单元格 -->
            <el-tab-pane label="网格单元格" name="cells">
              <div v-if="!currentStock" class="empty-hint">请在左侧选择一只股票</div>
              <div v-else>
                <!-- 筛选栏 -->
                <el-form :inline="true" size="small" class="cell-filter">
                  <el-form-item label="策略类型:">
                    <el-select v-model="cellFilter.strategyType" style="width: 100px" @change="loadCells">
                      <el-option label="MULTI" value="MULTI" />
                      <el-option label="SHORT" value="SHORT" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="类型:">
                    <el-select v-model="cellFilter.cellType" style="width: 90px" @change="loadCells">
                      <el-option label="全部" value="" />
                      <el-option label="BUY" value="BUY" />
                      <el-option label="SELL" value="SELL" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="价格:">
                    <el-input v-model="cellFilter.minPrice" placeholder="最小" style="width: 65px" />
                  </el-form-item>
                  <el-form-item><span>-</span></el-form-item>
                  <el-form-item>
                    <el-input v-model="cellFilter.maxPrice" placeholder="最大" style="width: 65px" />
                  </el-form-item>
                  <el-form-item label="状态:">
                    <el-select v-model="cellFilter.status" style="width: 90px">
                      <el-option label="全部" value="" />
                      <el-option label="未下单" value="NONE" />
                      <el-option label="已成交" value="FILLED_ALL" />
                      <el-option label="已提交" value="SUBMITTED" />
                    </el-select>
                  </el-form-item>
                  <el-form-item>
                    <el-button @click="loadCells">筛选</el-button>
                    <el-button @click="clearCellFilter">清除</el-button>
                  </el-form-item>
                </el-form>

                <!-- 单元格表格 -->
                <el-table :data="filteredCells" stripe border size="small" max-height="400"
                  highlight-current-row @current-change="onCellSelect">
                  <el-table-column prop="id" label="ID" width="55" />
                  <el-table-column label="类型" width="80">
                    <template #default="{ row }">
                      <span :style="{ color: row.parent_cell_id ? '#67c23a' : '#409eff', fontWeight: 600 }">
                        {{ row.cell_type === 'BUY' ? '买入' : '卖出' }}({{ row.parent_cell_id ? '子' : '父' }})
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column label="父ID" width="50">
                    <template #default="{ row }">{{ row.parent_cell_id || '-' }}</template>
                  </el-table-column>
                  <el-table-column label="价格" width="100" sortable sort-by="price">
                    <template #default="{ row }">
                      <el-input-number v-if="isCellEditable(row)" v-model="row.price"
                        :min="0.001" :step="0.01" :precision="3" :controls="false" size="small"
                        style="width: 85px" />
                      <span v-else>{{ row.price?.toFixed(3) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="数量" width="85">
                    <template #default="{ row }">
                      <el-input-number v-if="isCellEditable(row)" v-model="row.qty"
                        :min="1" :step="100" :controls="false" size="small"
                        style="width: 70px" />
                      <span v-else>{{ row.qty }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="订单状态" width="110">
                    <template #default="{ row }">
                      <span v-if="row.order_status">{{ row.order_status }}</span>
                      <span v-else style="color: #c0c4cc">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="成交量" width="70">
                    <template #default="{ row }">{{ row.dealt_qty || 0 }}</template>
                  </el-table-column>
                  <el-table-column label="成交均价" width="85">
                    <template #default="{ row }">{{ row.dealt_avg_price ? row.dealt_avg_price.toFixed(3) : '-' }}</template>
                  </el-table-column>
                  <el-table-column label="分配量" width="75">
                    <template #default="{ row }">
                      <el-input-number v-if="isCellEditable(row)" v-model="row.allocated_qty"
                        :min="0" :step="100" :controls="false" size="small"
                        style="width: 60px" />
                      <span v-else>{{ row.allocated_qty || 0 }}</span>
                    </template>
                  </el-table-column>
                </el-table>

                <!-- 操作按钮 -->
                <div class="cell-actions">
                  <el-button size="small" type="primary" @click="onAddParentCell">+ 添加父单元格</el-button>
                  <el-button size="small" type="success" @click="onAddChildCell">+ 添加子单元格</el-button>
                  <el-button size="small" type="danger" @click="onDeleteCell">- 删除单元格(级联)</el-button>
                  <el-button size="small" @click="onSaveCellEdits">💾 保存修改</el-button>
                  <el-button size="small" class="split-btn" @click="onSplitParentCell">✂️ 拆分父单元格</el-button>
                  <el-button size="small" @click="onClearCellOrder">清除订单信息</el-button>
                </div>
              </div>
            </el-tab-pane>

            <!-- Tab 3: 成交记录 -->
            <el-tab-pane label="成交记录" name="orders">
              <div v-if="!currentStock" class="empty-hint">请在左侧选择一只股票</div>
              <div v-else>
                <el-table :data="filledOrders" stripe size="small" max-height="450">
                  <el-table-column prop="completed_at" label="完成时间" width="155" />
                  <el-table-column label="买入价" width="80">
                    <template #default="{ row }">{{ (row.buy_dealt_avg_price || 0).toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="卖出价" width="80">
                    <template #default="{ row }">{{ (row.sell_dealt_avg_price || 0).toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="买入金额" width="95">
                    <template #default="{ row }">{{ (row.buy_amount || 0).toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="卖出金额" width="95">
                    <template #default="{ row }">{{ (row.sell_amount || 0).toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="利润" width="90">
                    <template #default="{ row }">
                      <span :style="{ color: (row.profit_diff || 0) >= 0 ? '#67c23a' : '#f56c6c', fontWeight: 600 }">
                        {{ (row.profit_diff || 0).toFixed(2) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="strategy_type" label="策略" width="70" />
                </el-table>
              </div>
            </el-tab-pane>

            <!-- Tab 4: 自救管理 -->
            <el-tab-pane label="自救管理" name="rescue">
              <div v-if="!currentStock" class="empty-hint">请在左侧选择一只股票</div>
              <div v-else class="rescue-panel">
                <!-- 上半部分: 可转换的 MULTI 买入单元格 -->
                <div class="rescue-section">
                  <div class="rescue-section-title">可转换的 MULTI 买入单元格（已成交）</div>
                  <el-table :data="availableCells" stripe size="small" max-height="180"
                    highlight-current-row @current-change="onAvailableCellSelect">
                    <el-table-column prop="cell_id" label="Cell ID" width="80" />
                    <el-table-column label="网格价格" width="100">
                      <template #default="{ row }">{{ row.price.toFixed(3) }}</template>
                    </el-table-column>
                    <el-table-column label="成交均价" width="100">
                      <template #default="{ row }">{{ row.dealt_avg_price.toFixed(3) }}</template>
                    </el-table-column>
                    <el-table-column label="成交数量" width="90">
                      <template #default="{ row }">{{ row.dealt_qty }}</template>
                    </el-table-column>
                    <el-table-column label="子单元格" width="80">
                      <template #default="{ row }">{{ row.child_count }}个</template>
                    </el-table-column>
                    <el-table-column label="状态" width="70">
                      <template #default>
                        <span style="color: #e6a23c; font-weight: 600">可转仓</span>
                      </template>
                    </el-table-column>
                  </el-table>
                  <div class="rescue-actions">
                    <el-button type="warning" size="small" @click="onTransfer">转仓到 SHORT →</el-button>
                    <el-button size="small" @click="loadAvailableCells">刷新</el-button>
                  </div>
                </div>

                <!-- 下半部分: 自救转换记录 -->
                <div class="rescue-section">
                  <div class="rescue-section-title">自救转换记录</div>
                  <el-table :data="rescueRecords" stripe size="small" max-height="180"
                    highlight-current-row @current-change="onRescueRecordSelect">
                    <el-table-column prop="id" label="记录ID" width="65" />
                    <el-table-column prop="multi_parent_cell_id" label="MULTI Cell" width="90" />
                    <el-table-column label="买入均价" width="85">
                      <template #default="{ row }">{{ (row.buy_dealt_avg_price || 0).toFixed(3) }}</template>
                    </el-table-column>
                    <el-table-column label="SHORT 卖价" width="90">
                      <template #default="{ row }">{{ (row.short_price || 0).toFixed(3) }}</template>
                    </el-table-column>
                    <el-table-column prop="qty" label="数量" width="70" />
                    <el-table-column prop="short_parent_cell_id" label="SHORT Cell" width="85" />
                    <el-table-column prop="created_at" label="转仓时间" width="145" />
                    <el-table-column label="状态" width="60">
                      <template #default="{ row }">
                        <span :style="{ color: row.status === 'ACTIVE' ? '#67c23a' : '#909399', fontWeight: 600 }">
                          {{ row.status === 'ACTIVE' ? '活跃' : '已还原' }}
                        </span>
                      </template>
                    </el-table-column>
                  </el-table>
                  <div class="rescue-actions">
                    <el-checkbox v-model="showRestored" @change="loadRescueRecords">显示已还原记录</el-checkbox>
                    <el-button type="primary" size="small" @click="onRestore">← 还原到 MULTI</el-button>
                    <el-button size="small" @click="loadRescueRecords">刷新</el-button>
                  </div>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <!-- 底部: 数据库维护 -->
    <el-card shadow="hover" class="db-maintenance">
      <div class="db-bar">
        <span class="db-path">数据库路径: backend/trading_grid.db</span>
        <div class="db-actions">
          <el-button size="small" type="warning" @click="onClearFilledOrders">清理成交记录</el-button>
          <el-button size="small" type="warning" @click="onClearAllCells">清理网格单元格</el-button>
        </div>
      </div>
    </el-card>

    <!-- 添加股票对话框 -->
    <el-dialog v-model="showStockDialog" :title="editMode ? '编辑配置' : '添加股票'" width="450px">
      <el-form :model="stockForm" label-width="100px" size="small">
        <el-form-item label="股票代码">
          <el-input v-model="stockForm.stock_code" :disabled="editMode" placeholder="HK.08017 / 600519.SH" />
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="stockForm.direction" style="width: 100%">
            <el-option label="双向 (ALL)" value="ALL" />
            <el-option label="仅做多 (MULTI)" value="MULTI" />
            <el-option label="仅做空 (SHORT)" value="SHORT" />
          </el-select>
        </el-form-item>
        <el-form-item label="买入格数">
          <el-input-number v-model="stockForm.buy_cell_count" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="卖出格数">
          <el-input-number v-model="stockForm.sell_cell_count" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="偏离阈值">
          <el-input-number v-model="stockForm.place_order_scope" :min="0.01" :step="0.05" :precision="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showStockDialog = false">取消</el-button>
        <el-button type="primary" @click="saveStock">保存</el-button>
      </template>
    </el-dialog>

    <!-- 添加父单元格对话框 -->
    <el-dialog v-model="showParentCellDialog" title="添加父单元格" width="400px">
      <el-form :model="cellForm" label-width="80px" size="small">
        <el-form-item label="价格">
          <el-input-number v-model="cellForm.price" :min="0.001" :step="0.1" :precision="3" style="width: 100%" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="cellForm.qty" :min="1" :step="100" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showParentCellDialog = false">取消</el-button>
        <el-button type="primary" @click="saveParentCell">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加子单元格对话框 -->
    <el-dialog v-model="showChildCellDialog" title="添加子单元格" width="400px">
      <el-form :model="cellForm" label-width="80px" size="small">
        <el-form-item label="父单元格">{{ selectedCell?.id }}</el-form-item>
        <el-form-item label="价格">
          <el-input-number v-model="cellForm.price" :min="0.001" :step="0.1" :precision="3" style="width: 100%" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="cellForm.qty" :min="1" :step="100" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showChildCellDialog = false">取消</el-button>
        <el-button type="primary" @click="saveChildCell">确定</el-button>
      </template>
    </el-dialog>

    <!-- 转仓对话框 -->
    <el-dialog v-model="showTransferDialog" title="MULTI → SHORT 转仓" width="420px">
      <el-form label-width="100px" size="small">
        <el-form-item label="原网格价格">{{ selectedAvailable?.price?.toFixed(3) }}</el-form-item>
        <el-form-item label="成交均价">{{ selectedAvailable?.dealt_avg_price?.toFixed(3) }}</el-form-item>
        <el-form-item label="成交数量">{{ selectedAvailable?.dealt_qty }}</el-form-item>
        <el-form-item label="SHORT卖价">
          <el-input-number v-model="transferForm.short_price" :min="0.001" :step="0.01" :precision="3" style="width: 100%" />
        </el-form-item>
        <el-form-item label="转仓数量">
          <el-input-number v-model="transferForm.qty" :min="1" :max="selectedAvailable?.dealt_qty || 99999" :step="100" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTransferDialog = false">取消</el-button>
        <el-button type="warning" @click="doTransfer">确认转仓</el-button>
      </template>
    </el-dialog>

    <!-- 拆分父单元格对话框 -->
    <el-dialog v-model="showSplitDialog" title="拆分父单元格" width="500px">
      <div style="margin-bottom: 12px; color: #606266; font-size: 13px">
        原单元格: ID={{ selectedCell?.id }}, 成交量={{ selectedCell?.dealt_qty || 0 }}, 成交均价={{ selectedCell?.dealt_avg_price?.toFixed(3) || '-' }}
      </div>
      <el-form size="small">
        <div v-for="(split, idx) in splitForm.splits" :key="idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
          <el-input-number v-model="split.price" :min="0.001" :step="0.1" :precision="3" placeholder="价格" style="flex: 1" />
          <el-input-number v-model="split.qty" :min="1" :step="100" placeholder="数量" style="flex: 1" />
          <el-button size="small" type="danger" circle @click="splitForm.splits.splice(idx, 1)">×</el-button>
        </div>
        <el-button size="small" @click="splitForm.splits.push({ price: selectedCell?.price || 1, qty: 100 })">+ 添加一笔</el-button>
        <div style="margin-top: 8px; color: #909399; font-size: 12px">
          拆分总量: {{ splitForm.splits.reduce((s: number, x: {qty: number}) => s + x.qty, 0) }} / {{ selectedCell?.dealt_qty || 0 }}
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showSplitDialog = false">取消</el-button>
        <el-button type="primary" @click="doSplit">确认拆分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

// Types
interface StockConfig {
  stock_code: string; market: string; direction: string
  buy_cell_count: number; sell_cell_count: number
  order_query_period: number; place_order_scope: number
  last_price: number | null; min_lot_size: number; is_active: number
}
interface Cell {
  id: number; stock_code: string; strategy_type: string; cell_type: string
  parent_cell_id: number | null; price: number; qty: number
  allocated_qty: number | null; order_id: string | null; order_status: string | null
  dealt_avg_price: number | null; dealt_qty: number | null
}
interface FilledOrder {
  completed_at: string; buy_dealt_avg_price: number; sell_dealt_avg_price: number
  buy_amount: number; sell_amount: number; profit_diff: number; strategy_type: string
}
interface RescueRecord {
  id: number; stock_code: string
  multi_parent_cell_id: number; short_parent_cell_id: number
  short_price: number; qty: number; buy_dealt_avg_price: number
  created_at: string; restored_at: string | null; status: string
  // 新结构字段 (迁移后可能存在)
  source_cell_id: number | null; target_cell_id: number | null
  transfer_price: number | null; transfer_qty: number | null
  snapshot_dealt_avg_price: number | null
}

// State
const configs = ref<StockConfig[]>([])
const currentStock = ref('')
const currentConfig = ref<StockConfig>({} as StockConfig)
const activeTab = ref('cells')

const cells = ref<Cell[]>([])
const selectedCell = ref<Cell | null>(null)
const filledOrders = ref<FilledOrder[]>([])
const rescueRecords = ref<RescueRecord[]>([])

const cellFilter = reactive({
  strategyType: 'MULTI',
  cellType: '',
  minPrice: '',
  maxPrice: '',
  status: '',
})

const showStockDialog = ref(false)
const editMode = ref(false)
const stockForm = reactive({ stock_code: '', direction: 'ALL', buy_cell_count: 3, sell_cell_count: 3, place_order_scope: 0.1 })

const showParentCellDialog = ref(false)
const showChildCellDialog = ref(false)
const cellForm = reactive({ price: 1.0, qty: 100 })

// Rescue state
interface AvailableCell {
  cell_id: number; price: number; dealt_avg_price: number; dealt_qty: number; child_count: number; status: string
}
const availableCells = ref<AvailableCell[]>([])
const selectedAvailable = ref<AvailableCell | null>(null)
const selectedRescueRecord = ref<RescueRecord | null>(null)
const showRestored = ref(false)
const showTransferDialog = ref(false)
const transferForm = reactive({ short_price: 1.0, qty: 100 })

// Split state
const showSplitDialog = ref(false)
const splitForm = reactive({ splits: [] as Array<{price: number; qty: number}> })

// Computed
const filteredCells = computed(() => {
  let result = cells.value
  if (cellFilter.cellType) result = result.filter(c => c.cell_type === cellFilter.cellType)
  if (cellFilter.minPrice) result = result.filter(c => c.price >= parseFloat(cellFilter.minPrice))
  if (cellFilter.maxPrice) result = result.filter(c => c.price <= parseFloat(cellFilter.maxPrice))
  if (cellFilter.status === 'NONE') result = result.filter(c => !c.order_status)
  else if (cellFilter.status) result = result.filter(c => c.order_status === cellFilter.status)
  return result
})

// Data Loading
async function loadConfigs() {
  try { configs.value = await api.get('/configs') as StockConfig[] } catch { /* */ }
}

async function onStockSelect(row: StockConfig | null) {
  if (!row) return
  currentStock.value = row.stock_code
  currentConfig.value = row
  await loadCells()
  await loadFilledOrders()
  await loadAvailableCells()
  await loadRescueRecords()
}

async function loadCells() {
  if (!currentStock.value) return
  try {
    const data = await api.get(`/cells?stock_code=${currentStock.value}&strategy_type=${cellFilter.strategyType}`) as Cell[]
    cells.value = data
  } catch { /* */ }
}

function clearCellFilter() {
  cellFilter.cellType = ''; cellFilter.minPrice = ''; cellFilter.maxPrice = ''; cellFilter.status = ''
}

function onCellSelect(row: Cell | null) { selectedCell.value = row }

async function loadFilledOrders() {
  if (!currentStock.value) return
  try { filledOrders.value = await api.get(`/dashboard/filled_orders?stock_code=${currentStock.value}&limit=200`) as FilledOrder[] } catch { /* */ }
}

async function loadRescueRecords() {
  if (!currentStock.value) return
  try {
    rescueRecords.value = await api.get(`/rescue/records?stock_code=${currentStock.value}&include_restored=${showRestored.value}`) as RescueRecord[]
  } catch { /* */ }
}
async function loadAvailableCells() {
  if (!currentStock.value) return
  try {
    availableCells.value = await api.get(`/rescue/available?stock_code=${currentStock.value}`) as AvailableCell[]
  } catch { /* */ }
}
function onAvailableCellSelect(row: AvailableCell | null) { selectedAvailable.value = row }
function onRescueRecordSelect(row: RescueRecord | null) { selectedRescueRecord.value = row }

function onTransfer() {
  if (!selectedAvailable.value) { ElMessage.warning('请先选择要转仓的单元格'); return }
  transferForm.short_price = selectedAvailable.value.price
  transferForm.qty = selectedAvailable.value.dealt_qty
  showTransferDialog.value = true
}
async function doTransfer() {
  if (!selectedAvailable.value) return
  try {
    await api.post('/rescue/transfer', { cell_id: selectedAvailable.value.cell_id, short_price: transferForm.short_price, qty: transferForm.qty })
    ElMessage.success('转仓完成'); showTransferDialog.value = false
    await loadAvailableCells(); await loadRescueRecords(); await loadCells()
  } catch (e: unknown) { ElMessage.error('转仓失败') }
}
async function onRestore() {
  if (!selectedRescueRecord.value) { ElMessage.warning('请先选择要还原的记录'); return }
  try {
    await ElMessageBox.confirm('确定还原该转仓记录？SHORT 端单元格将被删除。', '确认还原', { type: 'warning' })
    await api.post('/rescue/restore', { rescue_record_id: selectedRescueRecord.value.id })
    ElMessage.success('还原完成')
    await loadAvailableCells(); await loadRescueRecords(); await loadCells()
  } catch { /* cancelled */ }
}

// Save edits
function isCellEditable(row: Cell): boolean {
  // 可编辑条件: 没有活跃订单，或者订单已完结
  const editableStatuses = [null, undefined, '', 'FILLED_ALL', 'CANCELLED_PART', 'TRANSFERRED']
  return editableStatuses.includes(row.order_status as string)
}

async function onSaveCellEdits() {
  if (!currentStock.value || !filteredCells.value.length) {
    ElMessage.warning('没有可保存的数据')
    return
  }

  // 收集所有可编辑行的当前值
  const updates: Record<number, { price?: number; qty?: number; allocated_qty?: number }> = {}
  for (const cell of filteredCells.value) {
    if (isCellEditable(cell)) {
      updates[cell.id] = {
        price: cell.price,
        qty: cell.qty,
        allocated_qty: cell.allocated_qty || 0,
      }
    }
  }

  if (Object.keys(updates).length === 0) {
    ElMessage.info('没有可保存的修改')
    return
  }

  try {
    const res = await api.post('/cells/batch_update', { updates }) as { success: boolean; updated_count: number }
    ElMessage.success(`保存成功，更新了 ${res.updated_count} 个单元格`)
    await loadCells()
  } catch {
    ElMessage.error('保存失败')
  }
}

// Split
function onSplitParentCell() {
  if (!selectedCell.value) { ElMessage.warning('请先选中一个父单元格'); return }
  if (selectedCell.value.parent_cell_id) { ElMessage.warning('只能拆分父单元格'); return }
  if (!selectedCell.value.dealt_qty) { ElMessage.warning('只能拆分已成交的单元格'); return }
  splitForm.splits = [{ price: selectedCell.value.price, qty: 100 }]
  showSplitDialog.value = true
}
async function doSplit() {
  if (!selectedCell.value) return
  try {
    await api.post('/cells/split', { cell_id: selectedCell.value.id, splits: splitForm.splits })
    ElMessage.success('拆分完成'); showSplitDialog.value = false; await loadCells()
  } catch { ElMessage.error('拆分失败') }
}

// Stock CRUD
function onAddStock() {
  editMode.value = false
  stockForm.stock_code = ''; stockForm.direction = 'ALL'
  stockForm.buy_cell_count = 3; stockForm.sell_cell_count = 3; stockForm.place_order_scope = 0.1
  showStockDialog.value = true
}
function onEditConfig() {
  editMode.value = true
  Object.assign(stockForm, { stock_code: currentConfig.value.stock_code, direction: currentConfig.value.direction, buy_cell_count: currentConfig.value.buy_cell_count, sell_cell_count: currentConfig.value.sell_cell_count, place_order_scope: currentConfig.value.place_order_scope })
  showStockDialog.value = true
}
async function saveStock() {
  try {
    if (editMode.value) { await api.put(`/configs/${stockForm.stock_code}`, stockForm) }
    else { await api.post('/configs', stockForm) }
    ElMessage.success('保存成功'); showStockDialog.value = false; await loadConfigs()
  } catch { ElMessage.error('保存失败') }
}
async function onDeleteStock() {
  if (!currentStock.value) { ElMessage.warning('请先选择股票'); return }
  try {
    await ElMessageBox.confirm('删除将同时清除所有关联网格，确定？', '确认', { type: 'warning' })
    await api.delete(`/configs/${currentStock.value}`)
    ElMessage.success('已删除'); currentStock.value = ''; await loadConfigs()
  } catch { /* */ }
}

// Cell CRUD
function onAddParentCell() {
  if (!currentStock.value) { ElMessage.warning('请先选择股票'); return }
  cellForm.price = 1.0; cellForm.qty = 100; showParentCellDialog.value = true
}
async function saveParentCell() {
  const cellType = cellFilter.strategyType === 'MULTI' ? 'BUY' : 'SELL'
  try {
    await api.post('/cells', { stock_code: currentStock.value, strategy_type: cellFilter.strategyType, cell_type: cellType, price: cellForm.price, qty: cellForm.qty })
    ElMessage.success('父单元格已添加'); showParentCellDialog.value = false; await loadCells()
  } catch { ElMessage.error('添加失败') }
}
function onAddChildCell() {
  if (!selectedCell.value) { ElMessage.warning('请先选中一个父单元格'); return }
  if (selectedCell.value.parent_cell_id) { ElMessage.warning('请选择父单元格'); return }
  cellForm.price = 1.0; cellForm.qty = 100; showChildCellDialog.value = true
}
async function saveChildCell() {
  if (!selectedCell.value) return
  const cellType = cellFilter.strategyType === 'MULTI' ? 'SELL' : 'BUY'
  try {
    await api.post('/cells', { stock_code: currentStock.value, strategy_type: cellFilter.strategyType, cell_type: cellType, price: cellForm.price, qty: cellForm.qty, parent_cell_id: selectedCell.value.id })
    ElMessage.success('子单元格已添加'); showChildCellDialog.value = false; await loadCells()
  } catch { ElMessage.error('添加失败') }
}
async function onDeleteCell() {
  if (!selectedCell.value) { ElMessage.warning('请先选中单元格'); return }
  try {
    await ElMessageBox.confirm(`删除单元格 ID=${selectedCell.value.id}？如果是父单元格将级联删除子单元格。`, '确认', { type: 'warning' })
    await api.delete(`/cells/${selectedCell.value.id}`)
    ElMessage.success('已删除'); await loadCells()
  } catch { /* */ }
}
async function onClearCellOrder() {
  if (!selectedCell.value) { ElMessage.warning('请先选中单元格'); return }
  try {
    await ElMessageBox.confirm('清除该单元格的订单信息？', '确认', { type: 'warning' })
    await api.post(`/cells/${selectedCell.value.id}/clear`)
    ElMessage.success('已清除'); await loadCells()
  } catch { /* */ }
}

// DB Maintenance
async function onClearFilledOrders() {
  try {
    await ElMessageBox.confirm('确定清理所有成交记录？此操作不可恢复！', '确认', { type: 'warning' })
    ElMessage.success('功能开发中')
  } catch { /* */ }
}
async function onClearAllCells() {
  try {
    await ElMessageBox.confirm('确定清理所有网格单元格？此操作不可恢复！', '确认', { type: 'warning' })
    ElMessage.success('功能开发中')
  } catch { /* */ }
}

onMounted(loadConfigs)
</script>

<style scoped>
.config-page { display: flex; flex-direction: column; gap: 10px; }
.section-title { font-weight: 600; font-size: 14px; }
.stock-actions { display: flex; gap: 8px; margin-top: 8px; }
.empty-hint { color: #909399; text-align: center; padding: 40px; }
.stock-config-detail { padding: 8px; }
.cell-filter { margin-bottom: 8px; }
.cell-filter :deep(.el-form-item) { margin-bottom: 4px; margin-right: 8px; }
.cell-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.db-maintenance { margin-top: 0; }
.db-bar { display: flex; justify-content: space-between; align-items: center; }
.db-path { font-size: 12px; color: #909399; }
.db-actions { display: flex; gap: 8px; }
.rescue-panel { display: flex; flex-direction: column; gap: 12px; }
.rescue-section { border: 1px solid #ebeef5; border-radius: 4px; padding: 10px; }
.rescue-section-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.rescue-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.split-btn { background-color: #9c27b0 !important; color: #fff !important; border-color: #9c27b0 !important; }
.split-btn:hover { background-color: #7b1fa2 !important; border-color: #7b1fa2 !important; }
</style>
