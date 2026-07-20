import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, f as filterSearchResults, R as RESOURCE_FILTERS, Q as QUALITY_FILTERS } from './_plugin-vue_export-helper-BKBpQ8ln.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withKeys:_withKeys,unref:_unref} = await importShared('vue');


const _hoisted_1 = { class: "tg115-page" };
const _hoisted_2 = { class: "text-h6" };
const _hoisted_3 = { class: "text-h6" };
const _hoisted_4 = { class: "text-body-2" };
const _hoisted_5 = { class: "text-body-2" };
const _hoisted_6 = { class: "text-body-2" };
const _hoisted_7 = {
  key: 0,
  class: "d-flex flex-wrap ga-2 mt-3"
};
const _hoisted_8 = { class: "task-title" };
const _hoisted_9 = { class: "text-caption text-medium-emphasis" };
const _hoisted_10 = {
  key: 0,
  class: "text-caption text-error"
};
const _hoisted_11 = { class: "text-caption" };
const _hoisted_12 = { class: "text-right" };
const _hoisted_13 = { class: "d-flex align-center ga-2 mt-2" };
const _hoisted_14 = { class: "filter-row mt-3" };
const _hoisted_15 = { class: "filter-row mt-2" };
const _hoisted_16 = { class: "d-flex align-center mb-2" };
const _hoisted_17 = {
  key: 1,
  class: "text-caption text-medium-emphasis ml-auto"
};
const _hoisted_18 = ["title"];
const _hoisted_19 = {
  key: 0,
  class: "text-caption text-primary font-weight-medium mt-1"
};
const _hoisted_20 = {
  key: 1,
  class: "text-caption text-warning mt-1"
};
const _hoisted_21 = {
  key: 2,
  class: "text-caption text-medium-emphasis line-clamp-3 mt-1"
};
const _hoisted_22 = { class: "text-caption text-medium-emphasis mt-1" };
const _hoisted_23 = {
  key: 0,
  class: "filter-empty"
};
const _hoisted_24 = {
  key: 1,
  class: "d-flex justify-center mt-4"
};
const _hoisted_25 = {
  key: 2,
  class: "text-center text-caption text-medium-emphasis mt-3"
};

const {computed,onMounted,onUnmounted,reactive,ref} = await importShared('vue');

const CACHE_KEY = 'tg115_search_cache';
const PAGE_SIZE = 3;  // 资源站每批作品数（与后端 count=3 一致）

const _sfc_main = {
  __name: 'Page',
  props: {
  pluginId: { type: String, default: 'TgSearch115' },
  api: { type: Object, default: null },
},
  setup(__props) {

const props = __props;

const PID = computed(() => props.pluginId || 'TgSearch115');

// ---- 配置 / 状态 ----
const config = reactive({ enabled: false, p115_cookie: '', cms_url: '', cms_token: '', delay_seconds: 0, tg_channels: [] });
const runtime = reactive({
  scheduler: { running: false, last_run: '', next_run: '', scanned_count: 0, queue_size: 0 },
  sources: {},
  tasks: [],
});
const statusLoading = ref(false);
const retryingBtih = ref('');
let statusTimer = null;
const sourceStates = computed(() => Object.entries(runtime.sources || {}).map(([name, state]) => ({ name, ...state })));
const channelCount = computed(() => (Array.isArray(config.tg_channels) ? config.tg_channels.length : 0));
const loginOk = computed(() => {
  const c = String(config.p115_cookie || '');
  return c.length > 0 && ['UID', 'CID', 'SEID'].every((k) => c.includes(k + '='))
});

// ---- 搜索 ----
// 搜索结果持久化：保存到 localStorage，下次进详情页自动恢复，新搜索覆盖
function loadCache() {
  try {
    const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    return c && Array.isArray(c.results) ? c : null
  } catch { return null }
}
function saveCache(c) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ...c, ts: Date.now() })); } catch {}
}
const _init = loadCache();
const keyword = ref(_init ? _init.keyword : '');
const searchSource = ref('all');
const resourceFilter = ref(_init?.resource_filter || 'all');
const qualityFilter = ref(_init?.quality_filter || 'all');
const results = ref(_init ? _init.results : []);
const offset = ref(_init ? _init.offset || 0 : 0);
const hasMore = ref(_init ? !!_init.has_more : false);
const searching = ref(false);
const loadingMore = ref(false);
const searchMsg = ref(_init ? `已恢复上次搜索「${_init.keyword}」的结果（${_init.results.length} 条）` : '');
const searchOk = ref(!!_init);
const transferringIdx = ref(-1);
const hasTransferable = computed(() => results.value.some(
  (r) => r.pan_type === '115' || r.pan_type === 'magnet',
));
const filteredResults = computed(() => filterSearchResults(
  results.value,
  resourceFilter.value,
  qualityFilter.value,
));

