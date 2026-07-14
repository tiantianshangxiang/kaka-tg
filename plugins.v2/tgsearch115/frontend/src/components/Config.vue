<!--
  Config.vue -- 「拦截mp订阅」插件自定义配置页（被 MoviePilot 前端通过 Module Federation 加载）。

  MoviePilot 注入 props：
    - pluginId:       插件 ID（用于拼 API 路径）
    - api:            API 客户端，含 get(url) / post(url, data)，自动带 apikey 与 /api/v1 前缀
    - initialConfig:  MP 预取的初始配置（可选）

  布局：竖向三段式
    ① 115 网盘登录配置区
    ② Tabs 标签栏（VTabs，自带 Active 下划线动画）
    ③ 标签页内容区（TG 机器人模块 / TG 频道模块）
-->
<template>
  <div class="tg115-config">
    <!-- ============ 第 ① 段：115 网盘登录 ============ -->
    <v-card variant="outlined" rounded="lg" class="tg115-card mb-4">
      <v-card-title class="d-flex align-center px-4 py-3">
        <v-icon icon="mdi-cloud-outline" color="primary" class="mr-2" />
        <span class="text-subtitle-1 font-weight-bold">115 网盘登录</span>
        <v-spacer />
        <v-chip
          :color="loginOk ? 'success' : 'grey'"
          variant="tonal"
          size="small"
          class="font-weight-medium"
          :prepend-icon="loginOk ? 'mdi-check-circle' : 'mdi-alert-circle-outline'"
        >
          {{ loginOk ? '已登录' : '未登录' }}
        </v-chip>
      </v-card-title>
      <v-divider />
      <v-card-text class="px-4 py-4">
        <v-row>
          <v-col cols="12">
            <v-text-field
              v-model="config.p115_cookie"
              :type="showSecrets ? 'text' : 'password'"
              label="115 Cookie"
              variant="outlined"
              density="comfortable"
              hint="需用 115 客户端扫码登录后抓取，必须包含 UID / CID / SEID（网页版 Cookie 无法转存）"
              persistent-hint
              :append-inner-icon="showSecrets ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showSecrets = !showSecrets"
            />
          </v-col>
          <v-col cols="12" md="8">
            <v-text-field
              v-model="config.p115_target"
              label="115 转存目标目录"
              variant="outlined"
              density="comfortable"
              hint="如 /电影；目录不存在会自动创建；也可填数字 cid"
              persistent-hint
            />
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center flex-wrap ga-2">
            <v-btn color="primary" variant="flat" :loading="saving" prepend-icon="mdi-refresh" @click="saveAll">
              {{ loginOk ? '更新凭证' : '登录' }}
            </v-btn>
            <v-btn variant="outlined" prepend-icon="mdi-qrcode-scan" @click="openQrcode">扫码登录</v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- ============ 第 ② + ③ 段：Tabs + 内容区 ============ -->
    <v-card variant="outlined" rounded="lg" class="tg115-card">
      <v-tabs v-model="activeTab" color="primary" density="comfortable" class="px-2">
        <v-tab value="bot" prepend-icon="mdi-robot-outline">TG 机器人模块</v-tab>
        <v-tab value="channel" prepend-icon="mdi-bullhorn-outline">TG 频道模块</v-tab>
      </v-tabs>
      <v-divider />

      <v-window v-model="activeTab">
        <!-- ====== Tab 1：TG 机器人模块 ====== -->
        <v-window-item value="bot" class="pa-4">
          <v-row>
            <v-col cols="12" md="6" class="d-flex align-center">
              <div class="mr-2">
                <div class="text-subtitle-2">功能总开关</div>
                <div class="text-caption text-medium-emphasis">开启后监听订阅新增事件并自动检索 TG 频道</div>
              </div>
              <v-spacer />
              <v-switch v-model="config.enabled" color="primary" hide-details density="compact" />
            </v-col>
            <v-col cols="12" md="6" class="d-flex align-center">
              <div class="mr-2">
                <div class="text-subtitle-2">MP 过滤规则组二次匹配</div>
                <div class="text-caption text-medium-emphasis">复用 MoviePilot 订阅过滤规则组对命中资源再过滤</div>
              </div>
              <v-spacer />
              <v-switch v-model="config.use_rule_groups" color="primary" hide-details density="compact" />
            </v-col>
          </v-row>

          <div class="section-label mt-4 mb-2">Telegram 会话凭证（User Session）</div>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="config.tg_api_id"
                label="TG API ID"
                variant="outlined"
                density="comfortable"
                hint="在 my.telegram.org 申请的 API ID（数字）"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="config.tg_api_hash"
                :type="showSecrets ? 'text' : 'password'"
                label="TG API Hash"
                variant="outlined"
                density="comfortable"
                hint="在 my.telegram.org 申请的 API Hash"
                persistent-hint
                :append-inner-icon="showSecrets ? 'mdi-eye-off' : 'mdi-eye'"
                @click:append-inner="showSecrets = !showSecrets"
              />
            </v-col>
            <v-col cols="12">
              <v-text-field
                v-model="config.tg_session"
                :type="showSecrets ? 'text' : 'password'"
                label="TG Session String"
                variant="outlined"
                density="comfortable"
                hint="用 gen_tg_session.py 在本地生成后粘贴（容器内无法交互登录）"
                persistent-hint
                :append-inner-icon="showSecrets ? 'mdi-eye-off' : 'mdi-eye'"
                @click:append-inner="showSecrets = !showSecrets"
              />
            </v-col>
          </v-row>

          <v-row>
            <v-col cols="12" md="4">
              <v-text-field
                v-model="config.tg_proxy"
                label="TG 代理"
                variant="outlined"
                density="comfortable"
                placeholder="socks5://host:port"
                hint="可选；SOCKS 需另装 telethon[socks]"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model="config.tg_max_messages"
                label="最大检索消息数"
                variant="outlined"
                density="comfortable"
                type="number"
                hint="每个频道最多检索的历史消息数"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model="config.delay_seconds"
                label="触发延迟（秒）"
                variant="outlined"
                density="comfortable"
                type="number"
                hint="订阅创建后等待几秒再触发"
                persistent-hint
              />
            </v-col>
          </v-row>

          <div class="section-label mt-2 mb-1">通知</div>
          <v-row>
            <v-col cols="12" md="6" class="d-flex align-center">
              <span class="text-body-2 mr-2">转存成功通知</span>
              <v-switch v-model="config.notify_success" color="primary" hide-details density="compact" />
            </v-col>
            <v-col cols="12" md="6" class="d-flex align-center">
              <span class="text-body-2 mr-2">未命中 / 失败通知</span>
              <v-switch v-model="config.notify_fail" color="primary" hide-details density="compact" />
            </v-col>
          </v-row>

          <div class="d-flex justify-end mt-4">
            <v-btn color="primary" variant="flat" :loading="saving" prepend-icon="mdi-content-save" @click="saveAll">
              保存该模块配置
            </v-btn>
          </div>
        </v-window-item>

        <!-- ====== Tab 2：TG 频道模块 ====== -->
        <v-window-item value="channel" class="pa-4">
          <div class="section-label mb-2">添加频道</div>
          <v-card variant="tonal" color="primary" rounded="lg" class="mb-4 add-card">
            <v-card-text>
              <v-row align="center">
                <v-col cols="12" md="4">
                  <v-text-field v-model="newName" label="频道名称" variant="outlined" density="comfortable" hide-details />
                </v-col>
                <v-col cols="12" md="5">
                  <v-text-field
                    v-model="newId"
                    label="频道 ID / 链接"
                    variant="outlined"
                    density="comfortable"
                    hint="@用户名 / 邀请链接 / 数字 ID"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="3" class="d-flex justify-md-end">
                  <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="addChannel">保存 / 添加</v-btn>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <div class="d-flex align-center mb-2">
            <span class="section-label">已添加频道</span>
            <v-chip size="small" variant="tonal" class="ml-2">{{ channels.length }}</v-chip>
            <v-spacer />
            <v-btn color="secondary" variant="tonal" prepend-icon="mdi-import" @click="openImport">批量导入</v-btn>
          </div>

          <div v-if="channels.length" class="channel-list">
            <v-card
              v-for="(ch, i) in channels"
              :key="ch.uid || i"
              variant="outlined"
              rounded="lg"
              class="channel-item"
            >
              <div class="d-flex align-center px-3 py-2">
                <v-icon icon="mdi-bullhorn-variant-outline" color="primary" class="mr-3" />
                <div class="channel-meta">
                  <div class="text-body-2 font-weight-medium text-truncate">{{ ch.name }}</div>
                  <div class="text-caption text-medium-emphasis text-truncate">{{ ch.id }}</div>
                </div>
                <v-btn icon variant="text" color="error" size="small" @click="openDelete(i)">
                  <v-icon icon="mdi-trash-can-outline" />
                  <v-tooltip activator="parent" location="top">删除</v-tooltip>
                </v-btn>
              </div>
            </v-card>
          </div>
          <div v-else class="empty-state">
            <v-icon icon="mdi-account-group-off-outline" size="48" class="mb-2" />
            <div class="text-body-2">暂未添加任何 TG 频道</div>
          </div>
        </v-window-item>
      </v-window>
    </v-card>

    <!-- 批量导入弹窗 -->
    <v-dialog v-model="importDialog" max-width="640">
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center px-4 py-3">
          <v-icon icon="mdi-import" class="mr-2" />批量导入频道
        </v-card-title>
        <v-divider />
        <v-card-text class="px-4 py-4">
          <v-textarea
            v-model="importJson"
            label="粘贴 JSON 格式的频道数据"
            variant="outlined"
            rows="8"
            auto-grow
            placeholder='[{"name":"电影站","id":"@movie_115","enabled":true}]'
            hint='支持格式：[{"name":"频道1","id":"@xxx"}] 或直接 ["@xxx","@yyy"]'
            persistent-hint
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <v-spacer />
          <v-btn variant="text" @click="importDialog = false">取消</v-btn>
          <v-btn color="primary" variant="flat" :loading="saving" @click="confirmImport">确认导入</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认弹窗 -->
    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center px-4 py-3">
          <v-icon icon="mdi-trash-can-outline" color="error" class="mr-2" />确认删除
        </v-card-title>
        <v-divider />
        <v-card-text class="text-body-2 pt-4">
          确定要永久删除频道「<strong>{{ pendingDelete !== null ? channels[pendingDelete]?.name : '' }}</strong>」吗？此操作不可撤销。
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">取消</v-btn>
          <v-btn color="error" variant="flat" @click="confirmDelete">确认删除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 115 扫码登录弹窗 -->
    <v-dialog v-model="qrDialog" max-width="420" @update:model-value="onQrDialogToggle">
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center px-4 py-3">
          <v-icon icon="mdi-qrcode-scan" class="mr-2" />115 扫码登录
        </v-card-title>
        <v-divider />
        <v-card-text class="px-4 py-4 text-center">
          <v-select
            v-model="qrApp"
            :items="qrApps"
            item-title="title"
            item-value="value"
            label="登录端"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-3 text-left"
            @update:model-value="refreshQrcode"
          />
          <div v-if="qrData.qrcode_url" class="d-flex justify-center mb-3">
            <img :src="qrData.qrcode_url" alt="115 二维码" style="max-width: 220px; width: 100%;" />
          </div>
          <div class="d-flex align-center justify-center">
            <v-progress-circular v-if="qrPolling" indeterminate size="18" width="2" class="mr-2" />
            <span class="text-body-2 text-medium-emphasis">{{ qrMsg || '请使用 115 客户端扫码' }}</span>
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <v-btn variant="text" prepend-icon="mdi-refresh" @click="refreshQrcode">刷新二维码</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closeQrcode">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackModel" :color="snackColor" location="top right" timeout="2500">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

