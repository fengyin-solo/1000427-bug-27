<template>
  <section class="page" data-module="membrane">
    <header class="page-head">
      <div>
        <h2>膜组件管理</h2>
        <p class="page-desc">维护膜组，围绕膜组编号、膜型号、膜面积、跨膜压差做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记膜组</button>
        <button class="btn" type="button" @click="exportRows">导出膜组件清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilter">
      <label class="filter-item">
        <span>膜组编号</span>
        <input v-model="keyword" placeholder="按膜组编号检索" />
      </label>
      <label class="filter-item">
        <span>膜组状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(row, column) }}</td>
          <td class="row-actions">
            <template v-if="allowedActions(row).length">
              <button
                v-for="action in allowedActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">已归档，无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条膜组件记录</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stat = { label: string; value: number }

const ENDPOINT = '/api/membrane'
const columns = ["膜组编号", "膜型号", "膜面积", "跨膜压差", "通量", "清洗周期", "投用日期", "膜组状态"]
const statuses = ["待投用", "运行中", "待清洗", "已更换"]
// 状态机：每个状态只暴露允许的动作；已更换为终态，不允许再确认投用
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  "待投用": ["确认投用", "更换膜组"],
  "运行中": ["提交清洗", "更换膜组"],
  "待清洗": ["确认投用", "更换膜组"],
  "已更换": [],
}
const EMPTY_STATS: Stat[] = [
  { label: "膜组总数", value: 0 },
  { label: "运行膜组", value: 0 },
  { label: "待清洗膜组", value: 0 },
  { label: "已更换膜组", value: 0 },
  { label: "跨膜压差均值", value: 0 },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Stat[]>(EMPTY_STATS)
const errorMessage = ref('')
const successMessage = ref('')
const keyword = ref('')
const status = ref('')
const hasFilter = computed(() => keyword.value.trim() !== '' || status.value !== '')
const emptyText = computed(() =>
  hasFilter.value ? '没有符合条件的膜组，请调整筛选条件后重试' : '暂无膜组件数据，可先登记膜组',
)

function allowedActions(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? '')] ?? []
}

// 更换后被清空的字段统一展示为「—」，列表、详情保持同一口径
function formatCell(row: Row, column: string): string {
  const value = row[column]
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function applyFilter() {
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '膜组登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      // 重复更换、已更换再投用等情况由后端给出明确说明，直接透传给操作员
      throw new Error(payload?.message || '膜组件动作未生效，请稍后重试')
    }
    successMessage.value = payload.message || '操作已生效'
    // 动作完成后同时刷新列表与统计卡片，保证两处状态一致
    await reload({ keepMessage: true })
  } catch (error) {
    successMessage.value = ''
    errorMessage.value = error instanceof Error ? error.message : '膜组件操作失败'
  }
}

async function loadStats() {
  const response = await request(`${ENDPOINT}/stats`)
  if (!response.ok) {
    throw new Error('膜组件统计读取失败')
  }
  const payload = (await response.json()) as { items?: Stat[] }
  stats.value = payload.items ?? EMPTY_STATS
}

async function reload(options: { keepMessage?: boolean } = {}) {
  if (!options.keepMessage) {
    errorMessage.value = ''
    successMessage.value = ''
  }
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (status.value) params.set('status', status.value)
  const query = params.toString()
  try {
    const [listResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      loadStats(),
    ])
    if (!listResponse.ok) {
      throw new Error('膜组列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    successMessage.value = ''
    errorMessage.value = error instanceof Error ? error.message : '膜组件列表读取失败'
  }
}

onMounted(() => void reload())
</script>
