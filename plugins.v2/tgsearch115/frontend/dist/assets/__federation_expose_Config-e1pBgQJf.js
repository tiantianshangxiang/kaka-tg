import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withKeys:_withKeys,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "tg115-config" };
const _hoisted_2 = { class: "d-flex justify-end mt-4" };
const _hoisted_3 = { class: "d-flex ga-2 mb-3" };
const _hoisted_4 = {
  key: 0,
  class: "channel-list"
};
const _hoisted_5 = { class: "d-flex align-center px-3 py-2" };
const _hoisted_6 = { class: "channel-meta" };
const _hoisted_7 = { class: "text-body-2 font-weight-medium text-truncate" };
const _hoisted_8 = { class: "text-caption text-medium-emphasis text-truncate" };
const _hoisted_9 = {
  key: 1,
  class: "empty-state"
};
const _hoisted_10 = { class: "d-flex align-center mb-2" };
const _hoisted_11 = {
  key: 0,
  class: "channel-list"
};
const _hoisted_12 = { class: "d-flex align-center px-3 py-2" };
const _hoisted_13 = { class: "channel-meta" };
const _hoisted_14 = { class: "text-body-2 font-weight-medium text-truncate" };
const _hoisted_15 = { class: "text-caption text-medium-emphasis text-truncate" };
const _hoisted_16 = {
  key: 1,
  class: "empty-state"
};
const _hoisted_17 = {
  key: 0,
  class: "d-flex justify-center mb-3"
};
const _hoisted_18 = ["src"];
const _hoisted_19 = { class: "d-flex align-center justify-center" };
const _hoisted_20 = { class: "text-body-2 text-medium-emphasis" };

const {computed,onMounted,reactive,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  pluginId: { type: String, default: 'TgSearch115' },
  api: { type: Object, default: null },
  initialConfig: { type: Object, default: null },
},
  emits: ['save', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const pluginBase = computed(() => `plugin/${props.pluginId || 'TgSearch115'}`);

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
};

const config = reactive({ ...DEFAULTS });
const channels = ref([]);
const activeTab = ref('transfer');
const showSecrets = ref(false);
const saving = ref(false);

const newName = ref('');
const newId = ref('');
const importDialog = ref(false);
const importJson = ref('');
const deleteDialog = ref(false);
const pendingDelete = ref(null);

// 115 扫码登录
const qrDialog = ref(false);
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
];
const qrApp = ref('web');

// 手动转存 / 手动搜索
const transferUrl = ref('');
const transferTarget = ref('');
const transferLoading = ref(false);
const transferResult = ref(null);
const searchKeyword = ref('');
const searchLoading = ref(false);
const searchResults = ref([]);
const searched = ref(false);
const transferLabel = computed(() => `115 转存目录（留空用默认：${config.p115_target || '/'}；也可填 cid）`);
const qrData = reactive({ uid: '', time: '', sign: '', qrcode_url: '', app: 'web' });
const qrMsg = ref('');
const qrPolling = ref(false);
let qrTimer = null;

const snackModel = ref(false);
const snackText = ref('');
const snackColor = ref('success');
function snack(text, color = 'success') {
  snackText.value = text;
  snackColor.value = color;
  snackModel.value = true;
}

// 115 登录态：客户端按 Cookie 是否含 UID/CID/SEID 判定（与后端 validate_cookie 一致）
const loginOk = computed(() => {
  const c = String(config.p115_cookie || '');
  return c.length > 0 && ['UID', 'CID', 'SEID'].every((k) => c.includes(k + '='))
});

/* --------------------------- API 调用（兼容 MP 响应封装） --------------------------- */
// MP 的 api.get 可能返回裸数据，也可能包成 {code, success, data, message}，统一兼容。
async function apiGet(path) {
  if (!props.api?.get) return null
  try {
    const res = await props.api.get(`${pluginBase.value}${path}`);
    if (res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res)) return res.data
    return res
  } catch (e) {
    const detail = e?.response?.data?.message || e?.message || e;
    snack('请求失败：' + detail, 'error');
    return null
  }
}
async function apiPost(path, data) {
  if (!props.api?.post) return { success: false, message: 'API 不可用（本地预览模式）' }
  try {
    const res = await props.api.post(`${pluginBase.value}${path}`, data);
    return { success: res?.success === true || res?.code === 0, message: res?.message || '' }
  } catch (e) {
    return { success: false, message: String(e?.message || e) }
  }
}

