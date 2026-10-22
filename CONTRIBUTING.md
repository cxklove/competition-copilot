# Contributing to Competition Copilot

## 开始开发前

阅读 [README](README.md)、[AGENTS](AGENTS.md)、[Development Plan](docs/DEVELOPMENT_PLAN.md)
和 [Architecture](docs/ARCHITECTURE.md)。先确认任务范围与阶段状态，再在干净工作区更新本地：

```powershell
git status --short --untracked-files=all
git pull
```

本地有未提交工作或遇到分支冲突时，先处理并与维护者沟通，不自动丢弃工作或重写历史。
安装与启动按根 README；锁文件和运行命令的详细说明保留在 Backend / Frontend README。

## 架构边界

- Frontend 只展示 authoritative result，不计算资格、评分、技能差距、影响或重规划 truth。
- Agent 负责意图、能力选择和解释，不重算 Eligibility / Recommendation / SkillGap / Impact / Replanning。
- Application 负责 use case、输入准备和 orchestration；Tool 通过抽象调用正式能力。
- Domain 不依赖 LLM；相同版本化输入应产生 deterministic 结果。
- Repository 只负责数据访问，Infrastructure 实现接口；上层不得越过抽象读取 seed/数据库。
- Preparation != Authorization。Frontend/模型文本不能授权 mutation，审批、精确 plan ref、
  current version、CAS 和 single-use continuation 保护必须保留。
- 事实变更需可追溯 source、verification、observed_at、reason/evidence；未知不改写为否定或已满足。

## Git workflow

一次改动聚焦一个已确认任务。不要使用 `git add .`，先检查完整状态，再显式 stage 文件：

```powershell
git status --short --untracked-files=all
git diff
git add -- path/to/intended-file
git diff --cached
```

提交前执行根 README 的 Backend pytest、Ruff、Frontend tests/lint/build、两项 generated
schema `--check` 和 `git diff --check`。在 PR 中记录实际运行的命令与结果；未运行需说明原因，
不能将未运行的检查勾为通过。文档类任务可按明确授权的范围减少回归并注明依据。

不要提交密钥、`.env`、本地生成数据、临时截图或依赖目录。禁止 force push，除非维护者明确允许。
遇到 non-fast-forward、保护分支或权限拒绝，停止并沟通，不自动 rebase/reset 或绕过保护。

## Commit style

推荐使用简洁前缀与动作说明：`feat:`、`fix:`、`docs:`、`test:`、`refactor:`、`chore:`。
例如 `docs: add team onboarding guide`。不强制复杂 scope 或发布自动化规则。

## Phase workflow

```text
Implementation → Independent Review → Status Sync → Full Regression → Commit → Push
```

没有完成独立评审时，不将阶段标为 CLOSED_VERIFIED。阶段变更以 Development Plan 为准，
状态同步不能隐式授权下一阶段，也不能将 readiness 写成已实现。
当前 PX1 / PX2 Core 为 CLOSED_VERIFIED；P12–P14 CLOSED_FROZEN；PX3 / P15 NOT_STARTED。
PX2 Product Detail Enrichment 为 DEFERRED 非阻塞工作，后续单独确认范围。

## Pull Request

使用 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md)，说明 why/scope、架构边界、验证与数据影响。
涉及 UI 必须附可复核截图；不复制未获授权的第三方代码或私有数据。
LICENSE STRATEGY 仍为 UNDECIDED，许可证由维护者另行决定。
