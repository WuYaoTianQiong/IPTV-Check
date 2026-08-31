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