function clearResults() {
  results.value = [];
  searchMsg.value = '';
  searchOk.value = false;
  keyword.value = '';
  offset.value = 0;
  hasMore.value = false;
  try { localStorage.removeItem(CACHE_KEY); } catch {}
}
// snackbar
const snack = ref(false);
const snackColor = ref('');
const snackText = ref('');

const PAN_LABEL = { '115': '115', quark: '夸克', baidu: '百度', aliyun: '阿里', xunlei: '迅雷', cloud189: '天翼', uc: 'UC', magnet: '磁力', other: '其他' };
const PAN_COLOR = { '115': 'success', quark: 'info', baidu: 'error', aliyun: 'cyan', xunlei: 'purple', cloud189: 'indigo', uc: 'orange', magnet: 'deep-purple', other: 'grey' };
function panLabel(t) { return PAN_LABEL[t] || t || '其他' }
function panColor(t) { return PAN_COLOR[t] || 'grey' }
function formatTime(value) {
  if (!value) return '尚未运行'
  const date = new Date(value);
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
  statusLoading.value = true;
  try {
    const res = await props.api.get(`plugin/${PID.value}/runtime/status`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    if (data?.success) {
      Object.assign(runtime.scheduler, data.scheduler || {});
      runtime.sources = data.sources || {};
      runtime.tasks = Array.isArray(data.tasks) ? data.tasks : [];
    }
  } catch {
    // Status refresh is non-blocking; search actions continue to work.
  } finally {
    statusLoading.value = false;
  }
}

async function retryTask(task) {
  if (!props.api?.post || !task?.btih) return
  retryingBtih.value = task.btih;
  try {
    const res = await props.api.post(`plugin/${PID.value}/tasks/retry`, { btih: task.btih });
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    showSnack(data?.message || (data?.success ? '任务已重新提交' : '重试失败'), data?.success ? 'success' : 'error');
    await loadRuntimeStatus();
  } catch (e) {
    showSnack('重试异常：' + (e?.message || e), 'error');
  } finally {
    retryingBtih.value = '';
  }
}

async function doSearch() {
  const kw = (keyword.value || '').trim();
  if (!kw) { showSnack('请输入搜索关键字', 'warning'); return }
  if (!props.api?.get) { showSnack('API 未就绪', 'error'); return }
  searching.value = true;
  searchMsg.value = '';
  try {
    const res = await props.api.get(`plugin/${PID.value}/search?keyword=${encodeURIComponent(kw)}&source=${searchSource.value}`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    if (data && data.success) {
      results.value = Array.isArray(data.results) ? data.results : [];
      searchMsg.value = data.warning || data.message || `找到 ${results.value.length} 条`;
      searchOk.value = !data.warning;
      offset.value = 0;
      hasMore.value = !!data.has_more;
      saveCache({ keyword: kw, results: results.value, offset: 0, has_more: hasMore.value, resource_filter: resourceFilter.value, quality_filter: qualityFilter.value });
    } else {
      results.value = [];
      searchMsg.value = (data && data.message) || '搜索失败';
      searchOk.value = false;
    }
  } catch (e) {
    results.value = [];
    searchMsg.value = '搜索异常：' + (e?.message || e);
    searchOk.value = false;
  } finally {
    searching.value = false;
  }
}

// 加载更多：资源站翻页（下一批作品），追加结果并全局重排（完结优先）
async function loadMore() {
  if (!hasMore.value || loadingMore.value || !props.api?.get) return
  loadingMore.value = true;
  try {
    const next = offset.value + PAGE_SIZE;
    const res = await props.api.get(`plugin/${PID.value}/search?keyword=${encodeURIComponent(keyword.value)}&offset=${next}&source=${searchSource.value}`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    if (data && data.success) {
      const more = Array.isArray(data.results) ? data.results : [];
      results.value = [...results.value, ...more];
      offset.value = next;
      hasMore.value = !!data.has_more;
      // 全局重排：完结优先，集数降序
      results.value.sort((a, b) => (b.is_complete - a.is_complete) || (b.episode_num - a.episode_num));
      saveCache({ keyword: keyword.value, results: results.value, offset: offset.value, has_more: hasMore.value, resource_filter: resourceFilter.value, quality_filter: qualityFilter.value });
      searchMsg.value = `共 ${results.value.length} 条`;
    } else {
      showSnack(data?.message || '加载更多失败', 'error');
    }
  } catch (e) {
    showSnack('加载更多异常：' + (e?.message || e), 'error');
  } finally {
    loadingMore.value = false;
  }
}

// 115 链接：若提取码未附在 URL 上，补上（share_receive 需要 receive_code）
function fullShareUrl(r) {  let url = r.share_url || '';
  const rc = r.receive_code || '';
  if (r.pan_type === '115' && rc && !/[?&](password|receive_code|pwd)=/.test(url)) {
    url += (url.includes('?') ? '&' : '?') + 'password=' + rc;
  }
  return url
}

async function copy(r) {
  const url = fullShareUrl(r);
  try {
    await navigator.clipboard.writeText(url);
    showSnack('已复制链接', 'success');
  } catch {
    showSnack('复制失败，请手动复制', 'error');
  }
}

async function transfer(r, i) {
  if (r.pan_type === '115' && !loginOk.value) {
    showSnack('未登录 115，无法转存', 'error');
    return
  }
  if (r.pan_type === 'magnet' && (!config.cms_url || !config.cms_token)) {
    showSnack('请先在观影设置中配置 CMS 地址和 API Token', 'error');
    return
  }
  transferringIdx.value = i;
  try {
    const res = r.pan_type === 'magnet'
      ? await props.api.post(`plugin/${PID.value}/magnet/offline`, {
          magnet: fullShareUrl(r),
          title: r.display_name || r.title || '',
        })
      : await props.api.get(`plugin/${PID.value}/transfer?share_url=${encodeURIComponent(fullShareUrl(r))}`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    const success = data?.success === true || data?.code === 0;
    showSnack(data?.message || (success ? '任务提交成功' : '转存失败'), success ? 'success' : 'error');
  } catch (e) {
    showSnack('转存异常：' + (e?.message || e), 'error');
  } finally {
    transferringIdx.value = -1;
  }
}

function showSnack(text, color) {
  snackText.value = text;
  snackColor.value = color;
  snack.value = true;
}

onMounted(async () => {
  if (!props.api?.get) return
  try {
    const res = await props.api.get(`plugin/${PID.value}/config/get`);
    const cfg = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    if (cfg && typeof cfg === 'object') Object.assign(config, cfg);
  } catch {
    // 静默
  }
  await loadRuntimeStatus();
  statusTimer = setInterval(loadRuntimeStatus, 30000);
});

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer);
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_tooltip = _resolveComponent("v-tooltip");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_table = _resolveComponent("v-table");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, {
      variant: "outlined",
      rounded: "lg",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-robot-outline",
              color: "primary",
              class: "mr-2"
            }),
            _cache[5] || (_cache[5] = _createTextVNode(" 拦截mp订阅 ", -1)),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_chip, {
              color: config.enabled ? 'success' : 'grey',
              variant: "tonal",
              size: "small"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(config.enabled ? '运行中' : '已停用'), 1)
              ]),
              _: 1
            }, 8, ["color"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_divider),
        _createVNode(_component_v_card_text, { class: "px-4 py-4" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_row, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "TG 频道数", -1)),
                    _createElementVNode("div", _hoisted_2, _toDisplayString(channelCount.value), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[7] || (_cache[7] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "115 登录", -1)),
                    _createElementVNode("div", {
                      class: _normalizeClass(["text-h6", loginOk.value ? 'text-success' : 'text-medium-emphasis'])
                    }, _toDisplayString(loginOk.value ? '已登录' : '未登录'), 3)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "触发延迟", -1)),
                    _createElementVNode("div", _hoisted_3, _toDisplayString(config.delay_seconds || 0) + " 秒", 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[9] || (_cache[9] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "上次周期扫描", -1)),
                    _createElementVNode("div", _hoisted_4, _toDisplayString(formatTime(runtime.scheduler.last_run)), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[10] || (_cache[10] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "下次周期扫描", -1)),
                    _createElementVNode("div", _hoisted_5, _toDisplayString(formatTime(runtime.scheduler.next_run)), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[11] || (_cache[11] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "队列 / 本轮订阅", -1)),
                    _createElementVNode("div", _hoisted_6, _toDisplayString(runtime.scheduler.queue_size || 0) + " / " + _toDisplayString(runtime.scheduler.scanned_count || 0), 1)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            (sourceStates.value.length)
              ? (_openBlock(), _createElementBlock("div", _hoisted_7, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sourceStates.value, (source) => {
                    return (_openBlock(), _createBlock(_component_v_chip, {
                      key: source.name,
                      size: "small",
                      variant: "tonal",
                      color: source.cooldown_seconds > 0 ? 'warning' : 'success'
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(source.name) + " · " + _toDisplayString(source.cooldown_seconds > 0 ? `冷却 ${source.cooldown_seconds}s` : '可用'), 1)
                      ]),
                      _: 2
                    }, 1032, ["color"]))
                  }), 128))
                ]))
              : _createCommentVNode("", true)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (runtime.tasks.length)
      ? (_openBlock(), _createBlock(_component_v_card, {
          key: 0,
          variant: "outlined",
          rounded: "lg",
          class: "mb-4"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  icon: "mdi-cloud-sync-outline",
                  color: "primary",
                  class: "mr-2"
                }),
                _cache[13] || (_cache[13] = _createTextVNode(" CMS / 115 任务 ", -1)),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  icon: "",
                  variant: "text",
                  size: "small",
                  loading: statusLoading.value,
                  onClick: loadRuntimeStatus
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, { icon: "mdi-refresh" }),
                    _createVNode(_component_v_tooltip, {
                      activator: "parent",
                      location: "top"
                    }, {
                      default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
                        _createTextVNode("刷新任务状态", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_table, { density: "compact" }, {
              default: _withCtx(() => [
                _cache[15] || (_cache[15] = _createElementVNode("thead", null, [
                  _createElementVNode("tr", null, [
                    _createElementVNode("th", null, "资源"),
                    _createElementVNode("th", null, "状态"),
                    _createElementVNode("th", null, "提交时间"),
                    _createElementVNode("th", { class: "text-right" }, "操作")
                  ])
                ], -1)),
                _createElementVNode("tbody", null, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(runtime.tasks, (task) => {
                    return (_openBlock(), _createElementBlock("tr", {
                      key: `${task.btih}-${task.submitted_at}`
                    }, [
                      _createElementVNode("td", null, [
                        _createElementVNode("div", _hoisted_8, _toDisplayString(task.title), 1),
                        _createElementVNode("div", _hoisted_9, "BTIH " + _toDisplayString(String(task.btih || '').slice(0, 12)) + "...", 1),
                        (task.error)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_10, _toDisplayString(task.error), 1))
                          : _createCommentVNode("", true)
                      ]),
                      _createElementVNode("td", null, [
                        _createVNode(_component_v_chip, {
                          size: "x-small",
                          variant: "tonal",
                          color: taskStatusColor(task.status)
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(taskStatusLabel(task.status)), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"])
                      ]),
                      _createElementVNode("td", _hoisted_11, _toDisplayString(formatTime(task.submitted_at)), 1),
                      _createElementVNode("td", _hoisted_12, [
                        (['failed', 'timed_out'].includes(task.status))
                          ? (_openBlock(), _createBlock(_component_v_btn, {
                              key: 0,
                              icon: "",
                              variant: "text",
                              size: "small",
                              color: "primary",
                              loading: retryingBtih.value === task.btih,
                              onClick: $event => (retryTask(task))
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_icon, { icon: "mdi-replay" }),
                                _createVNode(_component_v_tooltip, {
                                  activator: "parent",
                                  location: "top"
                                }, {
                                  default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                                    _createTextVNode("重试任务", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }, 8, ["loading", "onClick"]))
                          : _createCommentVNode("", true)
                      ])
                    ]))
                  }), 128))
                ])
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createVNode(_component_v_card, {
      variant: "outlined",
      rounded: "lg"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, { class: "d-flex align-center px-4 py-3" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-magnify",
              color: "primary",
              class: "mr-2"
            }),
            _cache[18] || (_cache[18] = _createTextVNode(" 手动搜索网盘资源 ", -1)),
            (results.value.length)
              ? (_openBlock(), _createBlock(_component_v_chip, {
                  key: 0,
                  size: "x-small",
                  variant: "tonal",
                  color: "primary",
                  class: "ml-2"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(filteredResults.value.length) + "/" + _toDisplayString(results.value.length) + " 条 ", 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_spacer),
            (hasTransferable.value)
              ? (_openBlock(), _createBlock(_component_v_chip, {
                  key: 1,
                  size: "x-small",
                  variant: "tonal",
                  color: "success",
                  class: "mr-1"
                }, {
                  default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                    _createTextVNode("支持转存到 115", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            (results.value.length)
              ? (_openBlock(), _createBlock(_component_v_btn, {
                  key: 2,
                  size: "x-small",
                  variant: "text",
                  color: "error",
                  "prepend-icon": "mdi-close",
                  onClick: clearResults
                }, {
                  default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                    _createTextVNode("清除", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode("", true)
          ]),
          _: 1
        }),
        _createVNode(_component_v_divider),
        _createVNode(_component_v_card_text, { class: "px-4 py-4" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_text_field, {
              modelValue: keyword.value,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((keyword).value = $event)),
              label: "输入片名搜索（TG 频道 + 观影，115 分享/磁力可转存）",
              variant: "outlined",
              density: "comfortable",
              "hide-details": "",
              loading: searching.value,
              "append-inner-icon": "mdi-magnify",
              "onClick:appendInner": doSearch,
              onKeyup: _withKeys(doSearch, ["enter"])
            }, null, 8, ["modelValue", "loading"]),
            _createElementVNode("div", _hoisted_13, [
              _cache[23] || (_cache[23] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "来源", -1)),
              _createVNode(_component_v_btn_toggle, {
                modelValue: searchSource.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((searchSource).value = $event)),
                mandatory: "",
                color: "primary",
                density: "compact",
                divided: ""
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_btn, {
                    value: "all",
                    size: "small"
                  }, {
                    default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                      _createTextVNode("全部", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_v_btn, {
                    value: "tg",
                    size: "small"
                  }, {
                    default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                      _createTextVNode("TG", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_v_btn, {
                    value: "site",
                    size: "small"
                  }, {
                    default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                      _createTextVNode("观影", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_v_btn, {
                    value: "juying",
                    size: "small"
                  }, {
                    default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                      _createTextVNode("聚影", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue"])
            ]),
            _createElementVNode("div", _hoisted_14, [
              _cache[24] || (_cache[24] = _createElementVNode("span", { class: "filter-label" }, "资源", -1)),
              _createVNode(_component_v_btn_toggle, {
                modelValue: resourceFilter.value,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((resourceFilter).value = $event)),
                mandatory: "",
                color: "primary",
                density: "compact",
                divided: "",
                class: "filter-toggle"
              }, {
                default: _withCtx(() => [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(RESOURCE_FILTERS), (item) => {
                    return (_openBlock(), _createBlock(_component_v_btn, {
                      key: item.value,
                      value: item.value,
                      size: "small"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(item.title), 1)
                      ]),
                      _: 2
                    }, 1032, ["value"]))
                  }), 128))
                ]),
                _: 1
              }, 8, ["modelValue"])
            ]),
            _createElementVNode("div", _hoisted_15, [
              _cache[25] || (_cache[25] = _createElementVNode("span", { class: "filter-label" }, "画质", -1)),
              _createVNode(_component_v_btn_toggle, {
                modelValue: qualityFilter.value,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((qualityFilter).value = $event)),
                mandatory: "",
                color: "primary",
                density: "compact",
                divided: "",
                class: "filter-toggle"
              }, {
                default: _withCtx(() => [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(QUALITY_FILTERS), (item) => {
                    return (_openBlock(), _createBlock(_component_v_btn, {
                      key: item.value,
                      value: item.value,
                      size: "small"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(item.title), 1)
                      ]),
                      _: 2
                    }, 1032, ["value"]))
                  }), 128))
                ]),
                _: 1
              }, 8, ["modelValue"])
            ]),
            (searchMsg.value)
              ? (_openBlock(), _createElementBlock("div", {
                  key: 0,
                  class: _normalizeClass(["text-caption mt-2", searchOk.value ? 'text-success' : 'text-error'])
                }, _toDisplayString(searchMsg.value), 3))
              : _createCommentVNode("", true)
          ]),
          _: 1
        }),
        (results.value.length)
          ? (_openBlock(), _createBlock(_component_v_card_text, {
              key: 0,
              class: "px-4 pb-4 pt-0"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_row, { dense: "" }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(filteredResults.value, (r, i) => {
                      return (_openBlock(), _createBlock(_component_v_col, {
                        key: r.share_url || i,
                        cols: "12",
                        sm: "6",
                        md: "4",
                        lg: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, {
                            variant: "tonal",
                            rounded: "lg",
                            class: "result-card h-100 d-flex flex-column"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_item, { class: "pb-2" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("div", _hoisted_16, [
                                    _createVNode(_component_v_chip, {
                                      color: panColor(r.pan_type),
                                      size: "x-small",
                                      variant: "flat",
                                      class: "mr-2"
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(panLabel(r.pan_type)), 1)
                                      ]),
                                      _: 2
                                    }, 1032, ["color"]),
                                    (r.is_complete)
                                      ? (_openBlock(), _createBlock(_component_v_chip, {
                                          key: 0,
                                          size: "x-small",
                                          variant: "flat",
                                          color: "success",
                                          class: "mr-2"
                                        }, {
                                          default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                                            _createTextVNode("完结", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                      : _createCommentVNode("", true),
                                    (r.pub_date)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_17, _toDisplayString(r.pub_date.slice(0, 10)), 1))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", {
                                    class: "text-body-1 font-weight-bold line-clamp-2",
                                    title: r.display_name || r.title
                                  }, _toDisplayString(r.display_name || r.title), 9, _hoisted_18),
                                  (r.meta)
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_19, _toDisplayString(r.meta), 1))
                                    : _createCommentVNode("", true),
                                  (r.pan_type === '115' && r.receive_code)
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_20, "提取码：" + _toDisplayString(r.receive_code), 1))
                                    : _createCommentVNode("", true),
                                  (r.text)
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_21, _toDisplayString(r.text), 1))
                                    : _createCommentVNode("", true),
                                  _createElementVNode("div", _hoisted_22, _toDisplayString(r.channel || '未知来源'), 1)
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode(_component_v_spacer),
                              _createVNode(_component_v_card_actions, { class: "pt-2" }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_btn, {
                                    size: "small",
                                    variant: "text",
                                    "prepend-icon": "mdi-content-copy",
                                    onClick: $event => (copy(r))
                                  }, {
                                    default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                                      _createTextVNode("复制链接", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"]),
                                  _createVNode(_component_v_spacer),
                                  (r.pan_type === '115' || r.pan_type === 'magnet')
                                    ? (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 0,
                                        size: "small",
                                        variant: "flat",
                                        color: "primary",
                                        "prepend-icon": "mdi-cloud-download",
                                        loading: transferringIdx.value === i,
                                        onClick: $event => (transfer(r, i))
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(r.pan_type === 'magnet' ? '离线到115' : '转存'), 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["loading", "onClick"]))
                                    : _createCommentVNode("", true)
                                ]),
                                _: 2
                              }, 1024)
                            ]),
                            _: 2
                          }, 1024)
                        ]),
                        _: 2
                      }, 1024))
                    }), 128))
                  ]),
                  _: 1
                }),
                (!filteredResults.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_23, "当前筛选条件下没有资源"))
                  : _createCommentVNode("", true),
                (hasMore.value)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_24, [
                      _createVNode(_component_v_btn, {
                        variant: "outlined",
                        loading: loadingMore.value,
                        "prepend-icon": "mdi-chevron-down",
                        onClick: loadMore
                      }, {
                        default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                          _createTextVNode(" 查看更多历史 ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading"])
                    ]))
                  : (_openBlock(), _createElementBlock("div", _hoisted_25, "已全部加载"))
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      _: 1
    }),
    _createVNode(_component_v_snackbar, {
      modelValue: snack.value,
      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((snack).value = $event)),
      color: snackColor.value,
      timeout: 2500,
      location: "top"
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-6a9d4b29"]]);

export { Page as default };
