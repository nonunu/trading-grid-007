import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export interface StockConfig {
  stock_code: string
  market: string
  direction: string
  buy_cell_count: number
  sell_cell_count: number
  order_query_period: number
  place_order_scope: number
  last_price: number | null
  min_lot_size: number
  is_active: number
  created_at: string | null
  updated_at: string | null
}

export const useConfigStore = defineStore('config', () => {
  const configs = ref<StockConfig[]>([])
  const loading = ref(false)

  async function fetchConfigs() {
    loading.value = true
    try {
      const data = await api.get('/configs') as StockConfig[]
      configs.value = data
    } catch {
      // API not ready
    } finally {
      loading.value = false
    }
  }

  return { configs, loading, fetchConfigs }
})
