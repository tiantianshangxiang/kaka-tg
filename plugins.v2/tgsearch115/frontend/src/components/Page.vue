<!--
  Page.vue -- 插件详情页（被 MoviePilot 前端通过 Module Federation 加载到插件详情 Tab）。
  上方运行状态概览；下方手动搜索（TG 频道 + 资源站），结果用响应式卡片网格展示。
  props 由 MP 注入：pluginId、api。
-->
<template>
  <div class="tg115-page">
    <!-- ============ 状态概览 ============ -->
    <v-card variant="outlined" rounded="lg" class="mb-4">
      <v-card-title class="d-flex align-center px-4 py-3">
        <v-icon icon="mdi-robot-outline" color="primary" class="mr-2" />
        拦截mp订阅
        <v-spacer />
        <v-chip :color="config.enabled ? 'success' : 'grey'" variant="tonal" size="small">
          {{ config.enabled ? '运行中' : '已停用' }}
        </v-chip>
      </v-card-title>
      <v-divider />
      <v-card-text class="px-4 py-4">
        <v-row>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">TG 频道数</div>
            <div class="text-h6">{{ channelCount }}</div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">115 登录</div>
            <div class="text-h6" :class="loginOk ? 'text-success' : 'text-medium-emphasis'">
              {{ loginOk ? '已登录' : '未登录' }}
            </div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">触发延迟</div>
            <div class="text-h6">{{ config.delay_seconds || 0 }} 秒</div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">上次周期扫描</div>
            <div class="text-body-2">{{ formatTime(runtime.scheduler.last_run) }}</div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">下次周期扫描</div>
            <div class="text-body-2">{{ formatTime(runtime.scheduler.next_run) }}</div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">队列 / 本轮订阅</div>
            <div class="text-body-2">{{ runtime.scheduler.queue_size || 0 }} / {{ runtime.scheduler.scanned_count || 0 }}</div>
          </v-col>
        </v-row>
        <div v-if="sourceStates.length" class="d-flex flex-wrap ga-2 mt-3">
          <v-chip
            v-for="source in sourceStates"
            :key="source.name"
            size="small"
            variant="tonal"
            :color="source.cooldown_seconds > 0 ? 'warning' : 'success'"
          >{{ source.name }} · {{ source.cooldown_seconds > 0 ? `冷却 ${source.cooldown_seconds}s` : '可用' }}</v-chip>
        </div>
      </v-card-text>
    </v-card>

    <v-card v-if="runtime.tasks.length" variant="outlined" rounded="lg" class="mb-4">
      <v-card-title class="d-flex align-center px-4 py-3">
        <v-icon icon="mdi-cloud-sync-outline" color="primary" class="mr-2" />
        CMS / 115 任务
        <v-spacer />
        <v-btn icon variant="text" size="small" :loading="statusLoading" @click="loadRuntimeStatus">
          <v-icon icon="mdi-refresh" />
          <v-tooltip activator="parent" location="top">刷新任务状态</v-tooltip>
        </v-btn>
      </v-card-title>
      <v-divider />
      <v-table density="compact">
        <thead>
          <tr><th>资源</th><th>状态</th><th>提交时间</th><th class="text-right">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="task in runtime.tasks" :key="`${task.btih}-${task.submitted_at}`">
            <td>
              <div class="task-title">{{ task.title }}</div>
              <div class="text-caption text-medium-emphasis">BTIH {{ String(task.btih || '').slice(0, 12) }}...</div>
              <div v-if="task.error" class="text-caption text-error">{{ task.error }}</div>
            </td>
            <td><v-chip size="x-small" variant="tonal" :color="taskStatusColor(task.status)">{{ taskStatusLabel(task.status) }}</v-chip></td>
            <td class="text-caption">{{ formatTime(task.submitted_at) }}</td>
            <td class="text-right">
              <v-btn
                v-if="['failed', 'timed_out'].includes(task.status)"
                icon variant="text" size="small" color="primary"
                :loading="retryingBtih === task.btih"
                @click="retryTask(task)"
              >
                <v-icon icon="mdi-replay" />
                <v-tooltip activator="parent" location="top">重试任务</v-tooltip>
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- ============ 手动搜索 ============ -->
    <v-card variant="outlined" rounded="lg">
      <v-card-title class="d-flex align-center px-4 py-3">
        <v-icon icon="mdi-magnify" color="primary" class="mr-2" />
        手动搜索网盘资源
        <v-chip v-if="results.length" size="x-small" variant="tonal" color="primary" class="ml-2">
          {{ filteredResults.length }}/{{ results.length }} 条
        </v-chip>
        <v-spacer />
        <v-chip v-if="hasTransferable" size="x-small" variant="tonal" color="success" class="mr-1">支持转存到 115</v-chip>
        <v-btn v-if="results.length" size="x-small" variant="text" color="error" prepend-icon="mdi-close" @click="clearResults">清除</v-btn>
      </v-card-title>
      <v-divider />
      <v-card-text class="px-4 py-4">
        <v-text-field
          v-model="keyword"
          label="输入片名搜索（TG 频道 + 观影，115 分享/磁力可转存）"
          variant="outlined"
          density="comfortable"
          hide-details
          :loading="searching"
          append-inner-icon="mdi-magnify"
          @click:append-inner="doSearch"
          @keyup.enter="doSearch"
        />
        <div class="d-flex align-center ga-2 mt-2">
          <span class="text-caption text-medium-emphasis">来源</span>
          <v-btn-toggle v-model="searchSource" mandatory color="primary" density="compact" divided>
            <v-btn value="all" size="small">全部</v-btn>
            <v-btn value="tg" size="small">TG</v-btn>
            <v-btn value="site" size="small">观影</v-btn>
            <v-btn value="juying" size="small">聚影</v-btn>
          </v-btn-toggle>
        </div>
        <div class="filter-row mt-3">
          <span class="filter-label">资源</span>
          <v-btn-toggle v-model="resourceFilter" mandatory color="primary" density="compact" divided class="filter-toggle">
            <v-btn v-for="item in RESOURCE_FILTERS" :key="item.value" :value="item.value" size="small">{{ item.title }}</v-btn>
          </v-btn-toggle>
        </div>
        <div class="filter-row mt-2">
          <span class="filter-label">画质</span>
          <v-btn-toggle v-model="qualityFilter" mandatory color="primary" density="compact" divided class="filter-toggle">
            <v-btn v-for="item in QUALITY_FILTERS" :key="item.value" :value="item.value" size="small">{{ item.title }}</v-btn>
          </v-btn-toggle>
        </div>
        <div v-if="searchMsg" class="text-caption mt-2" :class="searchOk ? 'text-success' : 'text-error'">
          {{ searchMsg }}
        </div>
      </v-card-text>

      <!-- 搜索结果：响应式卡片网格（1/2/3/4 列） -->
      <v-card-text v-if="results.length" class="px-4 pb-4 pt-0">
        <v-row dense>
          <v-col v-for="(r, i) in filteredResults" :key="r.share_url || i" cols="12" sm="6" md="4" lg="3">
            <v-card variant="tonal" rounded="lg" class="result-card h-100 d-flex flex-column">
              <v-card-item class="pb-2">
                <div class="d-flex align-center mb-2">
                  <v-chip :color="panColor(r.pan_type)" size="x-small" variant="flat" class="mr-2">
                    {{ panLabel(r.pan_type) }}
                  </v-chip>
                  <v-chip v-if="r.is_complete" size="x-small" variant="flat" color="success" class="mr-2">完结</v-chip>
                  <span v-if="r.pub_date" class="text-caption text-medium-emphasis ml-auto">{{ r.pub_date.slice(0, 10) }}</span>
                </div>
                <div class="text-body-1 font-weight-bold line-clamp-2" :title="r.display_name || r.title">
                  {{ r.display_name || r.title }}
                </div>
                <div v-if="r.meta" class="text-caption text-primary font-weight-medium mt-1">{{ r.meta }}</div>
                <div v-if="r.pan_type === '115' && r.receive_code" class="text-caption text-warning mt-1">提取码：{{ r.receive_code }}</div>
                <div v-if="r.text" class="text-caption text-medium-emphasis line-clamp-3 mt-1">{{ r.text }}</div>
                <div class="text-caption text-medium-emphasis mt-1">{{ r.channel || '未知来源' }}</div>
              </v-card-item>
              <v-spacer />
              <v-card-actions class="pt-2">
                <v-btn size="small" variant="text" prepend-icon="mdi-content-copy" @click="copy(r)">复制链接</v-btn>
                <v-spacer />
                <v-btn
                  v-if="r.pan_type === '115' || r.pan_type === 'magnet'"
                  size="small" variant="flat" color="primary" prepend-icon="mdi-cloud-download"
                  :loading="transferringIdx === i"
                  @click="transfer(r, i)"
                >{{ r.pan_type === 'magnet' ? '离线到115' : '转存' }}</v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
        <div v-if="!filteredResults.length" class="filter-empty">当前筛选条件下没有资源</div>
        <div v-if="hasMore" class="d-flex justify-center mt-4">
          <v-btn variant="outlined" :loading="loadingMore" prepend-icon="mdi-chevron-down" @click="loadMore">
            查看更多历史
          </v-btn>
        </div>
        <div v-else class="text-center text-caption text-medium-emphasis mt-3">已全部加载</div>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="snack" :color="snackColor" :timeout="2500" location="top">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { filterSearchResults, QUALITY_FILTERS, RESOURCE_FILTERS } from '../searchFilters.js'