const props = defineProps({
  pluginId: { type: String, default: 'TgSearch115' },
  api: { type: Object, default: null },
  initialConfig: { type: Object, default: null },
})
const emit = defineEmits(['save', 'close'])

const pluginBase = computed(() => `plugin/${props.pluginId || 'TgSearch115'}`)

// 默认配置结构（与后端 _default_config 一致）
const DEFAULTS = {
  enabled: false,
  tg_api_id: '',
  tg_api_hash: '',
  tg_session: '',
  tg_max_messages: 200,
  tg_proxy: '',
  p115_cookie: '',
  p115_target: '/电影',
  use_rule_groups: true,
  delay_seconds: 3,
  notify_success: true,
  notify_fail: false,
  tg_channels: [],
}

const config = reactive({ ...DEFAULTS })
const channels = ref([])
const activeTab = ref('bot')
const showSecrets = ref(false)
const saving = ref(false)

const newName = ref('')
const newId = ref('')
const importDialog = ref(false)
const importJson = ref('')
const deleteDialog = ref(false)
const pendingDelete = ref(null)

// 115 扫码登录
const qrDialog = ref(false)
// 115 支持的登录端（friendly 标题 -> app 值，值与 p115client.p115qrcode.APP_TO_SSOENT 一致）
const qrApps = [
  { title: '115 网页端', value: 'web' },
  { title: '115生活_苹果端', value: 'ios' },
  { title: '115网盘_苹果端', value: '115ios' },
  { title: '115生活_安卓端', value: 'android' },
  { title: '115网盘_安卓端', value: '115android' },
  { title: '115生活_苹果平板端', value: 'ipad' },
  { title: '115网盘_苹果平板端', value: '115ipad' },
  { title: '115生活_TV端', value: 'tv' },
  { title: '115生活_Windows端', value: 'windows' },
  { title: '115生活_macOS端', value: 'mac' },
  { title: '115生活_Linux端', value: 'linux' },
  { title: '115生活_微信小程序端', value: 'wechatmini' },
  { title: '115生活_支付宝小程序端', value: 'alipaymini' },
  { title: '115_鸿蒙端', value: 'harmony' },
]
const qrApp = ref('web')
const qrData = reactive({ uid: '', time: '', sign: '', qrcode_url: '', app: 'web' })
const qrMsg = ref('')
const qrPolling = ref(false)
let qrTimer = null

