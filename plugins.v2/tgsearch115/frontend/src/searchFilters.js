export const RESOURCE_FILTERS = [
  { title: '全部', value: 'all' },
  { title: '磁力', value: 'magnet' },
  { title: '网盘', value: 'pan' },
  { title: '115', value: '115' },
]

export const QUALITY_FILTERS = [
  { title: '全部画质', value: 'all' },
  { title: '4K', value: '4k' },
  { title: '1080P', value: '1080p' },
  { title: '高帧率', value: 'hfr' },
  { title: '排除 HDR', value: 'no_hdr' },
]

export const MAGNET_FILTERS = [
  { title: '全部', value: 'all' },
  { title: '720P', value: '720p' },
  { title: '1080P', value: '1080p' },
  { title: '中字1080P', value: 'chs1080p' },
  { title: '4K', value: '4k' },
  { title: '中字4K', value: 'chs4k' },
  { title: '原盘', value: 'remux' },
  { title: '未知', value: 'unknown' },
]

export const PAN_FILTERS = [
  { title: '全部', value: 'all' },
  { title: '迅雷网盘', value: 'xunlei' },
  { title: '百度网盘', value: 'baidu' },
  { title: '夸克网盘', value: 'quark' },
  { title: '天翼网盘', value: 'cloud189' },
  { title: '115网盘', value: '115' },
  { title: 'UC网盘', value: 'uc' },
  { title: '阿里网盘', value: 'aliyun' },
]

function resultText(result) {
  return [result?.display_name, result?.title, result?.meta, result?.text]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

export function filterSearchResults(results, resourceFilter, qualityFilter) {
  return (Array.isArray(results) ? results : []).filter((result) => {
    const panType = String(result?.pan_type || 'other').toLowerCase()
    if (resourceFilter === 'magnet' && panType !== 'magnet') return false
    if (resourceFilter === 'pan' && panType === 'magnet') return false
    if (resourceFilter === '115' && panType !== '115') return false

    if (resourceFilter === 'pan' && qualityFilter !== 'all' && panType !== qualityFilter) return false

    const text = resultText(result)
    const chinese = /(?:中文字幕|国语中字|中字|简中|繁中|简繁|内封.{0,6}(?:简|繁|中)|(?:chs|cht|chinese).{0,8}(?:sub|subtitle))/i.test(text)
    const is720 = /720[pi]?/i.test(text)
    const is1080 = /1080[pi]?/i.test(text)
    const is4k = /(?:\b4k\b|2160p|\buhd\b)/i.test(text)
    const isRemux = /(?:remux|原盘|blu-?ray|bdmv)/i.test(text)
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