/* --------------------------- 配置装载 --------------------------- */
function applyConfig(cfg) {
  if (!cfg || typeof cfg !== 'object') return
  Object.keys(DEFAULTS).forEach((k) => {
    if (cfg[k] !== undefined) config[k] = cfg[k];
  });
  const list = Array.isArray(cfg.tg_channels) ? cfg.tg_channels : [];
  channels.value = list.map((c, i) => ({
    uid: c.uid ?? i + 1,
    name: c.name || c.id || c.link || '',
    id: c.id || c.link || c.channel || '',
    enabled: c.enabled !== false,
  }));
}

onMounted(async () => {
  // get_form 返回空桩，MP 传入的 initialConfig 为空；始终从 /config/get 读取真实保存的配置
  await loadConfig();
});

async function loadConfig() {
  const data = await apiGet('/config/get');
  if (data) applyConfig(data);
}

/* 清空 115 Cookie 并立即保存（用于清掉残留/无效值） */
function clearCookie() {
  config.p115_cookie = '';
  snack('Cookie 已清空，正在保存…');
  saveAll();
}

/* --------------------------- 115 扫码登录 --------------------------- */
async function openQrcode() {
  qrDialog.value = true;
  await refreshQrcode();
}
async function refreshQrcode() {
  stopQrPoll();
  qrMsg.value = '正在获取二维码…';
  qrData.qrcode_url = '';
  const res = await apiGet(`/qrcode/get?app=${encodeURIComponent(qrApp.value)}`);
  if (res && res.success) {
    qrData.uid = res.uid;
    qrData.time = res.time;
    qrData.sign = res.sign;
    qrData.app = res.app;
    qrData.qrcode_url = res.qrcode_url;
    qrMsg.value = '请使用 115 客户端扫码';
    startQrPoll();
  } else {
    qrMsg.value = (res && res.message) || '获取二维码失败';
  }
}
function startQrPoll() {
  stopQrPoll();
  qrPolling.value = true;
  const poll = async () => {
    if (!qrDialog.value || !qrData.uid) {
      stopQrPoll();
      return
    }
    const res = await apiGet(
      `/qrcode/status?uid=${encodeURIComponent(qrData.uid)}&time=${encodeURIComponent(qrData.time)}`
      + `&sign=${encodeURIComponent(qrData.sign)}&app=${encodeURIComponent(qrData.app)}`,
    );
    if (!res) {
      qrTimer = setTimeout(poll, 3000);
      return
    }
    qrMsg.value = res.msg || '';
    if (res.login_ok) {
      stopQrPoll();
      snack('115 扫码登录成功');
      qrDialog.value = false;
      await loadConfig();
      return
    }
    if (res.status < 0) {
      // 过期 / 取消，停止轮询，用户可点「刷新二维码」
      stopQrPoll();
      return
    }
    qrTimer = setTimeout(poll, 2000);
  };
  qrTimer = setTimeout(poll, 1500);
}
function stopQrPoll() {
  qrPolling.value = false;
  if (qrTimer) {
    clearTimeout(qrTimer);
    qrTimer = null;
  }
}
function closeQrcode() {
  stopQrPoll();
  qrDialog.value = false;
}
function onQrDialogToggle(v) {
  if (!v) stopQrPoll();
}

