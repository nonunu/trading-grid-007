import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

interface StockPrice {
  stock_code: string
  last_price: number | null
  market: string
}

export const useEngineStore = defineStore('engine', () => {
  const running = ref(false)
  const strategiesCount = ref(0)
  const stocks = ref<string[]>([])
  const stockPrices = ref<StockPrice[]>([])

  async function fetchStatus() {
    try {
      const data = await api.get('/engine/status') as {
        running: boolean
        strategies_count: number
        stocks: string[]
      }
      running.value = data.running
      strategiesCount.value = data.strategies_count
      stocks.value = data.stocks
    } catch {
      // API not available yet
    }
  }

  async function start() {
    const data = await api.post('/engine/start') as { success: boolean; message: string }
    if (data.success) {
      running.value = true
    }
    return data
  }

  async function stop() {
    const data = await api.post('/engine/stop') as { success: boolean; message: string }
    if (data.success) {
      running.value = false
    }
    return data
  }

  function updateFromWs(wsData: { running: boolean; strategies_count: number; stocks: StockPrice[] }) {
    running.value = wsData.running
    strategiesCount.value = wsData.strategies_count
    stockPrices.value = wsData.stocks
  }

  return { running, strategiesCount, stocks, stockPrices, fetchStatus, start, stop, updateFromWs }
})
