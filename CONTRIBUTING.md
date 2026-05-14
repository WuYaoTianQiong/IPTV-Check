# 贡献指南

感谢你考虑为 IPTV-Check 做出贡献！

## 行为准则

本项目承诺为所有贡献者提供一个友好、包容的社区环境。请确保你的行为符合以下准则：
- 尊重他人，友善交流
- 接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

## 如何贡献

### 报告 Bug

如果你发现了 Bug，请在 GitHub 上创建一个 Issue，并包含以下信息：
1. 清晰的标题描述问题
2. 详细的复现步骤
3. 预期的行为和实际的行为
4. 你的运行环境（操作系统、Python 版本等）
5. 相关的截图或日志（如果有）

### 提出新功能

我们欢迎新功能的建议！请在提出之前：
1. 检查现有的 Issues，确保没有重复的建议
2. 清晰地描述你想要的功能
3. 解释为什么这个功能对项目有价值
4. 如果可能，提供实现思路或示例

### 提交代码

1. **Fork 本仓库**
2. **创建你的特性分支**：`git checkout -b feature/amazing-feature`
3. **提交你的更改**：`git commit -m 'Add some amazing feature'`
4. **推送到分支**：`git push origin feature/amazing-feature`
5. **提交 Pull Request**

### 代码规范

- 遵循 Python PEP 8 编码规范
- 使用有意义的变量名和函数名
- 添加必要的注释和文档字符串
- 确保代码通过语法检查（`python -m py_compile IPTV-Check.py`）

### 提交消息规范

我们使用以下格式编写提交消息：
```
<type>: <subject>

<body> (optional)
```

**type** 可以是：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具链相关

**示例**：
```
feat: 添加IPv4/IPv6分类导出功能

在导出对话框中新增协议分类选项，支持按网络协议类型分别导出结果
```

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/your-username/IPTV-Check.git
cd IPTV-Check

# 安装依赖
pip install ttkbootstrap requests openpyxl

# 运行程序
python IPTV-Check/IPTV-Check.py
```

## Pull Request 流程

1. 确保你的代码通过所有测试
2. 更新相关的文档
3. 确保你的分支与主分支保持同步
4. 项目维护者会尽快审查你的 PR

## 许可证

通过提交 Pull Request，你同意你的贡献将在本项目的 MIT 许可证下发布。

## 问题？

如果你有任何问题，随时可以：
- 创建一个 Issue
- 在现有 Issue 中留言

感谢你的贡献！🎉
