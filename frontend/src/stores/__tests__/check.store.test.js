import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCheckStore } from '../check'

describe('useCheckStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始状态应为空闲', () => {
    const store = useCheckStore()
    expect(store.isChecking).toBe(false)
    expect(store.checkTotal).toBe(0)
    expect(store.checkedCount).toBe(0)
    expect(store.progress).toBe(0)
    expect(store.phase).toBe('idle')
  })

  it('startCheckState 应正确初始化状态', () => {
    const store = useCheckStore()
    store.startCheckState(100)

    expect(store.isChecking).toBe(true)
    expect(store.checkTotal).toBe(100)
    expect(store.checkedCount).toBe(0)
    expect(store.phase).toBe('checking')
    expect(store.stage).toBe('parsing')
    expect(store.logs.length).toBe(1)
  })

  it('阶段加权进度 - parsing 阶段', () => {
    const store = useCheckStore()
    store.startCheckState(0)
    expect(store.progress).toBe(5)
  })

  it('阶段加权进度 - checking 阶段 50%', () => {
    const store = useCheckStore()
    store.startCheckState(100)
    store.handleChannelsLoaded(100)
    store.checkedCount = 50
    store.checkTotal = 100

    expect(store.progress).toBe(25 + 35)
  })

  it('handleChannelChecked 应更新计数', () => {
    const store = useCheckStore()
    store.startCheckState(10)

    store.handleChannelChecked({ is_valid: true })
    expect(store.checkedCount).toBe(1)
    expect(store.validCount).toBe(1)

    store.handleChannelChecked({ is_valid: false })
    expect(store.checkedCount).toBe(2)
    expect(store.invalidCount).toBe(1)
  })

  it('completeCheckState 应标记完成', () => {
    const store = useCheckStore()
    store.startCheckState(10)
    store.completeCheckState(10, 8, 2)

    expect(store.isChecking).toBe(false)
    expect(store.checkedCount).toBe(10)
    expect(store.validCount).toBe(8)
    expect(store.invalidCount).toBe(2)
    expect(store.phase).toBe('completed')
  })

  it('stopCheckState 应停止检测', () => {
    const store = useCheckStore()
    store.startCheckState(10)
    store.stopCheckState()

    expect(store.isChecking).toBe(false)
    expect(store.phase).toBe('stopped')
  })

  it('validRate 应正确计算', () => {
    const store = useCheckStore()
    store.checkedCount = 80
    store.validCount = 60
    expect(store.validRate).toBe(75)
  })

  it('currentStatus 应反映阶段消息', () => {
    const store = useCheckStore()
    store.startCheckState(100)
    store.stageMessage = '正在下载 3 个在线源...'

    expect(store.currentStatus).toBe('正在下载 3 个在线源...')
  })

  it('clearLogs 应清空日志', () => {
    const store = useCheckStore()
    store.addLog('测试日志')
    expect(store.logs.length).toBe(1)

    store.clearLogs()
    expect(store.logs.length).toBe(0)
  })
})
