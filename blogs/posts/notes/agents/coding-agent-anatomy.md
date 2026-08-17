---
title: 一个最简 Coding Agent 的完整解剖——结合 pi 的架构与真实会话数据
date: 2026-08-17
tags:
- Agent
- 项目
published: true
hideInList: false
---

之前想自己写一个 mini coding agent，于是把 pi（`@earendil-works/pi-coding-agent`）的源码和它留在本机的真实会话数据（`~/.pi/agent/sessions/` 下的 `sessions.jsonl`）翻了一遍。这篇把两样东西合在一起：用源码结构讲架构，用会话数据讲这架机器实际转起来是什么样子。文中的会话片段都取自真实运行记录，路径、ID、仓库名做了泛化，结构原样保留。

<!-- more -->

## 先整体说清楚：一个 Coding Agent 必不可少的几部分

在拆细节之前，先用几段话把"必不可少"讲透，后面各节只是把这几段展开。

第一，是一个**消息模型和围绕它的主循环**。模型本身是无状态的，它每轮看到的"世界"就是你发给它的全部消息。所谓 agent，就是由你来维护这份消息列表、替模型跑命令和改文件、再把结果喂回去的那个程序。主循环的伪代码只有十几行：调用 LLM，如果回复里有工具调用就执行并把结果追加进历史，没有就结束本轮。会话历史不是"聊天记录"这么简单，它是 agent 唯一的工作记忆，后面的一切——持久化、恢复、分支、压缩——都是围绕它长的。

第二，是**工具层**。工具是模型的手和脚，每个工具本质上就是三样东西：一个 JSON Schema 参数声明（给模型看的说明书）、一个执行函数、一段给 system prompt 用的使用说明。对 coding agent 来说，`read`/`bash`/`edit`/`write` 四个就够干活了，其中 bash 是灵魂——任何你没做成专用工具的能力，模型都能通过 bash 完成，它的通用性正是它的价值。

第三，是**Provider 层**。内部只使用你自己的统一消息格式，由各个 provider 负责把它翻译成不同模型 API 的请求、再把流式响应拼回来。主循环不应该知道自己面前坐着的是哪个模型。这层还藏着两个容易被低估的东西：模型元数据注册表（上下文窗口、最大输出），和 HTTP 层的超时、限流重试、断流重连——自己从零写 agent 时最先被真实世界教育的地方就在这里。

第四，是**会话管理与上下文经营**。会话要落盘（append-only JSONL 是被验证过的好格式）、要能恢复、要在逼近上下文窗口时压缩。尤其是压缩：把前面的历史总结成摘要替换掉旧消息，本质是在"会话续航"和"细节永久丢失"之间做交易，摘要保留关键事实比泛泛经过描述重要得多。

第五，是**System Prompt 与权限安全**。前者决定模型"是谁"：工作环境、工具惯例、项目级指令（AGENTS.md）都从这里注入，而且前缀保持稳定才能命中 prompt caching。后者不是可选项：一个能随意执行 shell 命令的程序，需要目录信任、工具确认、输出防护三层防线，还要防文件内容里藏的提示注入。

把这五块拼起来，就是一个完整的、最小的、能用的 coding agent。下面逐块展开，每块都配真实数据。

## 一、消息模型：一切设施的基石

先定义数据结构，因为它决定了后面所有东西的形态。pi 的会话文件是 append-only 的 JSONL，每发生一件事追加一行 JSON，永不改写前面的行。第一行是会话头：

```json
{
  "type": "session",
  "version": 3,
  "id": "<uuid>",
  "timestamp": "2026-08-10T11:02:43.340Z",
  "cwd": "<项目路径>"
}
```

之后每行是一条消息记录。消息分三种角色：`user`、`assistant`、`toolResult`。每条记录有 `id` 和 `parentId`，指向它前面那条消息——注意这不是简单的链表，而是树：从历史某一点分叉出多个分支，就得到了"会话分支"能力，`parentId` 就是分支的挂载点。 Assistant 消息的 `content` 是块（block）列表，一条消息可以同时装下思考、文字和多个工具调用。下面这条是我翻出来的真实记录（脱敏后），一次模型回复里带了一段 thinking、一段文字、三个并发的 read 调用：