const snackModel = ref(false)
const snackText = ref('')
const snackColor = ref('success')
function snack(text, color = 'success') {
  snackText.value = text
  snackColor.value = color
  snackModel.value = true
}

// 115 登录态：客户端按 Cookie 是否含 UID/CID/SEID 判定（与后端 validate_cookie 一致）
const loginOk = computed(() => {
  const c = String(config.p115_cookie || '')
  return c.length > 0 && ['UID', 'CID', 'SEID'].every((k) => c.includes(k + '='))
})

/* --------------------------- API 调用（兼容 MP 响应封装） --------------------------- */
// MP 的 api.get 可能返回裸数据，也可能包成 {code, success, data, message}，统一兼容。
async function apiGet(path) {
  if (!props.api?.get) return null
  try {
    const res = await props.api.get(`${pluginBase.value}${path}`)
    if (res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res)) return res.data
    return res
  } catch (e) {
    snack('请求失败：' + (e?.message || e), 'error')
    return null
  }
}
async function apiPost(path, data) {
  if (!props.api?.post) return { success: false, message: 'API 不可用（本地预览模式）' }
  try {
    const res = await props.api.post(`${pluginBase.value}${path}`, data)
    return { success: res?.success === true || res?.code === 0, message: res?.message || '' }
  } catch (e) {
    return { success: false, message: String(e?.message || e) }
  }
}

