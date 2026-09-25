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

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条膜组件记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type MembraneStats = {
  total: number
  running: number
  pending_clean: number
  replaced: number
  avg_tmp: number | null
  tmp_samples: number
}

const ENDPOINT = '/api/membrane'
const columns = ["膜组编号", "膜型号", "膜面积", "跨膜压差", "通量", "清洗周期", "投用日期", "膜组状态"]
const actions = ["确认投用", "提交清洗", "更换膜组"]

const stats = ref([
  { label: '膜组总数', value: '0' },
  { label: '运行膜组', value: '0' },
  { label: '待清洗膜组', value: '0' },
  { label: '跨膜压差均值', value: '—' },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const hasFilters = computed(() =>
  Object.values(filters.value).some((value) => Boolean(value && value.trim())),
)
const emptyText = computed(() =>
  hasFilters.value
    ? '没有符合筛选条件的膜组，可调整条件后重新查询'
    : '暂无膜组件数据，可先登记膜组',
)

function buildQuery(): string {
  const params = new URLSearchParams()
  const code = filters.value['膜组编号']?.trim()
  const model = filters.value['膜型号']?.trim()
  const area = filters.value['膜面积']?.trim()
  if (code) params.set('keyword', code)
  if (model) params.set('膜型号', model)
  if (area) params.set('膜面积', area)
  return params.toString()
}

function resetFilters() {
  filters.value = {}
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
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json().catch(() => null)) as
      | { ok?: boolean; message?: string }
      | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '膜组件动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? `膜组已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '膜组件操作失败'
  }
}

async function loadList(query: string) {
  const response = await request(`${ENDPOINT}?${query}`)
  if (!response.ok) {
    throw new Error('膜组列表读取失败')
  }
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function loadStats(query: string) {
  const response = await request(`${ENDPOINT}/stats?${query}`)
  if (!response.ok) {
    throw new Error('膜组统计读取失败')
  }
  const payload = (await response.json()) as MembraneStats
  stats.value = [
    { label: '膜组总数', value: String(payload.total ?? 0) },
    { label: '运行膜组', value: String(payload.running ?? 0) },
    { label: '待清洗膜组', value: String(payload.pending_clean ?? 0) },
    {
      label: '跨膜压差均值',
      value: payload.avg_tmp === null || payload.avg_tmp === undefined ? '—' : String(payload.avg_tmp),
    },
  ]
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery()
  const results = await Promise.allSettled([loadList(query), loadStats(query)])
  const failed = results.find((result) => result.status === 'rejected')
  if (failed && failed.status === 'rejected') {
    errorMessage.value =
      failed.reason instanceof Error ? failed.reason.message : '膜组件数据读取失败'
  }
}

onMounted(reload)
</script>
