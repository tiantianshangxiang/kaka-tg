import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const MAGNET_FILTERS = [
  { title: '全部', value: 'all' },
  { title: '720P', value: '720p' },
  { title: '1080P', value: '1080p' },
  { title: '中字1080P', value: 'chs1080p' },
  { title: '4K', value: '4k' },
  { title: '中字4K', value: 'chs4k' },
  { title: '原盘', value: 'remux' },
  { title: '未知', value: 'unknown' },
];

const PAN_FILTERS = [
  { title: '全部', value: 'all' },
  { title: '迅雷网盘', value: 'xunlei' },
  { title: '百度网盘', value: 'baidu' },
  { title: '夸克网盘', value: 'quark' },
  { title: '天翼网盘', value: 'cloud189' },
  { title: '115网盘', value: '115' },
  { title: 'UC网盘', value: 'uc' },
  { title: '阿里网盘', value: 'aliyun' },
];

function resultText(result) {
  return [result?.display_name, result?.title, result?.meta, result?.text]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function filterSearchResults(results, resourceFilter, qualityFilter) {
  return (Array.isArray(results) ? results : []).filter((result) => {
    const panType = String(result?.pan_type || 'other').toLowerCase();
    if (resourceFilter === 'magnet' && panType !== 'magnet') return false
    if (resourceFilter === 'pan' && panType === 'magnet') return false
    if (resourceFilter === '115' && panType !== '115') return false

    if (resourceFilter === 'pan' && qualityFilter !== 'all' && panType !== qualityFilter) return false

    const text = resultText(result);
    const chinese = /(?:中文字幕|国语中字|中字|简中|繁中|简繁|内封.{0,6}(?:简|繁|中)|(?:chs|cht|chinese).{0,8}(?:sub|subtitle))/i.test(text);
    const is720 = /720[pi]?/i.test(text);
    const is1080 = /1080[pi]?/i.test(text);
    const is4k = /(?:\b4k\b|2160p|\buhd\b)/i.test(text);
    const isRemux = /(?:remux|原盘|blu-?ray|bdmv)/i.test(text);
    if (resourceFilter === 'magnet' && qualityFilter === '720p' && !is720) return false
    if (resourceFilter === 'magnet' && qualityFilter === '1080p' && !is1080) return false
    if (resourceFilter === 'magnet' && qualityFilter === 'chs1080p' && !(is1080 && chinese)) return false
    if (resourceFilter === 'magnet' && qualityFilter === '4k' && !is4k) return false
    if (resourceFilter === 'magnet' && qualityFilter === 'chs4k' && !(is4k && chinese)) return false
    if (resourceFilter === 'magnet' && qualityFilter === 'remux' && !isRemux) return false
    if (resourceFilter === 'magnet' && qualityFilter === 'unknown' && (is720 || is1080 || is4k || isRemux)) return false
    if (qualityFilter === '4k' && !/(?:\b4k\b|2160p|\buhd\b)/i.test(text)) return false
    if (qualityFilter === '1080p' && !/1080[pi]?/i.test(text)) return false
    if (qualityFilter === 'hfr' && !/(?:\b(?:50|60|90|120)\s*fps\b|(?:50|60|90|120)\s*帧(?:率)?|\bhfr\b|高帧率)/i.test(text)) return false
    if (qualityFilter === 'no_hdr' && /(?:\bhdr(?:10\+?)?\b|dolby\s*vision|\bdv\b|dovi|杜比视界)/i.test(text)) return false
    return true
  })
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,withKeys:_withKeys,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,unref:_unref,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass} = await importShared('vue');


const _hoisted_1 = { class: "manual-search" };
const _hoisted_2 = { class: "d-flex align-center ga-2 mb-3 flex-wrap" };
const _hoisted_3 = { class: "d-flex ga-2 mb-3 search-row" };
const _hoisted_4 = { class: "filter-row mb-2" };
const _hoisted_5 = {
  key: 0,
  class: "filter-row mb-3"
};
const _hoisted_6 = {
  key: 1,
  class: "filter-row mb-3"
};
const _hoisted_7 = {
  key: 3,
  class: "empty-state"
};
const _hoisted_8 = { class: "d-flex align-center ga-1 mb-2" };
const _hoisted_9 = { class: "text-body-2 font-weight-medium" };
const _hoisted_10 = {
  key: 0,
  class: "text-caption text-primary mt-1"
};
const _hoisted_11 = { class: "text-caption text-medium-emphasis line-clamp-3 mt-1" };
const _hoisted_12 = { class: "text-caption text-medium-emphasis mt-1" };
const _hoisted_13 = {
  key: 5,
  class: "empty-state"
};

const {computed,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'ManualSearch',
  props: { pluginId: { type: String, default: 'TgSearch115' }, api: { type: Object, default: null } },
  setup(__props) {

const props = __props;
const base = computed(() => `plugin/${props.pluginId || 'TgSearch115'}`);
const keyword = ref('');
const source = ref('all');
const resourceType = ref('all');
const detailFilter = ref('all');
const results = ref([]);
const searching = ref(false);
const searched = ref(false);
const transferring = ref('');
const message = ref('');
const ok = ref(false);
const snack = ref(false);
const snackColor = ref('');
const snackText = ref('');
const filtered = computed(() => filterSearchResults(results.value, resourceType.value, detailFilter.value));

watch(resourceType, () => { detailFilter.value = 'all'; });

function unwrap(res) {
  if (res && typeof res === 'object' && res.data && typeof res.data === 'object') return res.data
  return res
}
function notify(text, color = 'success') { snackText.value = text; snackColor.value = color; snack.value = true; }
function fullUrl(r) {
  let url = String(r?.share_url || '');
  if (r?.pan_type === '115' && r?.receive_code && !/[?&](password|receive_code|pwd)=/.test(url)) {
    url += (url.includes('?') ? '&' : '?') + 'password=' + r.receive_code;
  }
  return url
}
async function search() {
  const value = keyword.value.trim();
  if (!value) return notify('请输入搜索关键字', 'warning')
  if (!props.api?.get) return notify('API 未就绪', 'error')
  searching.value = true; searched.value = true; message.value = '';
  try {
    const data = unwrap(await props.api.get(`${base.value}/search?keyword=${encodeURIComponent(value)}&source=${source.value}`));
    results.value = Array.isArray(data?.results) ? data.results : [];
    ok.value = !!data?.success;
    message.value = data?.warning || data?.message || (ok.value ? `找到 ${results.value.length} 条` : '搜索失败');
  } catch (e) {
    results.value = []; ok.value = false; message.value = e?.response?.data?.message || e?.message || '搜索失败';
  } finally { searching.value = false; }
}
async function copy(r) {
  try { await navigator.clipboard.writeText(fullUrl(r)); notify('已复制链接'); }
  catch { notify('复制失败，请手动复制', 'error'); }
}
async function transfer(r) {
  if (!props.api) return notify('API 未就绪', 'error')
  transferring.value = r.share_url;
  try {
    const response = r.pan_type === 'magnet'
      ? await props.api.post(`${base.value}/magnet/offline`, { magnet: fullUrl(r), title: r.display_name || r.title || '' })
      : await props.api.get(`${base.value}/transfer?share_url=${encodeURIComponent(fullUrl(r))}`);
    const data = unwrap(response);
    if (!data || typeof data !== 'object') throw new Error('服务返回非 JSON，请检查插件日志')
    const success = data.success === true || data.code === 0;
    notify(data.message || (success ? '任务提交成功' : '提交失败'), success ? 'success' : 'error');
  } catch (e) {
    notify(e?.response?.data?.message || e?.message || '离线请求失败', 'error');
  } finally { transferring.value = ''; }
}
function panLabel(t) { return ({ '115':'115网盘', quark:'夸克网盘', baidu:'百度网盘', aliyun:'阿里网盘', xunlei:'迅雷网盘', cloud189:'天翼网盘', uc:'UC网盘', magnet:'磁力' })[t] || '其他' }
function panColor(t) { return ({ '115':'success', quark:'info', baidu:'error', aliyun:'warning', xunlei:'secondary', cloud189:'primary', uc:'orange', magnet:'deep-purple' })[t] || 'grey' }

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[10] || (_cache[10] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "来源", -1)),
      _createVNode(_component_v_btn_toggle, {
        modelValue: source.value,
        "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((source).value = $event)),
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
            default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
              _createTextVNode("全部", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            value: "tg",
            size: "small"
          }, {
            default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
              _createTextVNode("TG", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            value: "site",
            size: "small"
          }, {
            default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
              _createTextVNode("观影", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            value: "juying",
            size: "small"
          }, {
            default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
              _createTextVNode("聚影", -1)
            ]))]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"])
    ]),
    _createElementVNode("div", _hoisted_3, [
      _createVNode(_component_v_text_field, {
        modelValue: keyword.value,
        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((keyword).value = $event)),
        label: "搜索关键字（影片名 + 年份）",
        variant: "outlined",
        density: "comfortable",
        "hide-details": "",
        loading: searching.value,
        onKeyup: _withKeys(search, ["enter"])
      }, null, 8, ["modelValue", "loading"]),
      _createVNode(_component_v_btn, {
        color: "primary",
        variant: "flat",
        loading: searching.value,
        "prepend-icon": "mdi-magnify",
        onClick: search
      }, {
        default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
          _createTextVNode("搜索", -1)
        ]))]),
        _: 1
      }, 8, ["loading"])
    ]),
    _createElementVNode("div", _hoisted_4, [
      _cache[15] || (_cache[15] = _createElementVNode("span", { class: "filter-label" }, "资源", -1)),
      _createVNode(_component_v_btn_toggle, {
        modelValue: resourceType.value,
        "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((resourceType).value = $event)),
        mandatory: "",
        color: "primary",
        density: "compact",
        divided: "",
        class: "filter-toggle"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_btn, {
            value: "all",
            size: "small"
          }, {
            default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
              _createTextVNode("全部", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            value: "magnet",
            size: "small"
          }, {
            default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
              _createTextVNode("磁力", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            value: "pan",
            size: "small"
          }, {
            default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
              _createTextVNode("网盘", -1)
            ]))]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"]),
      (results.value.length)
        ? (_openBlock(), _createBlock(_component_v_chip, {
            key: 0,
            size: "x-small",
            variant: "tonal",
            color: "primary"
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(filtered.value.length) + "/" + _toDisplayString(results.value.length) + " 条", 1)
            ]),
            _: 1
          }))
        : _createCommentVNode("", true)
    ]),
    (resourceType.value === 'magnet')
      ? (_openBlock(), _createElementBlock("div", _hoisted_5, [
          _cache[16] || (_cache[16] = _createElementVNode("span", { class: "filter-label" }, "画质", -1)),
          _createVNode(_component_v_btn_toggle, {
            modelValue: detailFilter.value,
            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((detailFilter).value = $event)),
            mandatory: "",
            color: "primary",
            density: "compact",
            divided: "",
            class: "filter-toggle"
          }, {
            default: _withCtx(() => [
              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(MAGNET_FILTERS), (item) => {
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
        ]))
      : (resourceType.value === 'pan')
        ? (_openBlock(), _createElementBlock("div", _hoisted_6, [
            _cache[17] || (_cache[17] = _createElementVNode("span", { class: "filter-label" }, "网盘", -1)),
            _createVNode(_component_v_btn_toggle, {
              modelValue: detailFilter.value,
              "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((detailFilter).value = $event)),
              mandatory: "",
              color: "primary",
              density: "compact",
              divided: "",
              class: "filter-toggle"
            }, {
              default: _withCtx(() => [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(PAN_FILTERS), (item) => {
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
          ]))
        : _createCommentVNode("", true),
    (message.value)
      ? (_openBlock(), _createElementBlock("div", {
          key: 2,
          class: _normalizeClass(["text-caption mb-3", ok.value ? 'text-success' : 'text-error'])
        }, _toDisplayString(message.value), 3))
      : _createCommentVNode("", true),
    (searching.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_7, [
          _createVNode(_component_v_progress_circular, {
            indeterminate: "",
            size: "40",
            color: "primary"
          })
        ]))
      : (filtered.value.length)
        ? (_openBlock(), _createBlock(_component_v_row, {
            key: 4,
            dense: ""
          }, {
            default: _withCtx(() => [
              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(filtered.value, (r, i) => {
                return (_openBlock(), _createBlock(_component_v_col, {
                  key: r.share_url || i,
                  cols: "12",
                  sm: "6",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card, {
                      variant: "outlined",
                      class: "result-card h-100 d-flex flex-column"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_card_item, null, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_8, [
                              _createVNode(_component_v_chip, {
                                color: panColor(r.pan_type),
                                size: "x-small",
                                variant: "tonal"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(panLabel(r.pan_type)), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"]),
                              (r.is_complete)
                                ? (_openBlock(), _createBlock(_component_v_chip, {
                                    key: 0,
                                    color: "success",
                                    size: "x-small",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                                      _createTextVNode("完结", -1)
                                    ]))]),
                                    _: 1
                                  }))
                                : _createCommentVNode("", true)
                            ]),
                            _createElementVNode("div", _hoisted_9, _toDisplayString(r.display_name || r.title), 1),
                            (r.meta)
                              ? (_openBlock(), _createElementBlock("div", _hoisted_10, _toDisplayString(r.meta), 1))
                              : _createCommentVNode("", true),
                            _createElementVNode("div", _hoisted_11, _toDisplayString(r.text || r.title), 1),
                            _createElementVNode("div", _hoisted_12, _toDisplayString(r.channel || '未知来源'), 1)
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode(_component_v_spacer),
                        _createVNode(_component_v_card_actions, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_btn, {
                              size: "small",
                              variant: "text",
                              "prepend-icon": "mdi-content-copy",
                              onClick: $event => (copy(r))
                            }, {
                              default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                                _createTextVNode("复制链接", -1)
                              ]))]),
                              _: 1
                            }, 8, ["onClick"]),
                            _createVNode(_component_v_spacer),
                            (['115','magnet'].includes(r.pan_type))
                              ? (_openBlock(), _createBlock(_component_v_btn, {
                                  key: 0,
                                  size: "small",
                                  variant: "flat",
                                  color: "primary",
                                  "prepend-icon": "mdi-cloud-download",
                                  loading: transferring.value === r.share_url,
                                  onClick: $event => (transfer(r))
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
          }))
        : (searched.value && !searching.value)
          ? (_openBlock(), _createElementBlock("div", _hoisted_13, "当前筛选条件下没有资源"))
          : _createCommentVNode("", true),
    _createVNode(_component_v_snackbar, {
      modelValue: snack.value,
      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((snack).value = $event)),
      color: snackColor.value,
      timeout: 3000,
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
const ManualSearch = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-60d35c2f"]]);

export { ManualSearch as M, _export_sfc as _, filterSearchResults as f };
