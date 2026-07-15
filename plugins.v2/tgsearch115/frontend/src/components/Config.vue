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
        <v-switch v-model="config.enabled" color="success" hide-details density="compact" inset class="ml-2" />
        <v-spacer />
        <v-btn size="small" color="primary" variant="flat" :loading="saving" prepend-icon="mdi-content-save" @click="saveAll">保存凭证</v-btn>
        <v-btn size="small" variant="outlined" prepend-icon="mdi-qrcode-scan" @click="openQrcode" class="ml-2">扫码登录</v-btn>
        <v-chip :color="loginStatusColor" variant="tonal" size="small" class="font-weight-medium ml-2" :prepend-icon="loginStatusIcon">{{ loginStatusText }}</v-chip>
        <v-btn v-if="loginOk" size="small" variant="text" :loading="verifyLoading" @click="verifyCookie" class="ml-1">验证</v-btn>
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
              hint="扫码登录后自动填入；点右侧眼睛可临时显示核对。格式应为 UID=...; CID=...; SEID=..."
              persistent-hint
              :append-inner-icon="showSecrets ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showSecrets = !showSecrets"
              :append-outer-icon="config.p115_cookie ? 'mdi-close-circle' : undefined"
              @click:append-outer="clearCookie"
            />
          </v-col>
          <v-col cols="12" md="8">
            <v-text-field
              v-model="config.p115_target"
              label="115 转存目录"
              variant="outlined"
              density="comfortable"
              :hint="targetPathName ? `📁 ${targetPathName}` : '如 /电影；目录不存在会自动创建；也可填数字 cid'"
              persistent-hint
              @update:model-value="onTargetChange"
            />
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center">
            <v-btn variant="outlined" prepend-icon="mdi-folder-open" @click="openDirBrowser('target')">选择目录</v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- ============ 第 ② + ③ 段：Tabs + 内容区 ============ -->
    <v-card variant="outlined" rounded="lg" class="tg115-card">
      <v-tabs v-model="activeTab" color="primary" density="comfortable" class="px-2">
        <v-tab value="transfer" prepend-icon="mdi-cloud-download-outline">手动转存</v-tab>
        <v-tab value="search" prepend-icon="mdi-magnify">手动搜索</v-tab>
        <v-tab value="channel" prepend-icon="mdi-bullhorn-outline">TG 频道模块</v-tab>
        <v-tab value="settings" prepend-icon="mdi-cog-outline">插件设置</v-tab>
      </v-tabs>
      <v-divider />

      <v-window v-model="activeTab">
        <!-- ====== Tab：手动转存（默认） ====== -->
        <v-window-item value="transfer" class="pa-4">
          <div class="section-label mb-2">手动转存 115 资源</div>
          <v-text-field
            v-model="transferUrl"
            label="115 分享链接"
            placeholder="https://115.com/s/xxxxxxxx?password=yyyy"
            variant="outlined"
            density="comfortable"
            hide-details
            class="mb-3"
          />
          <v-text-field
            v-model="transferTarget"
            :label="transferLabel"
            placeholder="如 /电影  或  cid 数字"
            variant="outlined"
            density="comfortable"
            hide-details
            class="mb-2"
            @update:model-value="onTransferTargetChange"
          />
          <div v-if="dirInfoName" class="text-caption text-success mb-2">📁 当前 cid 目录：{{ dirInfoName }}</div>
          <div class="d-flex ga-2 mb-3">
            <v-btn color="primary" variant="flat" :loading="transferLoading" prepend-icon="mdi-cloud-download" @click="doTransfer">转存</v-btn>
            <v-btn variant="outlined" prepend-icon="mdi-folder-open" @click="openDirBrowser('transfer')">选择目录</v-btn>
          </div>
          <v-alert
            v-if="transferResult"
            :type="transferResult.success ? 'success' : 'error'"
            variant="tonal"
            class="mt-3"
            :text="transferResult.message"
          />
        </v-window-item>

        <!-- ====== Tab：手动搜索 ====== -->
        <v-window-item value="search" class="pa-4">
          <div class="section-label mb-2">手动搜索 TG 频道 115 资源</div>
          <div class="d-flex ga-2 mb-3">
            <v-text-field
              v-model="searchKeyword"
              label="搜索关键字（影片名 + 年份）"
              variant="outlined"
              density="comfortable"
              hide-details
              @keyup.enter="doSearch"
            />
            <v-btn color="primary" variant="flat" :loading="searchLoading" prepend-icon="mdi-magnify" @click="doSearch">搜索</v-btn>
          </div>
          <div v-if="searchLoading" class="empty-state">
            <v-progress-circular indeterminate size="40" width="3" color="primary" class="mb-3" />
            <div class="text-body-2">正在搜索 TG 频道...</div>
          </div>
          <div v-else-if="searchResults.length" class="channel-list">
            <v-card v-for="(r, i) in searchResults.slice(0, displayLimit)" :key="i" variant="outlined" rounded="lg" class="channel-item mb-2">
              <div class="px-3 pt-2 pb-1">
                <div class="d-flex align-start">
                  <v-icon icon="mdi-file-video-outline" color="primary" class="mr-3 mt-1" />
                  <div class="channel-meta flex-grow-1">
                    <div class="text-body-2 font-weight-medium">{{ r.title }}</div>
                    <div class="text-caption text-medium-emphasis mt-1" style="white-space: pre-wrap; max-height: 4.5em; overflow: hidden;">{{ r.text || r.title }}</div>
                    <div class="text-caption text-medium-emphasis mt-1">{{ r.channel }}<span v-if="r.pub_date"> · {{ r.pub_date }}</span></div>
                  </div>
                  <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-cloud-download" :loading="transferringIndex === i" @click="transferFromSearch(r.share_url, i)" class="ml-2 mt-1">转存</v-btn>
                </div>
              </div>
            </v-card>
          </div>
          <div v-if="searchResults.length > displayLimit" class="text-center mt-3 mb-2">
            <v-btn variant="text" color="primary" size="small" @click="loadMoreResults">
              加载更多
              <v-icon icon="mdi-chevron-right" size="small" class="ml-1" style="transform: rotate(90deg);" />
            </v-btn>
          </div>
          <div v-else-if="searched && !searchLoading" class="empty-state">
            <v-icon icon="mdi-magnify-close" size="48" class="mb-2" />
            <div class="text-body-2">未找到 115 资源</div>
            <div class="text-caption text-medium-emphasis mt-1">提示：网页预览版仅显示最近约 20 条消息</div>
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

          <div class="d-flex align-center mb-2 flex-wrap ga-2">
            <span class="section-label">已添加频道</span>
            <v-chip size="small" variant="tonal">{{ channels.length }}</v-chip>
            <v-spacer />
            <template v-if="channelSelectMode">
              <v-btn size="small" variant="text" prepend-icon="mdi-select-all" @click="toggleSelectAll">
                {{ selectedChannels.length === channels.length ? '取消全选' : '全选' }}
              </v-btn>
              <v-btn size="small" color="error" variant="tonal" prepend-icon="mdi-delete-sweep" @click="openBatchDelete">
                删除选中 ({{ selectedChannels.length }})
              </v-btn>
              <v-btn size="small" variant="text" @click="exitSelectMode">退出选择</v-btn>
            </template>
            <template v-else>
              <v-btn size="small" variant="text" prepend-icon="mdi-checkbox-multiple-marked-outline" @click="enterSelectMode">批量删除</v-btn>
              <v-btn color="secondary" variant="tonal" prepend-icon="mdi-import" @click="openImport">批量导入</v-btn>
            </template>
          </div>

          <div v-if="channels.length" class="channel-list">
            <v-card
              v-for="(ch, i) in channels"
              :key="ch.uid || i"
              variant="outlined"
              rounded="lg"
              class="channel-item"
              :class="{ 'channel-selected': selectedChannels.includes(i) }"
            >
              <div class="d-flex align-center px-3 py-2">
                <v-checkbox
                  v-if="channelSelectMode"
                  :model-value="selectedChannels.includes(i)"
                  @update:model-value="toggleChannelSelect(i)"
                  hide-details
                  density="compact"
                  class="mr-2"
                />
                <v-icon icon="mdi-bullhorn-variant-outline" color="primary" class="mr-3" />
                <div class="channel-meta">
                  <div class="text-body-2 font-weight-medium text-truncate">{{ ch.name }}</div>
                  <div class="text-caption text-medium-emphasis text-truncate">{{ ch.id }}</div>
                </div>
                <v-btn v-if="!channelSelectMode" icon variant="text" color="error" size="small" @click="openDelete(i)">
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
        <!-- ====== Tab：插件设置 ====== -->
        <v-window-item value="settings" class="pa-4">
          <v-divider class="mb-4" />
          <v-row>
            <v-col cols="12" md="6" class="d-flex align-center">
              <div class="mr-2">
                <div class="text-subtitle-2">MP 过滤规则组二次匹配</div>
                <div class="text-caption text-medium-emphasis">复用 MoviePilot 订阅过滤规则组</div>
              </div>
              <v-spacer />
              <v-switch v-model="config.use_rule_groups" color="primary" hide-details density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="config.delay_seconds" label="触发延迟（秒）" variant="outlined" density="comfortable" type="number" hide-details hint="订阅创建后等待几秒再触发" persistent-hint />
            </v-col>
            <v-col cols="12" md="6" class="d-flex align-center">
              <span class="text-body-2 mr-2">转存成功通知</span>
              <v-switch v-model="config.notify_success" color="primary" hide-details density="compact" />
            </v-col>
            <v-col cols="12" md="6" class="d-flex align-center">
              <span class="text-body-2 mr-2">未命中通知</span>
              <v-switch v-model="config.notify_fail" color="primary" hide-details density="compact" />
            </v-col>
          </v-row>
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

    <!-- 115 目录浏览弹窗 -->
    <v-dialog v-model="dirBrowserOpen" max-width="560">
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center px-4 py-3">
          <v-icon icon="mdi-folder-open" class="mr-2" />选择 115 目录
        </v-card-title>
        <v-divider />
        <v-card-text class="px-2 py-2" style="max-height: 55vh; overflow-y: auto;">
          <div class="d-flex align-center px-2 py-1 flex-wrap">
            <v-btn variant="text" size="small" prepend-icon="mdi-home" @click="navigateRoot">根目录</v-btn>
            <template v-for="(p, i) in dirBrowserPath.slice(1)" :key="i">
              <v-icon size="small" class="mx-1">mdi-chevron-right</v-icon>
              <span class="text-caption">{{ p.name }}</span>
            </template>
            <v-spacer />
            <v-btn v-if="dirBrowserPath.length > 1" variant="text" size="small" prepend-icon="mdi-arrow-left" @click="navigateUp">上一级</v-btn>
          </div>
          <v-progress-circular v-if="dirBrowserLoading" indeterminate size="20" width="2" class="ma-4" />
          <v-list v-else density="compact" nav>
            <v-list-item v-for="d in dirBrowserDirs" :key="d.cid" @click="navigateInto(d.cid, d.name)">
              <template #prepend><v-icon icon="mdi-folder" color="amber-darken-2" /></template>
              <v-list-item-title>{{ d.name }}</v-list-item-title>
              <template #append>
                <v-btn size="small" variant="tonal" color="primary" @click.stop="selectDir(d.cid, dirBrowserPathStr + '/' + d.name)">选择</v-btn>
              </template>
            </v-list-item>
          </v-list>
          <div v-if="!dirBrowserLoading && !dirBrowserDirs.length" class="empty-state">无子目录</div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <span class="text-caption text-medium-emphasis text-truncate" style="max-width: 60%;">当前: {{ dirBrowserPathStr || '/' }}</span>
          <v-spacer />
          <v-btn variant="text" @click="dirBrowserOpen = false">取消</v-btn>
          <v-btn color="primary" variant="flat" @click="selectCurrent">确认</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 批量删除确认弹窗 -->
    <v-dialog v-model="batchDeleteDialog" max-width="420">
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center px-4 py-3">
          <v-icon icon="mdi-delete-sweep" color="error" class="mr-2" />确认批量删除
        </v-card-title>
        <v-divider />
        <v-card-text class="text-body-2 pt-4">
          确定要删除选中的 <strong>{{ selectedChannels.length }}</strong> 个频道吗？此操作不可撤销。
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <v-spacer />
          <v-btn variant="text" @click="batchDeleteDialog = false">取消</v-btn>
          <v-btn color="error" variant="flat" @click="confirmBatchDelete">确认删除</v-btn>
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
const activeTab = ref('transfer')
const showSecrets = ref(false)
const saving = ref(false)

