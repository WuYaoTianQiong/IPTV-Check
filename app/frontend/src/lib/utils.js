import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

const COUNTRY_ZH = {
  CN:'中国',HK:'中国香港',MO:'中国澳门',TW:'中国台湾',
  US:'美国',GB:'英国',JP:'日本',KR:'韩国',FR:'法国',DE:'德国',
  RU:'俄罗斯',IT:'意大利',ES:'西班牙',NL:'荷兰',SE:'瑞典',
  CH:'瑞士',AT:'奥地利',BE:'比利时',PL:'波兰',PT:'葡萄牙',
  IE:'爱尔兰',DK:'丹麦',NO:'挪威',FI:'芬兰',CZ:'捷克',
  HU:'匈牙利',RO:'罗马尼亚',BG:'保加利亚',HR:'克罗地亚',SK:'斯洛伐克',
  SI:'斯洛文尼亚',RS:'塞尔维亚',UA:'乌克兰',GR:'希腊',TR:'土耳其',
  IL:'以色列',AE:'阿联酋',SA:'沙特',QA:'卡塔尔',IR:'伊朗',
  IN:'印度',PK:'巴基斯坦',BD:'孟加拉',TH:'泰国',VN:'越南',
  MY:'马来西亚',SG:'新加坡',ID:'印度尼西亚',PH:'菲律宾',MM:'缅甸',
  AU:'澳大利亚',NZ:'新西兰',CA:'加拿大',MX:'墨西哥',BR:'巴西',
  AR:'阿根廷',CL:'智利',CO:'哥伦比亚',PE:'秘鲁',CU:'古巴',
  ZA:'南非',EG:'埃及',NG:'尼日利亚',KE:'肯尼亚',
}

export function countryCodeToName(code) {
  if (!code) return ''
  return COUNTRY_ZH[code.toUpperCase()] || code
}

// 中国省级行政区 / 直辖市 / 自治区 / 特别行政区名（与后端 _CN_REGION_KEYWORDS 的 region 粒度一致）
const CN_REGION_NAMES = new Set([
  '北京', '上海', '天津', '重庆',
  '河北', '山西', '辽宁', '吉林', '黑龙江', '江苏', '浙江', '安徽', '福建', '江西', '山东',
  '河南', '湖北', '湖南', '广东', '广西', '海南', '四川', '贵州', '云南', '西藏', '陕西', '甘肃',
  '青海', '宁夏', '新疆', '内蒙古', '香港', '澳门', '台湾',
])

function geoCountry(item) {
  return ((item && item.country) || '').toUpperCase()
}

function isCnCode(code) {
  return ['CN', 'CHN', 'HK', 'MO', 'TW'].includes(code)
}

/**
 * 频道归属地文本（展示用）：
 * - 国内频道 → "中国"+省份/港澳台（如 中国浙江 / 中国香港）；无法细分省时退化为 "中国"
 * - 国外频道 → 国家中文名（如 美国 / 日本）
 * - 无法识别 → ''
 */
export function geoLabel(item) {
  if (!item) return ''
  const country = geoCountry(item)
  const region = (item.region || '').trim()
  if (region === '香港' || region === '澳门' || region === '台湾') return '中国' + region
  if (region === '中国' || region.startsWith('中国')) return region
  if (region && CN_REGION_NAMES.has(region)) return '中国' + region
  if (isCnCode(country)) return region || '中国'
  if (country) return countryCodeToName(country)
  return region || ''
}

/** 是否为国外频道（决定归属地徽章底色；国内绿 / 国外靛蓝） */
export function geoIsForeign(item) {
  if (!item) return false
  const country = geoCountry(item)
  const region = (item.region || '').trim()
  if (isCnCode(country)) return false
  if (region && (region.startsWith('中国') || CN_REGION_NAMES.has(region))) return false
  if (country) return true
  return !!region
}