/* --------------------------- 配置装载 --------------------------- */
function applyConfig(cfg) {
  if (!cfg || typeof cfg !== 'object') return
  Object.keys(DEFAULTS).forEach((k) => {
    if (cfg[k] !== undefined) config[k] = cfg[k]
  })
  const list = Array.isArray(cfg.tg_channels) ? cfg.tg_channels : []
  channels.value = list.map((c, i) => ({
    uid: c.uid ?? i + 1,
    name: c.name || c.id || c.link || '',
    id: c.id || c.link || c.channel || '',
    enabled: c.enabled !== false,
  }))
}

onMounted(async () => {
  // get_form 返回空桩，MP 传入的 initialConfig 为空；始终从 /config/get 读取真实保存的配置
  await loadConfig()
})

async function loadConfig() {
  const data = await apiGet('/config/get')
  if (data) applyConfig(data)
}

/* --------------------------- 115 扫码登录 --------------------------- */
async function openQrcode() {
  qrDialog.value = true
  await refreshQrcode()
}
async function refreshQrcode() {
  stopQrPoll()
  qrMsg.value = '正在获取二维码…'
  qrData.qrcode_url = ''
  const res = await apiGet(`/qrcode/get?app=${encodeURIComponent(qrApp.value)}`)
  if (res && res.success) {
    qrData.uid = res.uid
    qrData.time = res.time
    qrData.sign = res.sign
    qrData.app = res.app
    qrData.qrcode_url = res.qrcode_url
    qrMsg.value = '请使用 115 客户端扫码'
    startQrPoll()
  } else {
    qrMsg.value = (res && res.message) || '获取二维码失败'
  }
}
function startQrPoll() {
  stopQrPoll()
  qrPolling.value = true
  const poll = async () => {
    if (!qrDialog.value || !qrData.uid) {
      stopQrPoll()
      return
    }
    const res = await apiGet(
      `/qrcode/status?uid=${encodeURIComponent(qrData.uid)}&time=${encodeURIComponent(qrData.time)}`
      + `&sign=${encodeURIComponent(qrData.sign)}&app=${encodeURIComponent(qrData.app)}`,
    )
    if (!res) {
      qrTimer = setTimeout(poll, 3000)
      return
    }
    qrMsg.value = res.msg || ''
    if (res.login_ok) {
      stopQrPoll()
      snack('115 扫码登录成功')
      qrDialog.value = false
      await loadConfig()
      return
    }
    if (res.status < 0) {
      // 过期 / 取消，停止轮询，用户可点「刷新二维码」
      stopQrPoll()
      return
    }
    qrTimer = setTimeout(poll, 2000)
  }
  qrTimer = setTimeout(poll, 1500)
}
function stopQrPoll() {
  qrPolling.value = false
  if (qrTimer) {
    clearTimeout(qrTimer)
    qrTimer = null
  }
}
function closeQrcode() {
  stopQrPoll()
  qrDialog.value = false
}
function onQrDialogToggle(v) {
  if (!v) stopQrPoll()
}

