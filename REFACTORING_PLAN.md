# IPTV-Check 架构重构计划

> 基于根因解决、方案复用、目标导向三大原则

---

## 一、架构问题诊断

### 1.1 后端架构问题

| 问题 | 影响 | 根因 |
|------|------|------|
| 状态管理混乱 | 线程安全隐患，状态不一致 | AppState 直接暴露所有字段，无封装 |
| 检测引擎分裂 | 维护成本高，功能重复 | checker.py（同步）和 async_checker.py（异步）各自实现 |
| API 响应不一致 | 前端适配困难 | 部分返回 dict，部分返回 HTTPException |
| M3U 服务状态硬编码 | 前端显示错误 | 总是返回 `{"running": False, "url": ""}` |
| 媒体探针未集成 | "假有效"频道问题 | 媒体探针功能存在但未接入主检测流程 |

### 1.2 前端架构问题

| 问题 | 影响 | 根因 |
|------|------|------|
| 状态同步问题 | 显示数据与实际不一致 | 前端不使用后端返回的统计数据 |
| API 响应处理不统一 | 错误处理缺失 | 缺少 axios 拦截器统一处理 |
| 组件耦合度高 | 难以维护和扩展 | 业务逻辑与 UI 混合 |

### 1.3 数据库问题

| 问题 | 影响 | 根因 |
|------|------|------|
| 缺少趋势分析 | 无法追踪频道稳定性 | 只有当前检测结果，无时间维度查询 |
| 索引不完善 | 查询性能差 | 缺少复合索引 |

---

## 二、重构策略

### 2.1 渐进式重构原则

1. **新增模块，不破坏现有功能**
2. **保持 API 兼容性**
3. **逐步替换旧实现**
4. **每步验证**

### 2.2 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 状态管理 | dataclass + threading.Lock | 轻量级，线程安全，无额外依赖 |
| API 响应 | FastAPI JSONResponse | 标准化，类型安全 |
| 任务队列 | asyncio.Queue | Python 内置，异步友好 |
| 缓存 | diskcache | 已集成，持久化 |
| 数据库 | SQLModel + SQLite | 已集成，类型安全 |
| 前端状态 | Pinia (已有) | 保持现状，优化封装 |

---

## 三、实施计划

### Phase 1: 基础架构模块（已完成准备）

- [x] `infra/service_state.py` - 线程安全状态容器
- [x] `infra/api_response.py` - 统一 API 响应格式
- [ ] `infra/database.py` 优化 - 修复 timedelta 导入，添加趋势查询

### Phase 2: 后端核心重构

- [ ] `server/app.py` 重构
  - 引入线程安全状态管理
  - 统一 API 响应格式
  - 修复 M3U 服务状态追踪
  - 集成媒体探针到检测流程
  - 添加 WebSocket 广播队列

### Phase 3: 前端架构优化

- [ ] `frontend/src/api/index.js` 重构
  - 统一响应处理
  - 添加错误拦截器
  - 标准化错误提示
- [ ] `frontend/src/stores/app.js` 优化
  - 使用后端返回的统计数据
  - 移除硬编码逻辑

### Phase 4: 新增功能

- [ ] 频道质量趋势分析
- [ ] 智能源推荐引擎
- [ ] 定时检测任务调度
- [ ] 多源聚合播放支持

### Phase 5: 测试验证

- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能验证

---

## 四、详细实现方案

### 4.1 统一状态管理架构

```python
# 新增模块
class ServiceState:
    """服务级全局状态，线程安全"""
    is_checking: bool = False
    local_isp: str = "未知"
    use_media_probe: bool = False
    ffmpeg_available: bool = False

class CheckState:
    """检测任务状态，线程安全"""
    is_running: bool = False
    total_count: int = 0
    checked_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0

class WebSocketManager:
    """WebSocket 客户端管理器"""
    - 线程安全的客户端列表
    - 异步广播队列
    - 自动清理断开的连接
```

### 4.2 统一 API 响应格式

```python
# 所有 API 端点统一返回
{
    "success": True/False,
    "code": 200/400/500,
    "message": "操作成功/失败原因",
    "data": {...}  # 可选
}
```

### 4.3 M3U 服务状态追踪

```python
class M3UServiceState:
    running: bool = False
    url: str = ""
    file_path: str = ""
    started_at: datetime = None
    
    def is_running(self) -> bool:
        return self.running and os.path.isfile(self.file_path)
```

### 4.4 媒体探针集成

在检测流程中，当检测到 HLS 流时，自动调用媒体探针验证可播放性：

```python
if is_m3u8 and use_media_probe:
    probe_result = await media_probe.probe(url)
    if not probe_result.is_playable:
        result.is_valid = False
        result.details = f"流不可播放: {probe_result.error_message}"
```

---

## 五、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| API 兼容性破坏 | 前端无法正常工作 | 保持现有 API 路径和响应结构 |
| 状态迁移遗漏 | 部分功能失效 | 全面测试所有路由 |
| 性能下降 | 响应变慢 | 压测验证，优化瓶颈 |

---

## 六、验收标准

1. 所有现有 API 端点正常工作
2. WebSocket 实时推送正常
3. 前端所有页面正常显示
4. 检测功能完整可用
5. 新增功能通过测试验证