const newName = ref('')
const newId = ref('')
const importDialog = ref(false)
const importJson = ref('')
const deleteDialog = ref(false)
const pendingDelete = ref(null)
const channelSelectMode = ref(false)
const selectedChannels = ref([])
const batchDeleteDialog = ref(false)

// 115 扫码登录
const qrDialog = ref(false)
// 115 支持的登录端（friendly 标题 -> app 值，值与 p115client.p115qrcode.APP_TO_SSOENT 一致）
const qrApps = [
  { title: '115 网页端', value: 'web' },
  { title: '115生活_苹果端', value: 'ios' },
  { title: '115_苹果端', value: '115ios' },
  { title: '115生活_安卓端', value: 'android' },
  { title: '115_安卓端', value: '115android' },
  { title: '115生活_苹果平板端', value: 'ipad' },
  { title: '115_苹果平板端', value: '115ipad' },
  { title: '115生活_TV端', value: 'tv' },
  { title: '115生活_Windows端', value: 'os_windows' },
  { title: '115生活_macOS端', value: 'os_mac' },
  { title: '115生活_Linux端', value: 'os_linux' },
  { title: '115生活_微信小程序端', value: 'wechatmini' },
  { title: '115生活_支付宝小程序', value: 'alipaymini' },
  { title: '115_鸿蒙端', value: 'harmony' },
]
const qrApp = ref('web')