/* --------------------------- 手动转存 / 手动搜索 --------------------------- */
async function doTransfer() {
  const url = (transferUrl.value || '').trim();
  if (!url) { snack('请输入 115 分享链接', 'warning'); return }
  transferLoading.value = true;
  transferResult.value = null;
  const target = (transferTarget.value || '').trim();
  const res = await apiGet(`/transfer?share_url=${encodeURIComponent(url)}&target=${encodeURIComponent(target)}`);
  transferLoading.value = false;
  if (res) {
    transferResult.value = res;
    snack(res.message || (res.success ? '转存成功' : '转存失败'), res.success ? 'success' : 'error');
  } else {
    transferResult.value = { success: false, message: '转存请求失败' };
  }
}
async function transferFromSearch(url) {
  transferUrl.value = url;
  await doTransfer();
}
async function doSearch() {
  const kw = (searchKeyword.value || '').trim();
  if (!kw) { snack('请输入搜索关键字', 'warning'); return }
  searchLoading.value = true;
  searched.value = true;
  searchResults.value = [];
  const res = await apiGet(`/search?keyword=${encodeURIComponent(kw)}`);
  searchLoading.value = false;
  if (res && res.success) {
    searchResults.value = res.results || [];
    snack(res.message || `找到 ${searchResults.value.length} 条`);
  } else {
    snack((res && res.message) || '搜索失败', 'error');
  }
}

/* --------------------------- 保存 --------------------------- */
async function saveAll() {
  saving.value = true;
  // 提交时只保留后端需要的字段，去掉本地 uid
  config.tg_channels = channels.value.map(({ name, id, enabled }) => ({ name, id, enabled }));
  const res = await apiPost('/config/save', { ...config });
  saving.value = false;
  if (res.success) {
    snack(res.message || '配置已保存并生效');
    emit('save', { ...config });
  } else {
    snack(res.message || '保存失败', 'error');
  }
}

