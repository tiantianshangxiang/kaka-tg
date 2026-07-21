<template>
  <div class="manual-search">
    <div class="d-flex align-center ga-2 mb-3 flex-wrap">
      <span class="text-caption text-medium-emphasis">来源</span>
      <v-btn-toggle v-model="source" mandatory color="primary" density="compact" divided>
        <v-btn value="all" size="small">全部</v-btn>
        <v-btn value="tg" size="small">TG</v-btn>
        <v-btn value="site" size="small">观影</v-btn>
        <v-btn value="juying" size="small">聚影</v-btn>
      </v-btn-toggle>
    </div>

    <div class="d-flex ga-2 mb-3 search-row">
      <v-text-field v-model="keyword" label="搜索关键字（影片名 + 年份）" variant="outlined"
        density="comfortable" hide-details :loading="searching" @keyup.enter="search" />
      <v-btn color="primary" variant="flat" :loading="searching" prepend-icon="mdi-magnify" @click="search">搜索</v-btn>
    </div>

    <div class="filter-row mb-2">
      <span class="filter-label">资源</span>
      <v-btn-toggle v-model="resourceType" mandatory color="primary" density="compact" divided class="filter-toggle">
        <v-btn value="all" size="small">全部</v-btn>
        <v-btn value="magnet" size="small">磁力</v-btn>
        <v-btn value="pan" size="small">网盘</v-btn>
      </v-btn-toggle>
      <v-chip v-if="results.length" size="x-small" variant="tonal" color="primary">{{ filtered.length }}/{{ results.length }} 条</v-chip>
    </div>

    <div v-if="resourceType === 'magnet'" class="filter-row mb-3">
      <span class="filter-label">画质</span>
      <v-btn-toggle v-model="detailFilter" mandatory color="primary" density="compact" divided class="filter-toggle">
        <v-btn v-for="item in MAGNET_FILTERS" :key="item.value" :value="item.value" size="small">{{ item.title }}</v-btn>
      </v-btn-toggle>
    </div>
    <div v-else-if="resourceType === 'pan'" class="filter-row mb-3">
      <span class="filter-label">网盘</span>
      <v-btn-toggle v-model="detailFilter" mandatory color="primary" density="compact" divided class="filter-toggle">
        <v-btn v-for="item in PAN_FILTERS" :key="item.value" :value="item.value" size="small">{{ item.title }}</v-btn>
      </v-btn-toggle>
    </div>

    <div v-if="message" class="text-caption mb-3" :class="ok ? 'text-success' : 'text-error'">{{ message }}</div>
    <div v-if="searching" class="empty-state"><v-progress-circular indeterminate size="40" color="primary" /></div>
    <v-row v-else-if="filtered.length" dense>
      <v-col v-for="(r, i) in filtered" :key="r.share_url || i" cols="12" sm="6" md="4">
        <v-card variant="outlined" class="result-card h-100 d-flex flex-column">
          <v-card-item>
            <div class="d-flex align-center ga-1 mb-2">
              <v-chip :color="panColor(r.pan_type)" size="x-small" variant="tonal">{{ panLabel(r.pan_type) }}</v-chip>
              <v-chip v-if="r.is_complete" color="success" size="x-small" variant="tonal">完结</v-chip>
            </div>
            <div class="text-body-2 font-weight-medium">{{ r.display_name || r.title }}</div>
            <div v-if="r.meta" class="text-caption text-primary mt-1">{{ r.meta }}</div>
            <div class="text-caption text-medium-emphasis line-clamp-3 mt-1">{{ r.text || r.title }}</div>
            <div class="text-caption text-medium-emphasis mt-1">{{ r.channel || '未知来源' }}</div>
          </v-card-item>
          <v-spacer />
          <v-card-actions>
            <v-btn size="small" variant="text" prepend-icon="mdi-content-copy" @click="copy(r)">复制链接</v-btn>
            <v-spacer />
            <v-btn v-if="['115','magnet'].includes(r.pan_type)" size="small" variant="flat" color="primary"
              prepend-icon="mdi-cloud-download" :loading="transferring === r.share_url" @click="transfer(r)">
              {{ r.pan_type === 'magnet' ? '离线到115' : '转存' }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <div v-else-if="searched && !searching" class="empty-state">当前筛选条件下没有资源</div>

    <v-snackbar v-model="snack" :color="snackColor" :timeout="3000" location="top">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { filterSearchResults, MAGNET_FILTERS, PAN_FILTERS } from '../searchFilters.js'

const props = defineProps({ pluginId: { type: String, default: 'TgSearch115' }, api: { type: Object, default: null } })
const base = computed(() => `plugin/${props.pluginId || 'TgSearch115'}`)
const keyword = ref('')
const source = ref('all')
const resourceType = ref('all')
const detailFilter = ref('all')
const results = ref([])
const searching = ref(false)
const searched = ref(false)
const transferring = ref('')
const message = ref('')
const ok = ref(false)
const snack = ref(false)
const snackColor = ref('')
const snackText = ref('')
const filtered = computed(() => filterSearchResults(results.value, resourceType.value, detailFilter.value))

watch(resourceType, () => { detailFilter.value = 'all' })

function unwrap(res) {
  if (res && typeof res === 'object' && res.data && typeof res.data === 'object') return res.data
  return res
}
function notify(text, color = 'success') { snackText.value = text; snackColor.value = color; snack.value = true }
function fullUrl(r) {
  let url = String(r?.share_url || '')
  if (r?.pan_type === '115' && r?.receive_code && !/[?&](password|receive_code|pwd)=/.test(url)) {
    url += (url.includes('?') ? '&' : '?') + 'password=' + r.receive_code
  }
  return url
}
async function search() {
  const value = keyword.value.trim()
  if (!value) return notify('请输入搜索关键字', 'warning')
  if (!props.api?.get) return notify('API 未就绪', 'error')
  searching.value = true; searched.value = true; message.value = ''
  try {
    const data = unwrap(await props.api.get(`${base.value}/search?keyword=${encodeURIComponent(value)}&source=${source.value}`))
    results.value = Array.isArray(data?.results) ? data.results : []
    ok.value = !!data?.success
    message.value = data?.warning || data?.message || (ok.value ? `找到 ${results.value.length} 条` : '搜索失败')
  } catch (e) {
    results.value = []; ok.value = false; message.value = e?.response?.data?.message || e?.message || '搜索失败'
  } finally { searching.value = false }
}
async function copy(r) {
  try { await navigator.clipboard.writeText(fullUrl(r)); notify('已复制链接') }
  catch { notify('复制失败，请手动复制', 'error') }
}
async function transfer(r) {
  if (!props.api) return notify('API 未就绪', 'error')
  transferring.value = r.share_url
  try {
    const response = r.pan_type === 'magnet'
      ? await props.api.post(`${base.value}/magnet/offline`, { magnet: fullUrl(r), title: r.display_name || r.title || '' })
      : await props.api.get(`${base.value}/transfer?share_url=${encodeURIComponent(fullUrl(r))}`)
    const data = unwrap(response)
    if (!data || typeof data !== 'object') throw new Error('服务返回非 JSON，请检查插件日志')
    const success = data.success === true || data.code === 0
    notify(data.message || (success ? '任务提交成功' : '提交失败'), success ? 'success' : 'error')
  } catch (e) {
    notify(e?.response?.data?.message || e?.message || '离线请求失败', 'error')
  } finally { transferring.value = '' }
}
function panLabel(t) { return ({ '115':'115网盘', quark:'夸克网盘', baidu:'百度网盘', aliyun:'阿里网盘', xunlei:'迅雷网盘', cloud189:'天翼网盘', uc:'UC网盘', magnet:'磁力' })[t] || '其他' }
function panColor(t) { return ({ '115':'success', quark:'info', baidu:'error', aliyun:'warning', xunlei:'secondary', cloud189:'primary', uc:'orange', magnet:'deep-purple' })[t] || 'grey' }
</script>

<style scoped>
.filter-row { display:flex; align-items:center; gap:8px; min-width:0; flex-wrap:wrap; }
.filter-label { flex:0 0 32px; font-size:.75rem; color:rgba(var(--v-theme-on-surface),.6); }
.filter-toggle { flex-wrap:wrap; height:auto; }
.search-row > :first-child { min-width:0; flex:1; }
.result-card { min-height:180px; border-radius:8px; }
.line-clamp-3 { display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.empty-state { padding:28px; text-align:center; color:rgba(var(--v-theme-on-surface),.6); }
@media (max-width:600px) { .search-row { flex-direction:column; } .search-row .v-btn { width:100%; } }
</style>
