import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withKeys:_withKeys,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "tg115-page" };
const _hoisted_2 = { class: "text-h6" };
const _hoisted_3 = { class: "text-h6" };
const _hoisted_4 = { class: "d-flex align-center mb-2" };
const _hoisted_5 = {
  key: 1,
  class: "text-caption text-medium-emphasis ml-auto"
};
const _hoisted_6 = ["title"];
const _hoisted_7 = {
  key: 0,
  class: "text-caption text-primary font-weight-medium mt-1"
};
const _hoisted_8 = { class: "text-caption text-medium-emphasis mt-1" };
const _hoisted_9 = {
  key: 0,
  class: "d-flex justify-center mt-4"
};
const _hoisted_10 = {
  key: 1,
  class: "text-center text-caption text-medium-emphasis mt-3"
};

const {computed,onMounted,reactive,ref} = await importShared('vue');


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
const config = reactive({ enabled: false, p115_cookie: '', delay_seconds: 0, tg_channels: [] });
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
const results = ref(_init ? _init.results : []);
const offset = ref(_init ? _init.offset || 0 : 0);
const hasMore = ref(_init ? !!_init.has_more : false);
const searching = ref(false);
const loadingMore = ref(false);
const searchMsg = ref(_init ? `已恢复上次搜索「${_init.keyword}」的结果（${_init.results.length} 条）` : '');
const searchOk = ref(!!_init);
const transferringIdx = ref(-1);
const has115 = computed(() => results.value.some((r) => r.pan_type === '115'));

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

const PAN_LABEL = { '115': '115', quark: '夸克', baidu: '百度', aliyun: '阿里', xunlei: '迅雷', cloud189: '天翼', uc: 'UC', other: '其他' };
const PAN_COLOR = { '115': 'success', quark: 'info', baidu: 'error', aliyun: 'cyan', xunlei: 'purple', cloud189: 'indigo', uc: 'orange', other: 'grey' };
function panLabel(t) { return PAN_LABEL[t] || t || '其他' }
function panColor(t) { return PAN_COLOR[t] || 'grey' }

async function doSearch() {
  const kw = (keyword.value || '').trim();
  if (!kw) { showSnack('请输入搜索关键字', 'warning'); return }
  if (!props.api?.get) { showSnack('API 未就绪', 'error'); return }
  searching.value = true;
  searchMsg.value = '';
  try {
    const res = await props.api.get(`plugin/${PID.value}/search?keyword=${encodeURIComponent(kw)}`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    if (data && data.success) {
      results.value = Array.isArray(data.results) ? data.results : [];
      searchMsg.value = data.message || `找到 ${results.value.length} 条`;
      searchOk.value = true;
      offset.value = 0;
      hasMore.value = !!data.has_more;
      saveCache({ keyword: kw, results: results.value, offset: 0, has_more: hasMore.value });
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
    const res = await props.api.get(`plugin/${PID.value}/search?keyword=${encodeURIComponent(keyword.value)}&offset=${next}`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    if (data && data.success) {
      const more = Array.isArray(data.results) ? data.results : [];
      results.value = [...results.value, ...more];
      offset.value = next;
      hasMore.value = !!data.has_more;
      // 全局重排：完结优先，集数降序
      results.value.sort((a, b) => (b.is_complete - a.is_complete) || (b.episode_num - a.episode_num));
      saveCache({ keyword: keyword.value, results: results.value, offset: offset.value, has_more: hasMore.value });
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
  if (!loginOk.value) { showSnack('未登录 115，无法转存', 'error'); return }
  transferringIdx.value = i;
  try {
    const url = encodeURIComponent(fullShareUrl(r));
    const res = await props.api.get(`plugin/${PID.value}/transfer?share_url=${url}`);
    const data = res && typeof res === 'object' && 'data' in res && ('success' in res || 'code' in res) ? res.data : res;
    showSnack(data?.message || (data?.success ? '转存成功' : '转存失败'), data?.success ? 'success' : 'error');
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
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_text_field = _resolveComponent("v-text-field");
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
            _cache[2] || (_cache[2] = _createTextVNode(" 拦截mp订阅 ", -1)),
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
                    _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "TG 频道数", -1)),
                    _createElementVNode("div", _hoisted_2, _toDisplayString(channelCount.value), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "115 登录", -1)),
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
                    _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "触发延迟", -1)),
                    _createElementVNode("div", _hoisted_3, _toDisplayString(config.delay_seconds || 0) + " 秒", 1)
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
            _cache[8] || (_cache[8] = _createTextVNode(" 手动搜索网盘资源 ", -1)),
            (results.value.length)
              ? (_openBlock(), _createBlock(_component_v_chip, {
                  key: 0,
                  size: "x-small",
                  variant: "tonal",
                  color: "primary",
                  class: "ml-2"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(results.value.length) + " 条 ", 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_spacer),
            (has115.value)
              ? (_openBlock(), _createBlock(_component_v_chip, {
                  key: 1,
                  size: "x-small",
                  variant: "tonal",
                  color: "success",
                  class: "mr-1"
                }, {
                  default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
                    _createTextVNode("含 115 可转存", -1)
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
                  default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
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
              label: "输入片名搜索（TG 频道 + 资源站，仅 115 可转存）",
              variant: "outlined",
              density: "comfortable",
              "hide-details": "",
              loading: searching.value,
              "append-inner-icon": "mdi-magnify",
              "onClick:appendInner": doSearch,
              onKeyup: _withKeys(doSearch, ["enter"])
            }, null, 8, ["modelValue", "loading"]),
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
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(results.value, (r, i) => {
                      return (_openBlock(), _createBlock(_component_v_col, {
                        key: i,
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
                                  _createElementVNode("div", _hoisted_4, [
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
                                          default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                                            _createTextVNode("完结", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                      : _createCommentVNode("", true),
                                    (r.pub_date)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_5, _toDisplayString(r.pub_date.slice(0, 10)), 1))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", {
                                    class: "text-body-1 font-weight-bold line-clamp-2",
                                    title: r.display_name || r.title
                                  }, _toDisplayString(r.display_name || r.title), 9, _hoisted_6),
                                  (r.meta)
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_7, _toDisplayString(r.meta), 1))
                                    : _createCommentVNode("", true),
                                  _createElementVNode("div", _hoisted_8, _toDisplayString(r.channel || '未知来源'), 1)
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
                                    default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
                                      _createTextVNode("复制链接", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"]),
                                  _createVNode(_component_v_spacer),
                                  (r.pan_type === '115')
                                    ? (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 0,
                                        size: "small",
                                        variant: "flat",
                                        color: "primary",
                                        "prepend-icon": "mdi-cloud-download",
                                        loading: transferringIdx.value === i,
                                        onClick: $event => (transfer(r, i))
                                      }, {
                                        default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                                          _createTextVNode("转存", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["loading", "onClick"]))
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
                (hasMore.value)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_9, [
                      _createVNode(_component_v_btn, {
                        variant: "outlined",
                        loading: loadingMore.value,
                        "prepend-icon": "mdi-chevron-down",
                        onClick: loadMore
                      }, {
                        default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
                          _createTextVNode(" 查看更多历史 ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading"])
                    ]))
                  : (_openBlock(), _createElementBlock("div", _hoisted_10, "已全部加载"))
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      _: 1
    }),
    _createVNode(_component_v_snackbar, {
      modelValue: snack.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((snack).value = $event)),
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-34139453"]]);

export { Page as default };