/* --------------------------- 频道增删导入 --------------------------- */
let _uid = 1000;
function addChannel() {
  const id = (newId.value || '').trim();
  if (!id) {
    snack('请填写频道 ID / 链接', 'warning');
    return
  }
  channels.value.push({ uid: ++_uid, name: (newName.value || '').trim() || id, id, enabled: true });
  newName.value = '';
  newId.value = '';
  snack('频道已添加，正在保存…');
  saveAll();
}
function openDelete(i) {
  pendingDelete.value = i;
  deleteDialog.value = true;
}
function confirmDelete() {
  const i = pendingDelete.value;
  if (i !== null) {
    const removed = channels.value.splice(i, 1)[0];
    snack(`已删除「${removed?.name || '频道'}」`, 'info');
  }
  deleteDialog.value = false;
  pendingDelete.value = null;
  saveAll();
}
function openImport() {
  importJson.value = '';
  importDialog.value = true;
}
function confirmImport() {
  let data;
  try {
    data = JSON.parse(importJson.value || '[]');
  } catch (e) {
    snack('JSON 解析失败：' + e.message, 'error');
    return
  }
  if (!Array.isArray(data)) {
    snack('内容需为 JSON 数组', 'error');
    return
  }
  const parsed = [];
  for (const d of data) {
    if (typeof d === 'string') {
      if (d.trim()) parsed.push({ uid: ++_uid, name: d.trim(), id: d.trim(), enabled: true });
      continue
    }
    if (d && typeof d === 'object') {
      const id = String(d.id || d.link || d.channel || '').trim();
      if (!id) continue
      parsed.push({ uid: ++_uid, name: String(d.name || id).trim(), id, enabled: d.enabled !== false });
    }
  }
  if (!parsed.length) {
    snack('未解析到有效频道', 'warning');
    return
  }
  channels.value.push(...parsed);
  importDialog.value = false;
  snack(`已导入 ${parsed.length} 个频道，正在保存…`);
  saveAll();
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_tab = _resolveComponent("v-tab");
  const _component_v_tabs = _resolveComponent("v-tabs");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_window_item = _resolveComponent("v-window-item");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_tooltip = _resolveComponent("v-tooltip");
  const _component_v_window = _resolveComponent("v-window");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_dialog = _resolveComponent("v-dialog");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, {
      variant: "outlined",
      rounded: "lg",
      class: "tg115-card mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-cloud-outline",
              color: "primary",
              class: "mr-2"
            }),
            _cache[30] || (_cache[30] = _createElementVNode("span", { class: "text-subtitle-1 font-weight-bold" }, "115 网盘登录", -1)),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_chip, {
              color: loginOk.value ? 'success' : 'grey',
              variant: "tonal",
              size: "small",
              class: "font-weight-medium",
              "prepend-icon": loginOk.value ? 'mdi-check-circle' : 'mdi-alert-circle-outline'
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(loginOk.value ? '已登录' : '未登录'), 1)
              ]),
              _: 1
            }, 8, ["color", "prepend-icon"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_divider),
        _createVNode(_component_v_card_text, { class: "px-4 py-4" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_row, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.p115_cookie,
                      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.p115_cookie) = $event)),
                      type: showSecrets.value ? 'text' : 'password',
                      label: "115 Cookie",
                      variant: "outlined",
                      density: "comfortable",
                      hint: "扫码登录后自动填入；点右侧眼睛可临时显示核对。格式应为 UID=...; CID=...; SEID=...",
                      "persistent-hint": "",
                      "append-inner-icon": showSecrets.value ? 'mdi-eye-off' : 'mdi-eye',
                      "onClick:appendInner": _cache[1] || (_cache[1] = $event => (showSecrets.value = !showSecrets.value)),
                      "append-outer-icon": config.p115_cookie ? 'mdi-close-circle' : undefined,
                      "onClick:appendOuter": clearCookie
                    }, null, 8, ["modelValue", "type", "append-inner-icon", "append-outer-icon"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.p115_target,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.p115_target) = $event)),
                      label: "115 转存目录",
                      variant: "outlined",
                      density: "comfortable",
                      hint: "如 /电影；目录不存在会自动创建；也可填数字 cid",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4",
                  class: "d-flex align-center flex-wrap ga-2"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      color: "primary",
                      variant: "flat",
                      loading: saving.value,
                      "prepend-icon": "mdi-refresh",
                      onClick: saveAll
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(loginOk.value ? '更新凭证' : '登录'), 1)
                      ]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      variant: "outlined",
                      "prepend-icon": "mdi-qrcode-scan",
                      onClick: openQrcode
                    }, {
                      default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
                        _createTextVNode("扫码登录", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_card, {
      variant: "outlined",
      rounded: "lg",
      class: "tg115-card"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_tabs, {
          modelValue: activeTab.value,
          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((activeTab).value = $event)),
          color: "primary",
          density: "comfortable",
          class: "px-2"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_tab, {
              value: "transfer",
              "prepend-icon": "mdi-cloud-download-outline"
            }, {
              default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
                _createTextVNode("手动转存", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_tab, {
              value: "bot",
              "prepend-icon": "mdi-robot-outline"
            }, {
              default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                _createTextVNode("TG 机器人模块", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_tab, {
              value: "search",
              "prepend-icon": "mdi-magnify"
            }, {
              default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
                _createTextVNode("手动搜索", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_tab, {
              value: "channel",
              "prepend-icon": "mdi-bullhorn-outline"
            }, {
              default: _withCtx(() => [...(_cache[35] || (_cache[35] = [
                _createTextVNode("TG 频道模块", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createVNode(_component_v_divider),
        _createVNode(_component_v_window, {
          modelValue: activeTab.value,
          "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((activeTab).value = $event))
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_window_item, {
              value: "transfer",
              class: "pa-4"
            }, {
              default: _withCtx(() => [
                _cache[37] || (_cache[37] = _createElementVNode("div", { class: "section-label mb-2" }, "手动转存 115 资源", -1)),
                _createVNode(_component_v_text_field, {
                  modelValue: transferUrl.value,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((transferUrl).value = $event)),
                  label: "115 分享链接",
                  placeholder: "https://115.com/s/xxxxxxxx?password=yyyy",
                  variant: "outlined",
                  density: "comfortable",
                  "hide-details": "",
                  class: "mb-3"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_v_text_field, {
                  modelValue: transferTarget.value,
                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((transferTarget).value = $event)),
                  label: transferLabel.value,
                  placeholder: "如 /电影  或  cid 数字",
                  variant: "outlined",
                  density: "comfortable",
                  "hide-details": "",
                  class: "mb-3"
                }, null, 8, ["modelValue", "label"]),
                _createVNode(_component_v_btn, {
                  color: "primary",
                  variant: "flat",
                  loading: transferLoading.value,
                  "prepend-icon": "mdi-cloud-download",
                  onClick: doTransfer
                }, {
                  default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
                    _createTextVNode("转存", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                (transferResult.value)
                  ? (_openBlock(), _createBlock(_component_v_alert, {
                      key: 0,
                      type: transferResult.value.success ? 'success' : 'error',
                      variant: "tonal",
                      class: "mt-3",
                      text: transferResult.value.message
                    }, null, 8, ["type", "text"]))
                  : _createCommentVNode("", true)
              ]),
              _: 1
            }),
            _createVNode(_component_v_window_item, {
              value: "bot",
              class: "pa-4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6",
                      class: "d-flex align-center"
                    }, {
                      default: _withCtx(() => [
                        _cache[38] || (_cache[38] = _createElementVNode("div", { class: "mr-2" }, [
                          _createElementVNode("div", { class: "text-subtitle-2" }, "功能总开关"),
                          _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "开启后监听订阅新增事件并自动检索 TG 频道")
                        ], -1)),
                        _createVNode(_component_v_spacer),
                        _createVNode(_component_v_switch, {
                          modelValue: config.enabled,
                          "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.enabled) = $event)),
                          color: "primary",
                          "hide-details": "",
                          density: "compact"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6",
                      class: "d-flex align-center"
                    }, {
                      default: _withCtx(() => [
                        _cache[39] || (_cache[39] = _createElementVNode("div", { class: "mr-2" }, [
                          _createElementVNode("div", { class: "text-subtitle-2" }, "MP 过滤规则组二次匹配"),
                          _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "复用 MoviePilot 订阅过滤规则组对命中资源再过滤")
                        ], -1)),
                        _createVNode(_component_v_spacer),
                        _createVNode(_component_v_switch, {
                          modelValue: config.use_rule_groups,
                          "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.use_rule_groups) = $event)),
                          color: "primary",
                          "hide-details": "",
                          density: "compact"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _cache[43] || (_cache[43] = _createElementVNode("div", { class: "section-label mt-4 mb-2" }, "Telegram 会话凭证（User Session）", -1)),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.tg_api_id,
                          "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.tg_api_id) = $event)),
                          label: "TG API ID",
                          variant: "outlined",
                          density: "comfortable",
                          hint: "在 my.telegram.org 申请的 API ID（数字）",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.tg_api_hash,
                          "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.tg_api_hash) = $event)),
                          type: showSecrets.value ? 'text' : 'password',
                          label: "TG API Hash",
                          variant: "outlined",
                          density: "comfortable",
                          hint: "在 my.telegram.org 申请的 API Hash",
                          "persistent-hint": "",
                          "append-inner-icon": showSecrets.value ? 'mdi-eye-off' : 'mdi-eye',
                          "onClick:appendInner": _cache[10] || (_cache[10] = $event => (showSecrets.value = !showSecrets.value))
                        }, null, 8, ["modelValue", "type", "append-inner-icon"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, { cols: "12" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.tg_session,
                          "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.tg_session) = $event)),
                          type: showSecrets.value ? 'text' : 'password',
                          label: "TG Session String",
                          variant: "outlined",
                          density: "comfortable",
                          hint: "用 gen_tg_session.py 在本地生成后粘贴（容器内无法交互登录）",
                          "persistent-hint": "",
                          "append-inner-icon": showSecrets.value ? 'mdi-eye-off' : 'mdi-eye',
                          "onClick:appendInner": _cache[12] || (_cache[12] = $event => (showSecrets.value = !showSecrets.value))
                        }, null, 8, ["modelValue", "type", "append-inner-icon"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "4"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.tg_proxy,
                          "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.tg_proxy) = $event)),
                          label: "TG 代理",
                          variant: "outlined",
                          density: "comfortable",
                          placeholder: "socks5://host:port",
                          hint: "可选；SOCKS 需另装 telethon[socks]",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "4"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.tg_max_messages,
                          "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.tg_max_messages) = $event)),
                          label: "最大检索消息数",
                          variant: "outlined",
                          density: "comfortable",
                          type: "number",
                          hint: "每个频道最多检索的历史消息数",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "4"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.delay_seconds,
                          "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.delay_seconds) = $event)),
                          label: "触发延迟（秒）",
                          variant: "outlined",
                          density: "comfortable",
                          type: "number",
                          hint: "订阅创建后等待几秒再触发",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _cache[44] || (_cache[44] = _createElementVNode("div", { class: "section-label mt-2 mb-1" }, "通知", -1)),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6",
                      class: "d-flex align-center"
                    }, {
                      default: _withCtx(() => [
                        _cache[40] || (_cache[40] = _createElementVNode("span", { class: "text-body-2 mr-2" }, "转存成功通知", -1)),
                        _createVNode(_component_v_switch, {
                          modelValue: config.notify_success,
                          "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.notify_success) = $event)),
                          color: "primary",
                          "hide-details": "",
                          density: "compact"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6",
                      class: "d-flex align-center"
                    }, {
                      default: _withCtx(() => [
                        _cache[41] || (_cache[41] = _createElementVNode("span", { class: "text-body-2 mr-2" }, "未命中 / 失败通知", -1)),
                        _createVNode(_component_v_switch, {
                          modelValue: config.notify_fail,
                          "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((config.notify_fail) = $event)),
                          color: "primary",
                          "hide-details": "",
                          density: "compact"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createElementVNode("div", _hoisted_2, [
                  _createVNode(_component_v_btn, {
                    color: "primary",
                    variant: "flat",
                    loading: saving.value,
                    "prepend-icon": "mdi-content-save",
                    onClick: saveAll
                  }, {
                    default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                      _createTextVNode(" 保存该模块配置 ", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"])
                ])
              ]),
              _: 1
            }),
            _createVNode(_component_v_window_item, {
              value: "search",
              class: "pa-4"
            }, {
              default: _withCtx(() => [
                _cache[48] || (_cache[48] = _createElementVNode("div", { class: "section-label mb-2" }, "手动搜索 TG 频道 115 资源", -1)),
                _createElementVNode("div", _hoisted_3, [
                  _createVNode(_component_v_text_field, {
                    modelValue: searchKeyword.value,
                    "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((searchKeyword).value = $event)),
                    label: "搜索关键字（影片名 + 年份）",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": "",
                    onKeyup: _withKeys(doSearch, ["enter"])
                  }, null, 8, ["modelValue"]),
                  _createVNode(_component_v_btn, {
                    color: "primary",
                    variant: "flat",
                    loading: searchLoading.value,
                    "prepend-icon": "mdi-magnify",
                    onClick: doSearch
                  }, {
                    default: _withCtx(() => [...(_cache[45] || (_cache[45] = [
                      _createTextVNode("搜索", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"])
                ]),
                (searchResults.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_4, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(searchResults.value, (r, i) => {
                        return (_openBlock(), _createBlock(_component_v_card, {
                          key: i,
                          variant: "outlined",
                          rounded: "lg",
                          class: "channel-item"
                        }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_5, [
                              _createVNode(_component_v_icon, {
                                icon: "mdi-file-video-outline",
                                color: "primary",
                                class: "mr-3"
                              }),
                              _createElementVNode("div", _hoisted_6, [
                                _createElementVNode("div", _hoisted_7, _toDisplayString(r.title), 1),
                                _createElementVNode("div", _hoisted_8, _toDisplayString(r.channel) + " · " + _toDisplayString(r.share_url), 1)
                              ]),
                              _createVNode(_component_v_btn, {
                                color: "primary",
                                variant: "tonal",
                                size: "small",
                                "prepend-icon": "mdi-cloud-download",
                                loading: transferLoading.value,
                                onClick: $event => (transferFromSearch(r.share_url))
                              }, {
                                default: _withCtx(() => [...(_cache[46] || (_cache[46] = [
                                  _createTextVNode("转存", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading", "onClick"])
                            ])
                          ]),
                          _: 2
                        }, 1024))
                      }), 128))
                    ]))
                  : (searched.value)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_9, [
                        _createVNode(_component_v_icon, {
                          icon: "mdi-magnify-close",
                          size: "48",
                          class: "mb-2"
                        }),
                        _cache[47] || (_cache[47] = _createElementVNode("div", { class: "text-body-2" }, "未找到 115 资源", -1))
                      ]))
                    : _createCommentVNode("", true)
              ]),
              _: 1
            }),
            _createVNode(_component_v_window_item, {
              value: "channel",
              class: "pa-4"
            }, {
              default: _withCtx(() => [
                _cache[54] || (_cache[54] = _createElementVNode("div", { class: "section-label mb-2" }, "添加频道", -1)),
                _createVNode(_component_v_card, {
                  variant: "tonal",
                  color: "primary",
                  rounded: "lg",
                  class: "mb-4 add-card"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card_text, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_row, { align: "center" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_col, {
                              cols: "12",
                              md: "4"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_text_field, {
                                  modelValue: newName.value,
                                  "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((newName).value = $event)),
                                  label: "频道名称",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, {
                              cols: "12",
                              md: "5"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_text_field, {
                                  modelValue: newId.value,
                                  "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((newId).value = $event)),
                                  label: "频道 ID / 链接",
                                  variant: "outlined",
                                  density: "comfortable",
                                  hint: "@用户名 / 邀请链接 / 数字 ID",
                                  "persistent-hint": ""
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, {
                              cols: "12",
                              md: "3",
                              class: "d-flex justify-md-end"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_btn, {
                                  color: "primary",
                                  variant: "flat",
                                  "prepend-icon": "mdi-plus",
                                  onClick: addChannel
                                }, {
                                  default: _withCtx(() => [...(_cache[49] || (_cache[49] = [
                                    _createTextVNode("保存 / 添加", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createElementVNode("div", _hoisted_10, [
                  _cache[51] || (_cache[51] = _createElementVNode("span", { class: "section-label" }, "已添加频道", -1)),
                  _createVNode(_component_v_chip, {
                    size: "small",
                    variant: "tonal",
                    class: "ml-2"
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(channels.value.length), 1)
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_spacer),
                  _createVNode(_component_v_btn, {
                    color: "secondary",
                    variant: "tonal",
                    "prepend-icon": "mdi-import",
                    onClick: openImport
                  }, {
                    default: _withCtx(() => [...(_cache[50] || (_cache[50] = [
                      _createTextVNode("批量导入", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                (channels.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(channels.value, (ch, i) => {
                        return (_openBlock(), _createBlock(_component_v_card, {
                          key: ch.uid || i,
                          variant: "outlined",
                          rounded: "lg",
                          class: "channel-item"
                        }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_12, [
                              _createVNode(_component_v_icon, {
                                icon: "mdi-bullhorn-variant-outline",
                                color: "primary",
                                class: "mr-3"
                              }),
                              _createElementVNode("div", _hoisted_13, [
                                _createElementVNode("div", _hoisted_14, _toDisplayString(ch.name), 1),
                                _createElementVNode("div", _hoisted_15, _toDisplayString(ch.id), 1)
                              ]),
                              _createVNode(_component_v_btn, {
                                icon: "",
                                variant: "text",
                                color: "error",
                                size: "small",
                                onClick: $event => (openDelete(i))
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_icon, { icon: "mdi-trash-can-outline" }),
                                  _createVNode(_component_v_tooltip, {
                                    activator: "parent",
                                    location: "top"
                                  }, {
                                    default: _withCtx(() => [...(_cache[52] || (_cache[52] = [
                                      _createTextVNode("删除", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }, 8, ["onClick"])
                            ])
                          ]),
                          _: 2
                        }, 1024))
                      }), 128))
                    ]))
                  : (_openBlock(), _createElementBlock("div", _hoisted_16, [
                      _createVNode(_component_v_icon, {
                        icon: "mdi-account-group-off-outline",
                        size: "48",
                        class: "mb-2"
                      }),
                      _cache[53] || (_cache[53] = _createElementVNode("div", { class: "text-body-2" }, "暂未添加任何 TG 频道", -1))
                    ]))
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"])
      ]),
      _: 1
    }),
    _createVNode(_component_v_dialog, {
      modelValue: importDialog.value,
      "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((importDialog).value = $event)),
      "max-width": "640"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { rounded: "lg" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  icon: "mdi-import",
                  class: "mr-2"
                }),
                _cache[55] || (_cache[55] = _createTextVNode("批量导入频道 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_text, { class: "px-4 py-4" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_textarea, {
                  modelValue: importJson.value,
                  "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((importJson).value = $event)),
                  label: "粘贴 JSON 格式的频道数据",
                  variant: "outlined",
                  rows: "8",
                  "auto-grow": "",
                  placeholder: "[{\"name\":\"电影站\",\"id\":\"@movie_115\",\"enabled\":true}]",
                  hint: "支持格式：[{\"name\":\"频道1\",\"id\":\"@xxx\"}] 或直接 [\"@xxx\",\"@yyy\"]",
                  "persistent-hint": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_actions, { class: "px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[23] || (_cache[23] = $event => (importDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[56] || (_cache[56] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "primary",
                  variant: "flat",
                  loading: saving.value,
                  onClick: confirmImport
                }, {
                  default: _withCtx(() => [...(_cache[57] || (_cache[57] = [
                    _createTextVNode("确认导入", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: deleteDialog.value,
      "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((deleteDialog).value = $event)),
      "max-width": "420"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { rounded: "lg" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  icon: "mdi-trash-can-outline",
                  color: "error",
                  class: "mr-2"
                }),
                _cache[58] || (_cache[58] = _createTextVNode("确认删除 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_text, { class: "text-body-2 pt-4" }, {
              default: _withCtx(() => [
                _cache[59] || (_cache[59] = _createTextVNode(" 确定要永久删除频道「", -1)),
                _createElementVNode("strong", null, _toDisplayString(pendingDelete.value !== null ? channels.value[pendingDelete.value]?.name : ''), 1),
                _cache[60] || (_cache[60] = _createTextVNode("」吗？此操作不可撤销。 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_actions, { class: "px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[25] || (_cache[25] = $event => (deleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[61] || (_cache[61] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "error",
                  variant: "flat",
                  onClick: confirmDelete
                }, {
                  default: _withCtx(() => [...(_cache[62] || (_cache[62] = [
                    _createTextVNode("确认删除", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: qrDialog.value,
      "onUpdate:modelValue": [
        _cache[28] || (_cache[28] = $event => ((qrDialog).value = $event)),
        onQrDialogToggle
      ],
      "max-width": "420"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { rounded: "lg" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  icon: "mdi-qrcode-scan",
                  class: "mr-2"
                }),
                _cache[63] || (_cache[63] = _createTextVNode("115 扫码登录 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_text, { class: "px-4 py-4 text-center" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_select, {
                  modelValue: qrApp.value,
                  "onUpdate:modelValue": [
                    _cache[27] || (_cache[27] = $event => ((qrApp).value = $event)),
                    refreshQrcode
                  ],
                  items: qrApps,
                  "item-title": "title",
                  "item-value": "value",
                  label: "登录端",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  class: "mb-3 text-left"
                }, null, 8, ["modelValue"]),
                (qrData.qrcode_url)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_17, [
                      _createElementVNode("img", {
                        src: qrData.qrcode_url,
                        alt: "115 二维码",
                        style: {"max-width":"220px","width":"100%"}
                      }, null, 8, _hoisted_18)
                    ]))
                  : _createCommentVNode("", true),
                _createElementVNode("div", _hoisted_19, [
                  (qrPolling.value)
                    ? (_openBlock(), _createBlock(_component_v_progress_circular, {
                        key: 0,
                        indeterminate: "",
                        size: "18",
                        width: "2",
                        class: "mr-2"
                      }))
                    : _createCommentVNode("", true),
                  _createElementVNode("span", _hoisted_20, _toDisplayString(qrMsg.value || '请使用 115 客户端扫码'), 1)
                ])
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_actions, { class: "px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  variant: "text",
                  "prepend-icon": "mdi-refresh",
                  onClick: refreshQrcode
                }, {
                  default: _withCtx(() => [...(_cache[64] || (_cache[64] = [
                    _createTextVNode("刷新二维码", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: closeQrcode
                }, {
                  default: _withCtx(() => [...(_cache[65] || (_cache[65] = [
                    _createTextVNode("关闭", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackModel.value,
      "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((snackModel).value = $event)),
      color: snackColor.value,
      location: "top right",
      timeout: "2500"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(snackText.value), 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-c2960420"]]);

export { Config as default };