const props = defineProps({
  pluginId: { type: String, default: 'TgSearch115' },
  api: { type: Object, default: null },
})

const PID = computed(() => props.pluginId || 'TgSearch115')

// ---- 配置 / 状态 ----
const config = reactive({ enabled: false, p115_cookie: '', cms_url: '', cms_token: '', delay_seconds: 0, tg_channels: [] })
const runtime = reactive({
  scheduler: { running: false, last_run: '', next_run: '', scanned_count: 0, queue_size: 0 },
  sources: {},
  tasks: [],
})
const statusLoading = ref(false)
const retryingBtih = ref('')
let statusTimer = null
const sourceStates = computed(() => Object.entries(runtime.sources || {}).map(([name, state]) => ({ name, ...state })))
const channelCount = computed(() => (Array.isArray(config.tg_channels) ? config.tg_channels.length : 0))
const loginOk = computed(() => {
  const c = String(config.p115_cookie || '')
  return c.length > 0 && ['UID', 'CID', 'SEID'].every((k) => c.includes(k + '='))
})

// ---- 搜索 ----
// 搜索结果持久化：保存到 localStorage，下次进详情页自动恢复，新搜索覆盖
const CACHE_KEY = 'tg115_search_cache'
const PAGE_SIZE = 3  // 资源站每批作品数（与后端 count=3 一致）
function loadCache() {
  try {
    const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null')
    return c && Array.isArray(c.results) ? c : null
  } catch { return null }
}
function saveCache(c) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ...c, ts: Date.now() })) } catch {}
}
const _init = loadCache()
const keyword = ref(_init ? _init.keyword : '')
const searchSource = ref('all')
const resourceFilter = ref(_init?.resource_filter || 'all')
const qualityFilter = ref(_init?.quality_filter || 'all')
const results = ref(_init ? _init.results : [])
const offset = ref(_init ? _init.offset || 0 : 0)
const hasMore = ref(_init ? !!_init.has_more : false)
const searching = ref(false)
const loadingMore = ref(false)
const searchMsg = ref(_init ? `已恢复上次搜索「${_init.keyword}」的结果（${_init.results.length} 条）` : '')
const searchOk = ref(!!_init)
const transferringIdx = ref(-1)
const hasTransferable = computed(() => results.value.some(
  (r) => r.pan_type === '115' || r.pan_type === 'magnet',
))
const filteredResults = computed(() => filterSearchResults(
  results.value,
  resourceFilter.value,
  qualityFilter.value,
))