// 手动转存 / 手动搜索
const transferUrl = ref('')
const transferTarget = ref('')
const transferLoading = ref(false)
const transferResult = ref(null)
const searchKeyword = ref('')
const searchLoading = ref(false)
const searchResults = ref([])
const searched = ref(false)
const displayLimit = ref(3)
const transferringIndex = ref(-1)  // 正在转存的结果索引（-1=无）
// 115 目录查询/浏览
const dirInfoName = ref('')
const dirBrowserOpen = ref(false)
const dirBrowserCid = ref('0')
const dirBrowserParent = ref('0')
const dirBrowserDirs = ref([])
const dirBrowserLoading = ref(false)
const dirBrowserPath = ref([{ cid: '0', name: '根目录' }])
const dirBrowserMode = ref('transfer')
const targetPathName = ref('')
let dirInfoTimer = null
let targetTimer = null
const dirBrowserPathStr = computed(() => {
  const parts = dirBrowserPath.value.slice(1).map((p) => p.name)
  return parts.length ? '/' + parts.join('/') : ''
})
const transferLabel = computed(() => `115 转存目录（留空用默认：${config.p115_target || '/'}；也可填 cid）`)
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

// Cookie 实测有效性（点「验证」按钮调 /verify_cookie 真实验证；null=未验证）
const verifyLoading = ref(false)
const cookieVerified = ref(null)
const loginStatusText = computed(() => {
  if (!loginOk.value) return '未登录'
  if (cookieVerified.value === true) return '已验证'
  if (cookieVerified.value === false) return 'Cookie已失效'
  return '已登录'
})
const loginStatusColor = computed(() => {
  if (!loginOk.value) return 'grey'
  if (cookieVerified.value === false) return 'error'
  return 'success'
})
const loginStatusIcon = computed(() => {
  if (!loginOk.value) return 'mdi-alert-circle-outline'
  if (cookieVerified.value === false) return 'mdi-alert-circle'
  return 'mdi-check-circle'
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
    const detail = e?.response?.data?.message || e?.message || e
    snack('请求失败：' + detail, 'error')
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
  await loadConfig()
  // 每天只验证一次 Cookie（防止频繁验证触发 115 风控）
  if (loginOk.value) {
    try {
      const last = localStorage.getItem('tg115_last_verify')
      const today = new Date().toDateString()
      if (last !== today) {
        verifyCookie()
        localStorage.setItem('tg115_last_verify', today)
      }
    } catch (e) { verifyCookie() }
  }
  // 恢复上次搜索记录
  try {
    const saved = JSON.parse(localStorage.getItem('tg115_last_search') || 'null')
    if (saved && saved.results && saved.results.length) {
      searchKeyword.value = saved.kw || ''
      searchResults.value = saved.results
      searched.value = true
    }
  } catch (e) {}
})