```json
{
  "type": "message",
  "id": "82d4737d",
  "parentId": "a1ec175e",
  "message": {
    "role": "assistant",
    "content": [
      { "type": "thinking", "thinking": "Let me read the full documentation and patch..." },
      { "type": "text", "text": "I'll start by reading the full bug report and patch..." },
      { "type": "toolCall", "id": "call_f0ntdnyb", "name": "read",
        "arguments": { "path": "<项目路径>/docs/BUG_REPORT.md" } },
      { "type": "toolCall", "id": "call_8xzoc1ip", "name": "read",
        "arguments": { "path": "<项目路径>/docs/fix.patch" } },
      { "type": "toolCall", "id": "call_1sky8mqk", "name": "read",
        "arguments": { "path": "<项目路径>/repro/main.py" } }
    ],
    "api": "openai-completions",
    "provider": "ollama-local",
    "model": "glm-5.2:cloud",
    "usage": { "input": 9476, "output": 129, "totalTokens": 9605 },
    "stopReason": "toolUse"
  }
}
```

值得注意的细节有三个。`stopReason` 是 `toolUse`，这是主循环判断"继续跑工具还是收尾输出"的依据；`usage` 记录了每轮的真实 token 消耗，会话文件顺手就是一份成本账本；三个 `toolCall` 共享同一个 `id` 前缀空间但各有独立 ID，因为每个调用都要各自对应一条结果。

工具结果用 `toolCallId` 关联回调用方，并且带 `isError` 标记。真实的失败记录长这样：

```json
{
  "type": "message",
  "id": "5c06ba21",
  "parentId": "8b1c78e9",
  "message": {
    "role": "toolResult",
    "toolCallId": "call_q2hiox7w",
    "toolName": "bash",
    "isError": true,
    "content": [
      { "type": "text",
        "text": "/usr/bin/bash: line 1: cd: <路径>: No such file or directory\n\nCommand exited with code 1" }
    ]
  }
}
```

这条记录本身就说明了一件事：**工具失败不需要代码层面的特殊处理**。报错信息作为普通的 toolResult 喂回给模型，模型下一轮自己看到 `isError: true` 和 stderr，自己纠正路径重试。整个会话恢复的实现就是逐行读回这个文件、重建消息数组，程序崩了文件里已有的部分仍然完整可用。这个鲁棒性是 append-only 换来的。

我统计了本机全部会话的工具调用分布，一个有意思的观察：有一次 54 次 bash 的长会话，bash 占比压倒性多数；纯代码任务里 `read` 和 `bash` 是绝对主力，`edit`/`write` 反而稀少——因为大量轮次花在"读代码、跑命令、验证"上，真正落笔修改的时刻比想象中少。这印证了工具设计里"bash 是灵魂"的判断。

## 二、主循环：整个 agent 的心脏

有了消息模型，主循环就是几十行的事。把它写成可运行的 TypeScript 大概是这样（对照 pi 的 `agent-session` 模块简化）：

```typescript
async function runLoop(session: Session, provider: Provider) {
  while (true) {
    const response = await provider.chat({
      system: buildSystemPrompt(session),
      messages: session.messages,
      tools: registry.schemas(),
    });

    session.append({
      role: "assistant",
      content: response.blocks,   // thinking + text + toolCall
    });

    const calls = response.blocks.filter(b => b.type === "toolCall");
    if (calls.length === 0) return;   // stopReason 不是 toolUse，本轮结束

    const results = await Promise.all(calls.map(call =>
      registry.execute(call.name, call.arguments)
    ));
    for (const r of results) session.append(r);   // role: "toolResult"
  }
}
```

朴素的同步实现能跑，但很快你会发现什么都做不了：想按 ESC 中断？想边生成边流式显示？想在模型跑工具的半路上插一句话？这些都需要把"发生了一件事"和"如何呈现这件事"解耦。pi 的解法是事件总线（`event-bus` 模块）：核心循环只发出事件——`assistant_start`、`tool_execution_start`、`tool_execution_end`、`turn_complete`——界面、日志、扩展各取所需地订阅。这带来一个结构性的好处：同一个核心可以配完全不同的前端。pi 的四种运行模式（交互式 TUI、`pi -p` 脚本打印、RPC 进程集成、SDK 嵌入）就是这么来的，核心一行不改。