function clearResults() {
  results.value = []
  searchMsg.value = ''
  searchOk.value = false
  keyword.value = ''
  offset.value = 0
  hasMore.value = false
  try { localStorage.removeItem(CACHE_KEY) } catch {}
}
// snackbar
const snack = ref(false)
const snackColor = ref('')
const snackText = ref('')

const PAN_LABEL = { '115': '115', quark: '夸克', baidu: '百度', aliyun: '阿里', xunlei: '迅雷', cloud189: '天翼', uc: 'UC', magnet: '磁力', other: '其他' }
const PAN_COLOR = { '115': 'success', quark: 'info', baidu: 'error', aliyun: 'cyan', xunlei: 'purple', cloud189: 'indigo', uc: 'orange', magnet: 'deep-purple', other: 'grey' }
function panLabel(t) { return PAN_LABEL[t] || t || '其他' }
function panColor(t) { return PAN_COLOR[t] || 'grey' }
function formatTime(value) {
  if (!value) return '尚未运行'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
function taskStatusLabel(status) {
  return {
    waiting: '等待中', downloading: '下载中', pending_organize: '待整理',
    completed: '已完成', failed: '失败', timed_out: '超时',
  }[status] || status || '未知'
}
function taskStatusColor(status) {
  return {
    waiting: 'info', downloading: 'primary', pending_organize: 'warning',
    completed: 'success', failed: 'error', timed_out: 'warning',
  }[status] || 'grey'
}

async function loadRuntimeStatus() {
  if (!props.api?.get) return
  statusLoading.value = true
  try {
    const res = await props.api.get(`plugin/${PID.value}/runtime/status`)
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res
    if (data?.success) {
      Object.assign(runtime.scheduler, data.scheduler || {})
      runtime.sources = data.sources || {}
      runtime.tasks = Array.isArray(data.tasks) ? data.tasks : []
    }
  } catch {
    // Status refresh is non-blocking; search actions continue to work.
  } finally {
    statusLoading.value = false
  }
}

async function retryTask(task) {
  if (!props.api?.post || !task?.btih) return
  retryingBtih.value = task.btih
  try {
    const res = await props.api.post(`plugin/${PID.value}/tasks/retry`, { btih: task.btih })
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res
    showSnack(data?.message || (data?.success ? '任务已重新提交' : '重试失败'), data?.success ? 'success' : 'error')
    await loadRuntimeStatus()
  } catch (e) {
    showSnack('重试异常：' + (e?.message || e), 'error')
  } finally {
    retryingBtih.value = ''
  }
}

async function doSearch() {
  const kw = (keyword.value || '').trim()
  if (!kw) { showSnack('请输入搜索关键字', 'warning'); return }
  if (!props.api?.get) { showSnack('API 未就绪', 'error'); return }
  searching.value = true
  searchMsg.value = ''
  try {
    const res = await props.api.get(`plugin/${PID.value}/search?keyword=${encodeURIComponent(kw)}&source=${searchSource.value}`)
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res
    if (data && data.success) {
      results.value = Array.isArray(data.results) ? data.results : []
      searchMsg.value = data.warning || data.message || `找到 ${results.value.length} 条`
      searchOk.value = !data.warning
      offset.value = 0
      hasMore.value = !!data.has_more
      saveCache({ keyword: kw, results: results.value, offset: 0, has_more: hasMore.value, resource_filter: resourceFilter.value, quality_filter: qualityFilter.value })
    } else {
      results.value = []
      searchMsg.value = (data && data.message) || '搜索失败'
      searchOk.value = false
    }
  } catch (e) {
    results.value = []
    searchMsg.value = '搜索异常：' + (e?.message || e)
    searchOk.value = false
  } finally {
    searching.value = false
  }
}

// 加载更多：资源站翻页（下一批作品），追加结果并全局重排（完结优先）
async function loadMore() {
  if (!hasMore.value || loadingMore.value || !props.api?.get) return
  loadingMore.value = true
  try {
    const next = offset.value + PAGE_SIZE
    const res = await props.api.get(`plugin/${PID.value}/search?keyword=${encodeURIComponent(keyword.value)}&offset=${next}&source=${searchSource.value}`)
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res
    if (data && data.success) {
      const more = Array.isArray(data.results) ? data.results : []
      results.value = [...results.value, ...more]
      offset.value = next
      hasMore.value = !!data.has_more
      // 全局重排：完结优先，集数降序
      results.value.sort((a, b) => (b.is_complete - a.is_complete) || (b.episode_num - a.episode_num))
      saveCache({ keyword: keyword.value, results: results.value, offset: offset.value, has_more: hasMore.value, resource_filter: resourceFilter.value, quality_filter: qualityFilter.value })
      searchMsg.value = `共 ${results.value.length} 条`
    } else {
      showSnack(data?.message || '加载更多失败', 'error')
    }
  } catch (e) {
    showSnack('加载更多异常：' + (e?.message || e), 'error')
  } finally {
    loadingMore.value = false
  }
}

// 115 链接：若提取码未附在 URL 上，补上（share_receive 需要 receive_code）
function fullShareUrl(r) {  let url = r.share_url || ''
  const rc = r.receive_code || ''
  if (r.pan_type === '115' && rc && !/[?&](password|receive_code|pwd)=/.test(url)) {
    url += (url.includes('?') ? '&' : '?') + 'password=' + rc
  }
  return url
}

async function copy(r) {
  const url = fullShareUrl(r)
  try {
    await navigator.clipboard.writeText(url)
    showSnack('已复制链接', 'success')
  } catch {
    showSnack('复制失败，请手动复制', 'error')
  }
}

async function transfer(r, i) {
  if (r.pan_type === '115' && !loginOk.value) {
    showSnack('未登录 115，无法转存', 'error')
    return
  }
  if (r.pan_type === 'magnet' && (!config.cms_url || !config.cms_token)) {
    showSnack('请先在观影设置中配置 CMS 地址和 API Token', 'error')
    return
  }
  transferringIdx.value = i
  try {
    const res = r.pan_type === 'magnet'
      ? await props.api.post(`plugin/${PID.value}/magnet/offline`, {
          magnet: fullShareUrl(r),
          title: r.display_name || r.title || '',
        })
      : await props.api.get(`plugin/${PID.value}/transfer?share_url=${encodeURIComponent(fullShareUrl(r))}`)
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res
    const success = data?.success === true || data?.code === 0
    showSnack(data?.message || (success ? '任务提交成功' : '转存失败'), success ? 'success' : 'error')
  } catch (e) {
    showSnack('转存异常：' + (e?.message || e), 'error')
  } finally {
    transferringIdx.value = -1
  }
}

function showSnack(text, color) {
  snackText.value = text
  snackColor.value = color
  snack.value = true
}

onMounted(async () => {
  if (!props.api?.get) return
  try {
    const res = await props.api.get(`plugin/${PID.value}/config/get`)
    const cfg = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res
    if (cfg && typeof cfg === 'object') Object.assign(config, cfg)
  } catch {
    // 静默
  }
  await loadRuntimeStatus()
  statusTimer = setInterval(loadRuntimeStatus, 30000)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<style scoped>
.tg115-page {
  max-width: 1280px;
  margin: 0 auto;
}
.result-card {
  min-height: 180px;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.filter-label {
  flex: 0 0 32px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.62);
}
.filter-toggle {
  max-width: calc(100% - 40px);
  overflow-x: auto;
}
.filter-empty {
  padding: 28px 12px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 0.875rem;
}
.task-title {
  max-width: 520px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
