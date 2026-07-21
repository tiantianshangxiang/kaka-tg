import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, f as filterSearchResults, M as ManualSearch } from './ManualSearch-CwqCAbd1.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withModifiers:_withModifiers,vShow:_vShow,withDirectives:_withDirectives,withKeys:_withKeys,unref:_unref} = await importShared('vue');


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
const _hoisted_10 = { class: "text-caption text-medium-emphasis" };
const _hoisted_11 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_12 = { key: 0 };
const _hoisted_13 = {
  key: 1,
  class: "text-caption text-error"
};
const _hoisted_14 = { class: "text-caption" };
const _hoisted_15 = { class: "text-right" };

const {computed,onMounted,onUnmounted,reactive,ref} = await importShared('vue');

const CACHE_KEY = 'tg115_search_cache';

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
const config = reactive({ enabled: false, p115_cookie: '', cms_url: '', cms_token: '', offline_allow_cancel: false, delay_seconds: 0, tg_channels: [] });
const runtime = reactive({
  scheduler: { running: false, last_run: '', next_run: '', scanned_count: 0, queue_size: 0 },
  sources: {},
  tasks: [],
});
const statusLoading = ref(false);
const tasksExpanded = ref(false);
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
const _init = loadCache();
ref(_init ? _init.keyword : '');
ref('all');
const resourceFilter = ref(_init?.resource_filter || 'all');
const qualityFilter = ref(_init?.quality_filter || 'all');
const results = ref(_init ? _init.results : []);
ref(_init ? _init.offset || 0 : 0);
ref(_init ? !!_init.has_more : false);
ref(false);
ref(false);
ref(_init ? `已恢复上次搜索「${_init.keyword}」的结果（${_init.results.length} 条）` : '');
ref(!!_init);
ref(-1);
computed(() => results.value.some(
  (r) => r.pan_type === '115' || r.pan_type === 'magnet',
));
computed(() => filterSearchResults(
  results.value,
  resourceFilter.value,
  qualityFilter.value,
));
// snackbar
const snack = ref(false);
const snackColor = ref('');
const snackText = ref('');
function formatTime(value) {
  if (!value) return '尚未运行'
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
function taskStatusLabel(status) {
  return {
    waiting: '等待中', submitted: '已提交', downloading: '下载中', pending_organize: '待整理',
    completed: '已完成', failed: '失败', timed_out: '超时', cancelled: '已取消',
  }[status] || status || '未知'
}
function taskStatusColor(status) {
  return {
    waiting: 'info', submitted: 'info', downloading: 'primary', pending_organize: 'warning',
    completed: 'success', failed: 'error', timed_out: 'warning', cancelled: 'grey',
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
    showSnack(data?.message || (data?.success ? '订阅已恢复' : '重试失败'), data?.success ? 'success' : 'error');
    await loadRuntimeStatus();
  } catch (e) {
    showSnack('重试异常：' + (e?.message || e), 'error');
  } finally {
    retryingBtih.value = '';
  }
}
async function cancelTask(task) {
  if (!props.api?.post || !task?.btih) return
  try {
    const res = await props.api.post(`plugin/${PID.value}/tasks/cancel`, { btih: task.btih });
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    showSnack(data?.message || '取消失败', data?.success ? 'success' : 'error');
    await loadRuntimeStatus();
  } catch (e) {
    showSnack('取消异常：' + (e?.message || e), 'error');
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
  const _component_v_expand_transition = _resolveComponent("v-expand-transition");
  _resolveComponent("v-text-field");
  _resolveComponent("v-btn-toggle");
  _resolveComponent("v-card-item");
  _resolveComponent("v-card-actions");
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
            _cache[6] || (_cache[6] = _createTextVNode(" 拦截mp订阅 ", -1)),
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
                    _cache[7] || (_cache[7] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "TG 频道数", -1)),
                    _createElementVNode("div", _hoisted_2, _toDisplayString(channelCount.value), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "115 登录", -1)),
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
                    _cache[9] || (_cache[9] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "触发延迟", -1)),
                    _createElementVNode("div", _hoisted_3, _toDisplayString(config.delay_seconds || 0) + " 秒", 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[10] || (_cache[10] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "上次周期扫描", -1)),
                    _createElementVNode("div", _hoisted_4, _toDisplayString(formatTime(runtime.scheduler.last_run)), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[11] || (_cache[11] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "下次周期扫描", -1)),
                    _createElementVNode("div", _hoisted_5, _toDisplayString(formatTime(runtime.scheduler.next_run)), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[12] || (_cache[12] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "队列 / 本轮订阅", -1)),
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
            _createVNode(_component_v_card_title, {
              class: "d-flex align-center px-4 py-3 task-toggle",
              onClick: _cache[0] || (_cache[0] = $event => (tasksExpanded.value = !tasksExpanded.value))
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  icon: "mdi-cloud-sync-outline",
                  color: "primary",
                  class: "mr-2"
                }),
                _cache[14] || (_cache[14] = _createTextVNode(" CMS / 115 任务 ", -1)),
                _createVNode(_component_v_chip, {
                  size: "x-small",
                  variant: "tonal",
                  class: "ml-2"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(runtime.tasks.length), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  icon: "",
                  variant: "text",
                  size: "small",
                  loading: statusLoading.value,
                  onClick: _withModifiers(loadRuntimeStatus, ["stop"])
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, { icon: "mdi-refresh" }),
                    _createVNode(_component_v_tooltip, {
                      activator: "parent",
                      location: "top"
                    }, {
                      default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                        _createTextVNode("刷新任务状态", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode(_component_v_icon, {
                  icon: tasksExpanded.value ? 'mdi-chevron-up' : 'mdi-chevron-down'
                }, null, 8, ["icon"])
              ]),
              _: 1
            }),
            _createVNode(_component_v_expand_transition, null, {
              default: _withCtx(() => [
                _withDirectives(_createElementVNode("div", null, [
                  _createVNode(_component_v_divider),
                  _createVNode(_component_v_table, { density: "compact" }, {
                    default: _withCtx(() => [
                      _cache[17] || (_cache[17] = _createElementVNode("thead", null, [
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
                              _createElementVNode("div", _hoisted_9, _toDisplayString(task.source === '115_direct' ? '115 直接磁力' : 'CMS 回退') + " · task " + _toDisplayString(String(task.task_id || '').slice(0, 12)) + "...", 1),
                              _createElementVNode("div", _hoisted_10, "BTIH " + _toDisplayString(String(task.btih || '').slice(0, 12)) + "...", 1),
                              (task.target_cid)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
                                    _createTextVNode(" 115 目标 cid " + _toDisplayString(task.target_cid), 1),
                                    (task.download_name)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_12, " · " + _toDisplayString(task.download_name), 1))
                                      : _createCommentVNode("", true)
                                  ]))
                                : _createCommentVNode("", true),
                              (task.error_message)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_13, _toDisplayString(task.error_message), 1))
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
                            _createElementVNode("td", _hoisted_14, _toDisplayString(formatTime(task.submitted_at)), 1),
                            _createElementVNode("td", _hoisted_15, [
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
                                        default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                                          _createTextVNode("重试任务", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  }, 8, ["loading", "onClick"]))
                                : _createCommentVNode("", true),
                              (config.offline_allow_cancel && task.source === '115_direct' && ['submitted', 'downloading', 'pending_organize'].includes(task.status))
                                ? (_openBlock(), _createBlock(_component_v_btn, {
                                    key: 1,
                                    icon: "",
                                    variant: "text",
                                    size: "small",
                                    color: "error",
                                    onClick: $event => (cancelTask(task))
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_icon, { icon: "mdi-cancel" }),
                                      _createVNode(_component_v_tooltip, {
                                        activator: "parent",
                                        location: "top"
                                      }, {
                                        default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                                          _createTextVNode("取消任务并恢复订阅", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  }, 8, ["onClick"]))
                                : _createCommentVNode("", true)
                            ])
                          ]))
                        }), 128))
                      ])
                    ]),
                    _: 1
                  })
                ], 512), [
                  [_vShow, tasksExpanded.value]
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
            _cache[18] || (_cache[18] = _createTextVNode("手动搜索（TG 频道 + 观影） ", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_v_divider),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createVNode(ManualSearch, {
              "plugin-id": PID.value,
              api: props.api
            }, null, 8, ["plugin-id", "api"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createCommentVNode("", true),
    _createVNode(_component_v_snackbar, {
      modelValue: snack.value,
      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((snack).value = $event)),
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-689525e0"]]);

export { Page as default };