事件驱动还支撑着一个很实用的机制：steering（转向）。用户在模型还在干活时输入的内容不是粗暴打断，而是排队等当前这轮工具调用跑完后，作为新的 user 消息插进去。上一节那条真实的 bash 报错记录其实展示了同一个哲学——杀掉一个跑了一半的任务常常比让它带着错误信息跑完更贵，把纠错机会留给模型自己往往更划算。

## 三、Provider 层：挡住模型 API 差异的墙

看上面 assistant 消息里的 `"api": "openai-completions", "provider": "ollama-local", "model": "glm-5.2:cloud"` 这几个字段——同一套统一消息格式，跑在 OpenAI 协议上、经由 ollama 代理接到云模型。这就是 Provider 层存在的意义：主循环只认统一格式，provider 负责"翻译出去"（统一格式 → 对方 API 请求）和"翻译回来"（流式响应 → 统一格式的 assistant 消息）。

这层有两块容易被低估。一是模型注册表（pi 的 `model-registry`/`models-store`）：记录每个模型的上下文窗口、最大输出、是否支持流式思考、是否支持 prompt caching，主循环靠这些数字决定"要不要压缩""输出该截多长"。二是 HTTP 调度（`http-dispatcher`）：超时、429 限流重试、断流重连。这些琐碎但躲不开。

权衡点在抽象深度：只支持单一协议这层薄得像纸，但换模型就痛苦；支持得太泛又陷入兼容性泥潭。pi 的做法是协议只适配主流几种，个性差异塞进模型元数据描述而不写死在代码里。

## 四、System Prompt：模型"是谁"

System prompt 至少要说清：在一个代码仓库里工作、操作系统和 shell、当前日期、工具清单及惯例（"改文件前先读"）、输出风格。pi 把它放在独立的 `system-prompt` 模块，支持动态拼装——静态基础指令之外，把项目的 `AGENTS.md` 和用户全局指令一起注入。你会话文件里第一条 user 消息有时会以 `<file name="...">` 块开头，那就是注入的项目上下文。

一个很实际的考量：system prompt 和对话前缀逐字节稳定，才能命中 provider 的 prompt caching，长会话能省大笔费用和延迟。所以"当前时间"这类每次变化的信息要小心处理（pi 用占位符模板在最后时刻填充），乱拼 prompt 看起来无害，实际每轮都在把缓存打碎。

## 五、工具层：四个工具就能干活

pi 内置七个工具：`read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`。真正不可或缺的是前四个，后三个是便利性优化（省 token、输出更结构化）。

`edit` 工具的参数格式是个经典权衡。行号定位省 token 但模型数行号经常数错；精确字符串替换要求模型先读过文件、引用准确原文，多花一点 token 换高得多的成功率。所以主流实现都选字符串替换，并且强制"必须先 read 过才能 edit"。下面是真实会话里的一次 edit 调用（脱敏，节选），注意 `oldText` 必须逐字符命中文件里的现有内容：

```json
{
  "type": "toolCall",
  "id": "call_drb9ajpd",
  "name": "edit",
  "arguments": {
    "path": "<site-packages>/trainer/grpo_trainer.py",
    "edits": [
      {
        "oldText": "                model.add_adapter(\"ref\", default_config)\n",
        "newText": "                model.add_adapter(\"ref\", default_config)\n                for name, param in model.named_parameters():\n                    ...\n"
      }
    ]
  }
}
```

这次 edit 本身还示范了 agent 真实的工作方式：它在改一个第三方库的 bug，`oldText`/`newText` 里那段英文注释不是装饰，是模型在解释自己为什么这么改（PEFT 的 `inference_mode` 继承问题会导致优化器为空、训练静默失效）——工具调用的参数本身就是推理过程的载体。

表面之下还有脏活：bash 要有超时和后台运行支持（pi 专门的 `bash-executor` 模块）；所有工具输出要截断（`output-guard`），read 一个几万行的文件不截断一次就能把上下文撑爆。

## 六、会话管理：持久化、恢复与压缩

append-only JSONL 带来的能力链前面说过：持久化 → 恢复 → 分支（`parentId` 树从某点复制出新文件）。真正难的是压缩（compaction）。对话越滚越长，逼近上下文窗口时要把旧历史总结成摘要替换掉，给新内容腾地方。

