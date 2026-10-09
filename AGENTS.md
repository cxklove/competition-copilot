# Repository Guidelines

## 项目与目录

Competition Copilot 是面向高校学生的竞赛全生命周期决策与成长平台，目标参加华为 ICT 创新赛。目标能力包括学生画像、赛事检索、资格检查、个性化推荐、技能诊断、备赛规划、赛事变化检测与重规划，以及 Agent 工具、MCP、Web 前端和评测。核心设计是约束感知决策、静态知识与动态状态结合、事件驱动重规划。不得复制或依赖其他平台的源码、前端代码及私有整理数据；Schema、UI 和数据接入流程须独立实现。

仓库目录约定：`backend/` 放服务与领域代码，`frontend/` 放界面，`data/` 放可共享的数据样例，`docs/` 放设计文档，`evals/` 放评测用例，`scripts/` 放可重复运行的脚本。新增模块时同步说明其目录职责。

## 开发、构建与测试

`backend/` 已提供 `pyproject.toml`、`requirements.lock`、pytest 测试和 Ruff lint；准确的安装、测试、lint 与构建命令见 `backend/README.md`。当前尚无完整应用启动命令。提交前运行 `git status --short` 和 `git diff --check`；首次引入其他模块时，同时提交依赖清单、锁文件及该模块 README 中准确的安装、运行、构建和测试命令。当前没有覆盖率门槛；新功能仍须满足下方测试规则。

## 代码风格与命名

`backend/` 已配置 Ruff；新增 Python 代码使用四空格缩进和 `snake_case` 模块、函数名，并运行现有 lint。新增 JavaScript/TypeScript 代码默认使用两空格缩进、`camelCase` 变量和函数名、`PascalCase` 组件名；引入前端语言时配置格式化与 lint 工具，并在模块内统一执行。Python 测试放在 `backend/tests/`；TypeScript 测试可用相邻的 `*.test.ts` 或 `*.test.tsx`。

## 架构依赖方向（强制）

运行时能力调用与源码依赖边界必须遵循以下由外到内的顺序，禁止反向或越过抽象依赖具体实现：

```text
API / Agent / MCP
→ Application / Tool
→ Domain Service
→ Repository Interface
→ Infrastructure Adapter
```

箭头表示运行时能力使用路径，不要求每次调用都经过所有层。源码依赖必须指向抽象：`Infrastructure Adapter` 实现 `Repository Interface`，接口和上层代码不得导入适配器实现。Tool 对抽象 Repository/Gateway 的访问须遵守下方 Tool 规则。

## 不可违反的工程规则

1. **Domain 层禁止依赖 LLM。** Domain 不得依赖 LLM、模型 SDK 或 Agent 框架，也不得调用模型服务；业务规则必须能独立运行和测试。
2. **Repository 层只负责数据访问。** Repository Interface 定义数据访问能力，具体实现置于 Infrastructure Adapter；两者均不得实现资格判断、推荐评分或其他业务规则。
3. **Tool 层只通过抽象使用能力。** Tool 通过 Application/Domain Service 以及抽象 Repository/Gateway 使用能力；抽象 Repository/Gateway 仅用于数据或外部能力访问，业务判断须委托 Domain Service。Tool 不得直接依赖具体 Web、数据库、Agent SDK 或第三方基础设施。每个 Tool 必须可独立运行和测试。
4. **API 层不得直接实现业务规则。** API 只处理请求与响应、语法及协议校验和调用编排；须通过 Application/Tool 调用 Domain Service 处理业务约束。
5. **Agent 层不得实现资格判断和推荐评分公式。** Agent 只负责意图理解、工具选择、复杂推理和结果解释；资格与评分结果必须来自确定性的业务服务。不得为了“多 Agent”而人为拆分 Agent。
6. **所有硬规则必须 deterministic。** 相同的版本化输入必须产生相同结果；不得让 LLM 判定硬性资格或约束。LLM 不得直接读取原始 JSON 或数据库来完成事实判断。
7. **所有关键决策必须返回 reason code 和 evidence。** 资格检查、推荐、诊断与重规划等结果须包含稳定的 `reason_code` 和可追溯的 `evidence`，注明依据、来源或规则版本。
8. **AgentArts 代码必须隔离。** 所有 AgentArts 集成均置于 Adapter 边界内；迁移时只替换运行与编排层，不改写核心业务逻辑。
9. **每个阶段只允许修改当前任务相关文件。** 不顺带重构、格式化或修改其他文件；新增文件也必须服务于当前阶段目标。
10. **所有新功能必须配套测试。** 每项新功能须提交可复现的测试，覆盖关键正常路径和边界规则；不能只依靠 Agent 对话验证。
11. **赛事关键事实必须可溯源。** 每条关键事实保存 `source_url`、`source_type`、`observed_at` 和 `verification_status`。未经验证的 `CompetitionCandidate` 不得进入正式赛事库，也不得作为确定性决策依据。
12. **Competition Digital Twin 必须保留版本。** 动态状态禁止静默覆盖；每次变更须保留 `Snapshot`、可比较的 `Diff` 和对应的 `CompetitionEvent`，以便追溯与重放。
13. **自动重规划必须可审计。** 每次 Replanning 均保存 `before`、`after`、`trigger_event_id`、`reason_code` 和 `evidence`，并能关联触发事件与前后方案。

## Definition of Done

- 改动仅涉及当前任务文件，符合依赖方向；没有密钥、私有数据或未经验证的确定性依据。
- 新功能提交可复现的自动化测试，覆盖正常和关键边界路径；相关测试通过。
- 关键决策提供 `reason_code` 与 `evidence`；涉及赛事事实、动态状态或重规划时，保留上述来源与版本记录。
- 更新受影响的文档、配置及运行命令；提交前检查 `git diff --check`，并在 Pull Request 中记录验证结果。

## 提交与 Pull Request

提交标题统一推荐使用 `chore:`、`feat:`、`fix:`、`test:`、`docs:` 前缀，后接简短的祈使句，例如 `feat: add competition search API`。Pull Request 应说明改动、列出测试命令及结果；有相关议题时附链接，界面变更附截图。

## 安全与配置

不要提交密钥或私有数据。引入配置时提供安全的示例文件，并忽略本地密钥和生成的数据。