/* --------------------------- 保存 --------------------------- */
async function saveAll() {
  saving.value = true
  // 提交时只保留后端需要的字段，去掉本地 uid
  config.tg_channels = channels.value.map(({ name, id, enabled }) => ({ name, id, enabled }))
  const res = await apiPost('/config/save', { ...config })
  saving.value = false
  if (res.success) {
    snack(res.message || '配置已保存并生效')
    emit('save', { ...config })
  } else {
    snack(res.message || '保存失败', 'error')
  }
}

/* --------------------------- 频道增删导入 --------------------------- */
let _uid = 1000
function addChannel() {
  const id = (newId.value || '').trim()
  if (!id) {
    snack('请填写频道 ID / 链接', 'warning')
    return
  }
  channels.value.push({ uid: ++_uid, name: (newName.value || '').trim() || id, id, enabled: true })
  newName.value = ''
  newId.value = ''
  snack('频道已添加，正在保存…')
  saveAll()
}
function openDelete(i) {
  pendingDelete.value = i
  deleteDialog.value = true
}
function confirmDelete() {
  const i = pendingDelete.value
  if (i !== null) {
    const removed = channels.value.splice(i, 1)[0]
    snack(`已删除「${removed?.name || '频道'}」`, 'info')
  }
  deleteDialog.value = false
  pendingDelete.value = null
  saveAll()
}
function openImport() {
  importJson.value = ''
  importDialog.value = true
}
function confirmImport() {
  let data
  try {
    data = JSON.parse(importJson.value || '[]')
  } catch (e) {
    snack('JSON 解析失败：' + e.message, 'error')
    return
  }
  if (!Array.isArray(data)) {
    snack('内容需为 JSON 数组', 'error')
    return
  }
  const parsed = []
  for (const d of data) {
    if (typeof d === 'string') {
      if (d.trim()) parsed.push({ uid: ++_uid, name: d.trim(), id: d.trim(), enabled: true })
      continue
    }
    if (d && typeof d === 'object') {
      const id = String(d.id || d.link || d.channel || '').trim()
      if (!id) continue
      parsed.push({ uid: ++_uid, name: String(d.name || id).trim(), id, enabled: d.enabled !== false })
    }
  }
  if (!parsed.length) {
    snack('未解析到有效频道', 'warning')
    return
  }
  channels.value.push(...parsed)
  importDialog.value = false
  snack(`已导入 ${parsed.length} 个频道，正在保存…`)
  saveAll()
}
</script>

<style scoped>
.tg115-config {
  max-width: 960px;
  margin: 0 auto;
}
.tg115-card {
  background-color: rgb(var(--v-theme-surface));
  border-color: rgba(var(--v-theme-on-surface), 0.12);
}
.section-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.add-card {
  background-color: rgba(var(--v-theme-primary), 0.06);
}
.channel-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.channel-item {
  background-color: rgb(var(--v-theme-surface));
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.channel-item:hover {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 2px 10px rgba(var(--v-theme-on-surface), 0.08);
}
.channel-meta {
  min-width: 0;
  flex: 1 1 auto;
}
.empty-state {
  text-align: center;
  padding: 36px 16px;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
</style>