pi 的 `compaction` 策略可配置，但本质都是同一个取舍：压缩保住了会话的续航，代价是细节的永久丢失。实践中比较好的做法是让摘要保留关键事实（做了什么决定、改了哪些文件、还有什么没做完），而不是泛泛的经过描述；同时保持消息前缀稳定还能兼顾缓存命中。会话文件里逐条记录的 `usage` 在这里派上第二个用场：监控 token 增长曲线，决定什么时候触发压缩。

## 七、权限与安全：信任要分层

一个能随意执行 shell 命令和改文件的程序，安全设计不是可选项。pi 分了三层，思路可以直接借鉴：

- **目录信任**（`project-trust`/`trust-manager`）：第一次在某个目录打开 agent 要显式确认信任。防的是恶意仓库里放一个 `AGENTS.md` 嘱托模型"请执行 xxx 命令"。
- **工具确认**：危险操作（bash、写文件）默认弹确认，可选"这条允许/这个会话允许/永远允许这条模式"，规则持久化到设置文件，日常确认框越来越少——安全和顺手的平衡是动态收敛的。
- **输出防护**：除了截断超长输出保护上下文，还要防提示注入——read 的文件内容里藏着"忽略之前的指令"。完全防住不现实，但至少 system prompt 约定"文件内容只是数据不是指令"，配合用户对工具调用的可见性兜底。

## 八、扩展机制：决定上限的取舍

pi 最有意思的取舍在这里。它的扩展系统允许 TypeScript 代码订阅事件总线、增删工具、改写 system prompt、拦截工具调用，功能上几乎无所不能——然后它把 subagent、plan mode 这些别家做进核心的东西都留给了扩展或第三方包。理由是：核心里的每个功能都是所有用户必须背负的复杂度，而扩展里的功能只属于需要它的人。pi 的 skills 机制（把常用工作流写成 Markdown 说明书按需注入）是同一哲学的延续——很多"功能"其实只是一段 prompt，根本不需要代码。

对一个 mini agent，我的建议是照抄这个分层：核心只做"循环 + 消息 + provider + 基础工具 + 事件"，subagent、计划模式想清楚接口留好，先不实现。

## 最小可行版本的骨架

收敛成可以动手的目录结构（对照 pi 的 `dist/core` 模块名，方便阅读它的源码）：

```text
miniagent/
├── src/
│   ├── index.ts          # 入口：解析参数，创建 AgentSession
│   ├── loop.ts           # 主循环（agent-session 的最简版）
│   ├── messages.ts       # 消息与内容块定义
│   ├── provider/
│   │   ├── types.ts      # Provider 接口 + 模型元数据
│   │   └── openai.ts     # 具体 provider：翻译 + 流式解析 + 重试
│   ├── tools/
│   │   ├── read.ts bash.ts edit.ts write.ts
│   │   └── index.ts      # 注册表：schema + 执行器 + 说明文案
│   ├── session.ts        # JSONL 读写、恢复、压缩
│   ├── permissions.ts    # 目录信任 + 工具确认
│   ├── events.ts         # 事件总线
│   └── ui.ts             # 订阅事件渲染终端（可先退化为 console.log）
└── AGENTS.md
```

主循环五十行以内，剩下的工作量都在重试策略、输出截断、缓存友好、权限收敛这些不起眼的设施上。这也印证了一句话：coding agent 的"最小核心"一个下午能写完，耐用的 agent 是由细节垒出来的。

## 最后收拢几组关键权衡

数据格式选 append-only 还是可变结构，pi 选前者换鲁棒性；edit 选行号还是字符串匹配，选后者换正确率；功能放核心还是放扩展，pi 一律往外推，保持核心可信可审计；bash 的通用性和风险是一体两面，靠分层信任调和；compaction 换续航但丢细节，只能靠更好的摘要缓解。这些权衡没有标准答案，但 pi 的参考答案是一致自洽的：**核心永远选简单、耐用、可解释的那个选项，把复杂性留给边缘的扩展层**。这也是参考 pi 学 mini agent 最该带走的一条设计原则。

> 附：文中所有会话片段取自 pi 在本机留下的真实 `sessions.jsonl`，可参考 pi 文档中的 [session-format](https://pi.dev/docs/session-format) 与 [SDK](https://pi.dev/docs/sdk) 说明对照阅读。