async function loadConfig() {
  const data = await apiGet('/config/get')
  if (data) applyConfig(data)
  cookieVerified.value = null
}

/* 清空 115 Cookie 并立即保存（用于清掉残留/无效值） */
function clearCookie() {
  config.p115_cookie = ''
  snack('Cookie 已清空，正在保存…')
  saveAll()
}

async function verifyCookie() {
  verifyLoading.value = true
  const res = await apiGet('/verify_cookie')
  verifyLoading.value = false
  if (res && res.success) {
    cookieVerified.value = res.valid
    snack(res.message, res.valid ? 'success' : 'error')
  } else {
    cookieVerified.value = false
    snack((res && res.message) || '验证失败', 'error')
  }
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

/* --------------------------- 手动转存 / 手动搜索 --------------------------- */
async function doTransfer() {
  const url = (transferUrl.value || '').trim()
  if (!url) { snack('请输入 115 分享链接', 'warning'); return }
  transferLoading.value = true
  transferResult.value = null
  const target = (transferTarget.value || '').trim()
  const res = await apiGet(`/transfer?share_url=${encodeURIComponent(url)}&target=${encodeURIComponent(target)}`)
  transferLoading.value = false
  if (res) {
    transferResult.value = res
    snack(res.message || (res.success ? '转存成功' : '转存失败'), res.success ? 'success' : 'error')
  } else {
    transferResult.value = { success: false, message: '转存请求失败' }
  }
}
async function transferFromSearch(url, index) {
  transferringIndex.value = index
  transferUrl.value = url
  await doTransfer()
  transferringIndex.value = -1
}
async function doSearch() {
  const kw = (searchKeyword.value || '').trim()
  if (!kw) { snack('请输入搜索关键字', 'warning'); return }
  searchLoading.value = true
  searched.value = true
  searchResults.value = []
  const res = await apiGet(`/search?keyword=${encodeURIComponent(kw)}`)
  searchLoading.value = false
  if (res && res.success) {
    searchResults.value = res.results || []
    snack(res.message || `找到 ${searchResults.value.length} 条`)
    try { localStorage.setItem('tg115_last_search', JSON.stringify({ kw: kw, results: searchResults.value })) } catch (e) {}
  } else {
    snack((res && res.message) || '搜索失败', 'error')
  }
  displayLimit.value = 3
}
function loadMoreResults() {
  displayLimit.value += 10
}

/* --------------------------- 115 目录查询 / 浏览 --------------------------- */
function onTransferTargetChange() {
  clearTimeout(dirInfoTimer)
  dirInfoTimer = setTimeout(async () => {
    const c = (transferTarget.value || '').trim()
    dirInfoName.value = ''
    if (!/^\d+$/.test(c)) return
    const res = await apiGet(`/dir_info?cid=${encodeURIComponent(c)}`)
    if (res && res.success) dirInfoName.value = res.name
  }, 500)
}
function onTargetChange() {
  clearTimeout(targetTimer)
  targetTimer = setTimeout(async () => {
    const c = String(config.p115_target || '').trim()
    if (!/^\d+$/.test(c)) { targetPathName.value = ''; return }
    const res = await apiGet(`/dir_info?cid=${encodeURIComponent(c)}`)
    targetPathName.value = res && res.success ? res.name : ''
  }, 500)
}
async function openDirBrowser(mode = 'transfer') {
  dirBrowserMode.value = mode
  dirBrowserPath.value = [{ cid: '0', name: '根目录' }]
  dirBrowserOpen.value = true
  await loadDirs('0')
}
async function loadDirs(cid) {
  dirBrowserCid.value = cid
  dirBrowserLoading.value = true
  dirBrowserDirs.value = []
  const res = await apiGet(`/dirs?cid=${encodeURIComponent(cid)}`)
  dirBrowserLoading.value = false
  if (res && res.success) dirBrowserDirs.value = res.dirs || []
  else snack((res && res.message) || '获取目录失败', 'error')
}
async function navigateInto(cid, name) {
  dirBrowserPath.value.push({ cid, name })
  await loadDirs(cid)
}
async function navigateUp() {
  if (dirBrowserPath.value.length > 1) dirBrowserPath.value.pop()
  const cur = dirBrowserPath.value[dirBrowserPath.value.length - 1]
  await loadDirs(cur.cid)
}
async function navigateRoot() {
  dirBrowserPath.value = [{ cid: '0', name: '根目录' }]
  await loadDirs('0')
}
function selectDir(cid, path) {
  if (dirBrowserMode.value === 'transfer') {
    transferTarget.value = cid
    dirInfoName.value = path
  } else {
    config.p115_target = cid
    targetPathName.value = path
  }
  dirBrowserOpen.value = false
}
function selectCurrent() {
  const cur = dirBrowserPath.value[dirBrowserPath.value.length - 1]
  selectDir(cur.cid, dirBrowserPathStr.value)
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
  // 查重：频道 ID 已存在则拒绝
  const normalized = id.replace(/^@/, '').toLowerCase().trim()
  for (const ch of channels.value) {
    const existing = (ch.id || '').replace(/^@/, '').toLowerCase().trim()
    if (existing === normalized) {
      snack('该频道已存在，不可重复添加', 'warning')
      return
    }
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
function toggleChannelSelect(i) {
  const idx = selectedChannels.value.indexOf(i)
  if (idx >= 0) {
    selectedChannels.value.splice(idx, 1)
  } else {
    selectedChannels.value.push(i)
  }
}
function toggleSelectAll() {
  if (selectedChannels.value.length === channels.value.length) {
    selectedChannels.value = []
  } else {
    selectedChannels.value = channels.value.map((_, i) => i)
  }
}
function openBatchDelete() {
  if (!selectedChannels.value.length) {
    snack('请先选择要删除的频道', 'warning')
    return
  }
  batchDeleteDialog.value = true
}
function confirmBatchDelete() {
  // 从大到小排序删除，避免索引偏移
  const sorted = [...selectedChannels.value].sort((a, b) => b - a)
  for (const i of sorted) {
    channels.value.splice(i, 1)
  }
  selectedChannels.value = []
  channelSelectMode.value = false
  batchDeleteDialog.value = false
  snack(`已删除 ${sorted.length} 个频道，正在保存...`)
  saveAll()
}
function enterSelectMode() {
  channelSelectMode.value = true
  selectedChannels.value = []
}
function exitSelectMode() {
  channelSelectMode.value = false
  selectedChannels.value = []
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
  // 查重：只导入不重复的
  const existingIds = new Set(channels.value.map(ch => (ch.id || '').replace(/^@/, '').toLowerCase().trim()))
  const unique = parsed.filter(p => {
    const norm = (p.id || '').replace(/^@/, '').toLowerCase().trim()
    if (existingIds.has(norm)) return false
    existingIds.add(norm)
    return true
  })
  const skipped = parsed.length - unique.length
  channels.value.push(...unique)
  importDialog.value = false
  snack(`已导入 ${unique.length} 个频道` + (skipped ? `（跳过 ${skipped} 个重复）` : '') + '，正在保存…')
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
.channel-selected {
  border-color: rgb(var(--v-theme-error)) !important;
  background-color: rgba(var(--v-theme-error), 0.05);
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
