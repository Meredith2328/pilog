---
title: 一个最简 Coding Agent 的完整解剖——结合 pi 的架构与真实会话数据
date: 2026-08-17
tags:
- Agent
- 项目
published: true
hideInList: false
---

希望了解最小化的coding agent是什么样的。于是整理了 pi（`@earendil-works/pi-coding-agent`）的源码和它留在本机的真实会话数据（`~/.pi/agent/sessions/` 下的 `sessions.jsonl`）。这篇把两样东西合在一起：用源码结构讲架构，用会话数据讲这架机器实际转起来是什么样子。文中的会话片段都取自真实运行记录，路径、ID、仓库名做了泛化，结构原样保留。

<!-- more -->

> 自勉：
>
> 应该通过一手信息、而不是别人/ai总结的信息学习。

## 先整体说清楚：一个 Coding Agent 必不可少的几部分

在拆细节之前，先用几段话把"必不可少"讲透，后面各节只是把这几段展开。

第一，是一个**消息模型和围绕它的主循环**。模型本身是无状态的，它每轮看到的"世界"就是你发给它的全部消息。所谓 agent，就是由你来维护这份消息列表、替模型跑命令和改文件、再把结果喂回去的那个程序。主循环的伪代码只有十几行：调用 LLM，如果回复里有工具调用就执行并把结果追加进历史，没有就结束本轮。会话历史不是"聊天记录"这么简单，它是 agent 唯一的工作记忆，后面的一切——持久化、恢复、分支、压缩——都是围绕它长的。

第二，是**工具层**。工具是模型的手和脚，每个工具本质上就是三样东西：一个 JSON Schema 参数声明（给模型看的说明书）、一个执行函数、一段给 system prompt 用的使用说明。对 coding agent 来说，`read`/`bash`/`edit`/`write` 四个就够干活了，其中 bash 是灵魂——任何你没做成专用工具的能力，模型都能通过 bash 完成，它的通用性正是它的价值。

第三，是**Provider 层**。内部只使用你自己的统一消息格式，由各个 provider 负责把它翻译成不同模型 API 的请求、再把流式响应拼回来。主循环不应该知道自己面前坐着的是哪个模型。这层还藏着两个容易被低估的东西：模型元数据注册表（上下文窗口、最大输出），和 HTTP 层的超时、限流重试、断流重连——自己从零写 agent 时最先被真实世界教育的地方就在这里。

第四，是**会话管理与上下文经营**。会话要落盘（append-only JSONL 是被验证过的好格式）、要能恢复、要在逼近上下文窗口时压缩。尤其是压缩：例如可以把前面的历史总结成摘要替换掉旧消息，本质是在"会话续航"和"细节永久丢失"之间做交易，摘要保留关键事实比泛泛经过描述重要得多。

第五，是**System Prompt 与权限安全**。前者决定模型"是谁"：工作环境、工具惯例、项目级指令（AGENTS.md）都从这里注入，而且前缀保持稳定才能命中 prompt caching。后者不是可选项：一个能随意执行 shell 命令的程序，需要目录信任、工具确认、输出防护三层防线，还要防文件内容里藏的提示注入。

把这五块拼起来，就是一个完整的、最小的、能用的 coding agent。下面这张分层图是全文的地图，每一层都能点开看细节，后面两节还会用同样风格的图拆开消息模型和主循环。

<div class="archviz">
  <div class="av-head"><span class="av-tag">架构图</span><span class="av-title">Coding Agent 分层总览：核心很小，设施环绕</span></div>
  <div class="av-body">
    <div class="av-layers">
      <div class="av-layer l-front">
        <div class="av-l-head"><span class="av-l-name">前端层（可整体替换）</span><span class="av-pi">tui · print · rpc · sdk</span></div>
        <div class="av-l-desc">只订阅事件做渲染，不含任何业务逻辑——所以同一个核心能配四种完全不同的前端。</div>
        <details class="av-fold"><summary>四种运行模式</summary><div class="av-fold-body">交互式 TUI（日常使用）、<code>pi -p</code> 脚本打印模式（管道 / CI）、RPC 模式（进程集成）、SDK 模式（嵌入别的应用）。核心循环一行不改。</div></details>
      </div>
      <div class="av-l-arrow"><span class="av-alabel">订阅事件</span></div>
      <div class="av-layer l-bus">
        <div class="av-l-head"><span class="av-l-name">事件总线</span><span class="av-pi">event-bus</span></div>
        <div class="av-l-desc">核心只负责喊"发生了一件事"，谁来听、怎么呈现是订阅者的事。</div>
        <details class="av-fold"><summary>真实事件流</summary><div class="av-fold-body"><code>agent_start</code> → （<code>turn_start</code> → <code>message_start</code>/<code>message_update</code>/<code>message_end</code> → <code>tool_execution_start</code>/<code>tool_execution_end</code> → <code>turn_end</code>）× N → <code>agent_end</code> → <code>agent_settled</code>。steering（转向消息）不打断循环，排队插入。</div></details>
      </div>
      <div class="av-l-arrow"><span class="av-alabel">驱动 / 被驱动</span></div>
      <div class="av-layer l-core">
        <div class="av-l-head"><span class="av-l-name">核心循环</span><span class="av-pi">agent-session</span><span class="av-badge">50 行以内</span></div>
        <div class="av-l-desc">调 LLM → 解析回复 → 执行工具 → 结果回填 → 直到没有 toolCall。整个 agent 的心脏。</div>
        <details class="av-fold"><summary>伪代码</summary><div class="av-fold-body"><pre>while true:
    resp = LLM(system + messages + tools)
    append(resp)
    if not resp.toolCalls: return
    for call in resp.toolCalls:
        append(execute(call))</pre></div></details>
      </div>
      <div class="av-l-arrow"><span class="av-alabel">调用设施</span></div>
      <div class="av-layer l-infra">
        <div class="av-l-head"><span class="av-l-name">设施层（核心循环依赖的全部）</span></div>
        <div class="av-l-desc">消息模型与会话管理 · Provider 翻译 · 工具注册表 · 权限 · System Prompt 拼装。</div>
        <details class="av-fold"><summary>pi 对应模块</summary><div class="av-fold-body">消息 / 会话：<code>messages</code> · <code>session-manager</code>（JSONL 落盘、压缩）｜Provider：<code>pi-ai</code>（协议适配）· <code>model-registry</code>（模型目录）· <code>http-dispatcher</code>（undici 全局配置）｜工具：<code>tools/bash.js</code> · <code>tools/truncate.js</code>（2000 行 / 50KB 截断）｜安全：<code>trust-manager</code>（目录信任）｜提示词：<code>system-prompt</code>。</div></details>
      </div>
      <div class="av-l-arrow"><span class="av-alabel">系统调用 / HTTP</span></div>
      <div class="av-layer l-ext">
        <div class="av-l-head"><span class="av-l-name">外部世界</span></div>
        <div class="av-l-desc">模型 API（OpenAI / Anthropic 协议，流式返回）· 文件系统 · shell。虚线意味着：边界之外，agent 只能通过工具触达。</div>
      </div>
    </div>
  </div>
  <div class="av-foot">自上而下每层只依赖下一层；换前端不动核心，换模型只动 Provider。</div>
</div>

## 一、消息模型：一切设施的基石

先看一张真实会话的消息链——下面每一个节点都是 JSONL 里的一行，节点间的连线靠 `parentId`，工具结果靠 `toolCallId` 找回它的调用方。红色那条是一次真实的 bash 失败，注意它如何作为普通消息流回模型：

<div class="archviz">
  <div class="av-head"><span class="av-tag">架构图</span><span class="av-title">一次真实会话的消息链（sessions.jsonl 逐行对应）</span></div>
  <div class="av-body">
    <div class="av-chain">
      <div class="av-msg av-m-head">
        <div class="av-name"><span class="av-m-role">session 头</span><span class="av-m-id">type: "session" · version: 3</span></div>
        <div class="av-m-body">会话 ID、时间戳、工作目录（cwd）。之后每一行都是一条消息，永不改写前面的行。</div>
        <details class="av-fold"><summary>原始 JSON</summary><div class="av-fold-body"><pre>{ "type": "session", "version": 3,
  "id": "&lt;uuid&gt;", "timestamp": "...",
  "cwd": "&lt;项目路径&gt;" }</pre></div></details>
      </div>
      <div class="av-msg">
        <div class="av-name"><span class="av-m-role">user</span><span class="av-m-id">id: a1ec175e · parentId: …</span></div>
        <div class="av-m-body">用户输入，或注入的项目上下文（<code>&lt;file name="…"&gt;</code> 块）。</div>
      </div>
      <div class="av-msg av-m-asst">
        <div class="av-name"><span class="av-m-role">assistant</span><span class="av-m-id">stopReason: "toolUse" · 9476 in / 129 out</span></div>
        <div class="av-m-body">一条消息 = 块列表：<code>thinking</code> + <code>text</code> + 三个并发的 <code>toolCall</code>。模型一口气要三个文件。</div>
        <details class="av-fold"><summary>content 块结构</summary><div class="av-fold-body"><pre>[ { "type": "thinking", "thinking": "Let me read the full doc…" },
  { "type": "text", "text": "I'll start by reading…" },
  { "type": "toolCall", "id": "call_f0ntdnyb", "name": "read",
    "arguments": { "path": "…/BUG_REPORT.md" } },
  … 共 3 个 toolCall ]</pre>另有 <code>api</code> / <code>provider</code> / <code>model</code> / <code>usage</code> 元数据随行记录——会话文件顺手就是成本账本。</div></details>
      </div>
      <div class="av-msg av-m-tool">
        <div class="av-name"><span class="av-m-role">toolResult</span><span class="av-m-id">toolCallId: call_f0ntdnyb · isError: false</span></div>
        <div class="av-m-body">read 的文件内容，截断后喂回。三个 toolCall 各自对应一条 toolResult。</div>
      </div>
      <div class="av-msg av-m-bad">
        <div class="av-name"><span class="av-m-role">toolResult</span><span class="av-m-id">isError: true · bash</span></div>
        <div class="av-m-body">真实失败记录：<code>cd: &lt;路径&gt;: No such file or directory</code>，exit code 1。</div>
        <details class="av-fold"><summary>为什么失败不需要特殊处理</summary><div class="av-fold-body">报错信息作为普通 toolResult 喂回，模型下一轮看到 <code>isError: true</code> 和 stderr，自己纠正路径重试。纠错是模型的事，不是循环的事。</div></details>
      </div>
      <div class="av-msg av-m-asst">
        <div class="av-name"><span class="av-m-role">assistant</span><span class="av-m-id">stopReason: 无 toolCall</span></div>
        <div class="av-m-body">没有工具调用的回复 = 本轮结束，控制权交还用户。</div>
      </div>
    </div>
  </div>
  <div class="av-foot">id/parentId 构成一棵树：从任意节点分叉复制，就得到"会话分支"。</div>
</div>

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

有了消息模型，主循环就是几十行的事。数据在循环里怎么流的，一张图看清楚——注意右侧那条蓝色的回环，它就是"agent"和"一次性问答"的全部区别：

<div class="archviz">
  <div class="av-head"><span class="av-tag">架构图</span><span class="av-title">主循环数据流：一圈 = 一轮工具调用</span></div>
  <div class="av-body">
    <div class="av-flow">
      <div class="av-stage av-node k-core">
        <div class="av-name">组装请求<span class="av-pi">system + messages + tools</span></div>
        <div class="av-sub">System prompt（含 AGENTS.md）+ 全部历史 + 工具 schema 注册表</div>
      </div>
      <div class="av-down is-accent"><span class="av-alabel">HTTP（流式）</span></div>
      <div class="av-stage av-node">
        <div class="av-name">Provider 调用<span class="av-pi">model-registry · http-dispatcher</span></div>
        <div class="av-sub">统一格式 → 目标协议；重试 / 限流 / 断流重连都在这层</div>
        <details class="av-fold"><summary>流式响应怎么回来</summary><div class="av-fold-body">增量 token 边到边拼：先 thinking 块，再 text 块，最后 toolCall 块；拼完整条 assistant 消息才追加进历史。<code>stopReason</code> 决定循环走向。</div></details>
      </div>
      <div class="av-down"><span class="av-alabel">解析 blocks</span></div>
      <div class="av-stage av-node k-dec">
        <div class="av-name">判断 stopReason</div>
        <div class="av-sub">有 toolCall → 继续；没有 → 本轮结束，输出文本</div>
      </div>
      <div class="av-down is-green"><span class="av-alabel">并行执行</span></div>
      <div class="av-stage av-node k-tool">
        <div class="av-name">工具执行器<span class="av-pi">bash-executor · output-guard</span></div>
        <div class="av-sub">权限确认 → 执行 → 截断输出；失败也照常返回（isError）</div>
        <details class="av-fold"><summary>每个工具长什么样</summary><div class="av-fold-body">三件套：JSON Schema（给模型）、执行函数（给循环）、使用说明（进 system prompt）。read / bash / edit / write 四个就够干活。</div></details>
      </div>
      <div class="av-down"><span class="av-alabel">追加消息</span></div>
      <div class="av-stage av-node k-data">
        <div class="av-name">消息数组 + JSONL 落盘<span class="av-pi">session-manager</span></div>
        <div class="av-sub">toolResult 逐条 append；逼近上下文窗口时触发 compaction</div>
      </div>
      <div class="av-rail"><span class="av-rlabel">TOOL RESULT 回环</span></div>
    </div>
  </div>
  <div class="av-foot">蓝 = 模型边界，绿 = 工具边界；事件总线在每一站旁路发出事件，前端只听不做。</div>
</div>

教学版几十行就能写出来（下面这段是我按同样的结构写的简化版）：

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

而 pi 的真实实现分布在三个层次上：外层的 `agent-session.js`（会话编排：重试、压缩、扩展事件）、中间的 `pi-agent-core` 包（Agent 类和真正的循环 `runLoop`）、以及底层的 `pi-ai`（流式 HTTP 与协议适配）。先看最外层的骨架——`_runAgentPrompt` 先 `prompt()` 起一轮，然后靠一个"善后函数"的返回值决定要不要 `continue()`：

```typescript
async _runAgentPrompt(messages) {
    this._isAgentRunActive = true;
    try {
        await this.agent.prompt(messages);
        while (await this._handlePostAgentRun()) {
            await this.agent.continue();
        }
    } finally {
        this._systemPromptOverride = undefined;
        this._flushPendingBashMessages();
        await this._emitAgentSettled();
    }
}
```

`_handlePostAgentRun` 是外层的"方向盘"，按优先级处理四种情况：可重试的错误、重试次数耗尽、需要压缩、agent 队列里还有排队的消息：

```typescript
async _handlePostAgentRun() {
    const msg = this._lastAssistantMessage;
    this._lastAssistantMessage = undefined;
    if (!msg) return false;

    if (this._isRetryableError(msg) && (await this._prepareRetry(msg)))
        return true;

    if (msg.stopReason === "error" && this._retryAttempt > 0) {
        this._emit({ type: "auto_retry_end", success: false,
                     attempt: this._retryAttempt,
                     finalError: msg.errorMessage });
        this._retryAttempt = 0;
    }

    if (await this._checkCompaction(msg))
        return true;

    return this.agent.hasQueuedMessages();
}
```

中间层 `pi-agent-core` 才是循环本体。`Agent.prompt()` 只做归一化和启动，真正的引擎是 `runAgentLoop` → `runLoop`；`continue()` 在最后一条消息是 assistant 时优先消费 steering/follow-up 队列。整个引擎的心脏（内层 while 循环）长这样，每一行都值得对着图看：

```javascript
while (hasMoreToolCalls || pendingMessages.length > 0) {
    if (!firstTurn) { await emit({ type: "turn_start" }); }
    else { firstTurn = false; }

    // 注入排队中的 steering 消息（用户在模型干活时说的话）
    if (pendingMessages.length > 0) {
        for (const message of pendingMessages) {
            await emit({ type: "message_start", message });
            await emit({ type: "message_end", message });
            currentContext.messages.push(message);
            newMessages.push(message);
        }
        pendingMessages = [];
    }

    // 流式拿一条 assistant 回复（message_start/update/end 事件都从这里发）
    const message = await streamAssistantResponse(
        currentContext, config, signal, emit, streamFunction);
    newMessages.push(message);

    // 错误/中断：turn 收尾、整个 agent 结束
    if (message.stopReason === "error" || message.stopReason === "aborted") {
        await emit({ type: "turn_end", message, toolResults: [] });
        await emit({ type: "agent_end", messages: newMessages });
        return;
    }

    const toolCalls = message.content.filter((c) => c.type === "toolCall");
    const toolResults = [];
    hasMoreToolCalls = false;
    if (toolCalls.length > 0) {
        const executedToolBatch = message.stopReason === "length"
            ? await failToolCallsFromTruncatedMessage(toolCalls, emit)
            : await executeToolCalls(currentContext, message, config, signal, emit);
        toolResults.push(...executedToolBatch.messages);
        hasMoreToolCalls = !executedToolBatch.terminate;   // 决定还要不要再来一圈
        for (const result of toolResults) {
            currentContext.messages.push(result);
            newMessages.push(result);
        }
    }

    await emit({ type: "turn_end", message, toolResults });
    // ...prepareNextTurn / shouldStopAfterTurn 钩子...

    // turn 间隙再捞一次 steering（就是这里让"半路插话"成为可能）
    pendingMessages = (await config.getSteeringMessages?.()) || [];
}
```

要澄清一个我早先版本的错误判断，也是这张图最重要的修正：**pi 的工具调用默认是并行的**，不是串行。`executeToolCalls` 内部有一个明确的分岔——只有配置指定 `toolExecution: "sequential"`、或这批调用里存在标记了 `executionMode === "sequential"` 的工具时才走串行路径，否则默认 `Promise.all` 并行，而且并行完成后**按 assistant 消息里 toolCall 的原始顺序**回填结果（`orderedFinalizedCalls`），保证 tool_use/tool_result 配对顺序稳定：

```javascript
const hasSequentialToolCall = toolCalls.some((tc) =>
    currentContext.tools?.find((t) => t.name === tc.name)
        ?.executionMode === "sequential");
if (config.toolExecution === "sequential" || hasSequentialToolCall) {
    return executeToolCallsSequential(currentContext, assistantMessage,
                                      toolCalls, config, signal, emit);
}
return executeToolCallsParallel(currentContext, assistantMessage,
                                toolCalls, config, signal, emit);
```

```javascript
// 并行执行，但结果按 toolCall 原始顺序回填
const orderedFinalizedCalls = await Promise.all(
    finalizedCalls.map((entry) =>
        typeof entry === "function" ? entry() : Promise.resolve(entry)));
const messages = [];
for (const finalized of orderedFinalizedCalls) {
    const toolResultMessage = createToolResultMessage(finalized);
    await emitToolResultMessage(toolResultMessage, emit);
    messages.push(toolResultMessage);
}
```

abort（ESC 中断）的实现位置也值得注意：内层 while 本身**不检查** `signal.aborted`，signal 一路传给 `streamAssistantResponse`（打断流式请求）和工具执行器；工具准备阶段每次 `beforeToolCall` 钩子回来都查一次，串行路径每个工具跑完查一次。中断不是"循环顶部的 if"，而是"每个 await 点上的合作式检查"。

上面这些代码串起来就是下面两张图。第一张按抽象层拆：Agent 会话层（队列与生命周期）叠在 Turn 循环层上，Turn 层又叠在 Message 流式层和 Tool 执行层上——右侧的层按钮可以单独点亮某一层，其余层会变暗但连线仍在，方便看清层与层怎么咬合：

<div class="archviz">
  <div class="av-head"><span class="av-tag">架构图</span><span class="av-title">主循环分层状态机：pi-agent-core 的四层结构（点右侧按钮聚焦某一层）</span></div>
  <div class="av-body">
    <div class="av2">
      <div class="av2-main">
        <div class="av2-lane" data-av2-lane="agent">
          <div class="av2-lane-head"><span class="av2-lane-tag">L1 Agent 会话层</span><span class="av2-lane-sub">agent-session.js · Agent 类：一次用户提交到 agent_settled</span></div>
          <div class="av2-node" data-av2-layer="agent">
            <div class="av-name">prompt() / continue()</div>
            <div class="av-sub">prompt 归一化输入并启动；continue 在 assistant 结尾时优先 drain 队列</div>
            <details class="av-fold"><summary>continue() 的队列优先级</summary><div class="av-fold-body"><pre>async continue() {
    if (this.activeRun) throw new Error("Agent is already processing...");
    const lastMessage = this._state.messages[
        this._state.messages.length - 1];
    if (lastMessage.role === "assistant") {
        const queuedSteering = this.steeringQueue.drain();
        if (queuedSteering.length > 0) {
            await this.runPromptMessages(queuedSteering,
                { skipInitialSteeringPoll: true });
            return;
        }
        const queuedFollowUps = this.followUpQueue.drain();
        if (queuedFollowUps.length > 0) {
            await this.runPromptMessages(queuedFollowUps);
            return;
        }
        throw new Error("Cannot continue from message role: assistant");
    }
    await this.runContinuation();
}</pre>注意 <code>skipInitialSteeringPoll: true</code>——刚 drain 过就别在循环开头再捞一次，避免同一条消息被注入两遍。</div></details>
          </div>
          <div class="av-down"></div>
          <div class="av2-node" data-av2-layer="agent">
            <div class="av-name">_handlePostAgentRun（外层方向盘）</div>
            <div class="av-sub">重试 → 压缩 → 队列检查，返回 false 才真正停</div>
          </div>
        </div>
        <div class="av2-lane" data-av2-lane="turn">
          <div class="av2-lane-head"><span class="av2-lane-tag">L2 Turn 循环层</span><span class="av2-lane-sub">agent-loop.js · runLoop：一次 LLM 调用 + 它的工具批次 = 一个 turn</span></div>
          <div class="av2-node" data-av2-layer="turn">
            <div class="av-name">while (hasMoreToolCalls || pending)</div>
            <div class="av-sub">turn_start → 流式回复 → 工具批次 → turn_end → 捞 steering → 循环</div>
            <details class="av-fold"><summary>内层循环骨架</summary><div class="av-fold-body"><pre>while (hasMoreToolCalls || pendingMessages.length > 0) {
    if (!firstTurn) await emit({ type: "turn_start" });
    // 注入 steering → streamAssistantResponse →
    // stopReason 分支 → executeToolCalls → turn_end →
    pendingMessages = (await config
        .getSteeringMessages?.()) || [];
}</pre>退出条件是"没有更多工具调用且没有 pending steering"，退出后才进入外层的 follow-up 检查。</div></details>
          </div>
          <div class="av-down"></div>
          <div class="av2-node" data-av2-layer="turn">
            <div class="av-name">三个 agent_end 出口</div>
            <div class="av-sub">error/aborted 立即结束 · shouldStopAfterTurn 钩子叫停 · follow-up 耗尽自然退出</div>
          </div>
        </div>
        <div class="av2-lane" data-av2-lane="msg">
          <div class="av2-lane-head"><span class="av2-lane-tag">L3 Message 流式层</span><span class="av2-lane-sub">streamAssistantResponse：一条 assistant 消息的诞生</span></div>
          <div class="av2-node" data-av2-layer="msg">
            <div class="av-name">streamAssistantResponse</div>
            <div class="av-sub">消费 pi-ai 的 AssistantMessageEvent 流：start → text_delta / thinking_delta / toolcall_delta → done</div>
            <details class="av-fold"><summary>为什么这层没有循环</summary><div class="av-fold-body">它只是把流事件转成 <code>message_start / message_update / message_end</code> 转发出去并拼出最终 AssistantMessage。循环属于上层；这层是纯翻译。</div></details>
          </div>
        </div>
        <div class="av2-lane" data-av2-lane="tool">
          <div class="av2-lane-head"><span class="av2-lane-tag">L4 Tool 执行层</span><span class="av2-lane-sub">executeToolCalls：一个工具批次的两种执行策略</span></div>
          <div class="av2-node" data-av2-layer="tool">
            <div class="av-name">并行（默认）vs 串行（显式）</div>
            <div class="av-sub">Promise.all 并行执行，按 toolCall 原始顺序回填结果</div>
            <details class="av-fold"><summary>策略分岔代码</summary><div class="av-fold-body"><pre>const hasSequentialToolCall = toolCalls.some((tc) =>
    currentContext.tools?.find((t) => t.name === tc.name)
        ?.executionMode === "sequential");
if (config.toolExecution === "sequential" ||
    hasSequentialToolCall) {
    return executeToolCallsSequential(...);
}
return executeToolCallsParallel(...);</pre>并行版本里 <code>finalizedCalls.map(entry =&gt; entry())</code> 同时启动全部执行，<code>Promise.all</code> 收齐后按原顺序生成 toolResult 消息。串行路径每个工具跑完检查一次 <code>signal.aborted</code>，可随时停。</div></details>
          </div>
          <div class="av-down"></div>
          <div class="av2-node" data-av2-layer="tool">
            <div class="av-name">beforeToolCall 拦截点</div>
            <div class="av-sub">每个工具执行前过一遍扩展钩子（权限确认就挂这里）；钩子返回后立即查 abort</div>
          </div>
        </div>
      </div>
      <div class="av2-rail">
        <div class="av2-rail-title">层聚焦</div>
        <button type="button" class="av2-lbtn" data-av2-layer="agent">L1 会话</button>
        <button type="button" class="av2-lbtn" data-av2-layer="turn">L2 循环</button>
        <button type="button" class="av2-lbtn" data-av2-layer="msg">L3 流式</button>
        <button type="button" class="av2-lbtn" data-av2-layer="tool">L4 工具</button>
      </div>
    </div>
  </div>
  <div class="av-foot">层与层靠 emit() 事件和 await 调用串起来：上层 await 下层的返回值，下层 emit 事件给上层的订阅者。再点一次按钮取消聚焦。</div>
</div>

第二张图按"目的"演进：假如你只想做消息问答，引擎只需要什么？加上工具调用要多哪些件？错误处理和 steering 又是叠在哪里的？每个阶段的虚线框就是相对上一阶段的新增件：

<div class="archviz">
  <div class="av-head"><span class="av-tag">架构图</span><span class="av-title">按目的演进：从纯问答到完整 agent，每步加什么</span></div>
  <div class="av-body">
    <div class="av3-stages">
      <button type="button" class="av3-tab" data-av3-stage="qa">① 纯消息问答</button>
      <button type="button" class="av3-tab" data-av3-stage="tools">② ＋工具调用</button>
      <button type="button" class="av3-tab" data-av3-stage="full">③ ＋错误处理 · steering · 压缩</button>
    </div>

    <div class="av3-pane" data-av3-stage="qa">
      <div class="av3-note">只做问答：一个 turn 就够——发出去、流式收回、结束。连 while 循环都可以省掉，因为 stopReason 永远是 stop。</div>
      <div class="av-flow">
        <div class="av-stage av-node k-core">
          <div class="av-name">streamAssistantResponse</div>
          <div class="av-sub">唯一必需的部件：拼 system + messages，消费事件流，返回 AssistantMessage</div>
        </div>
        <div class="av-down"></div>
        <div class="av-stage av-node k-end">
          <div class="av-name">stopReason === "stop" → 结束</div>
          <div class="av-sub">emit turn_end / agent_end，把消息 push 进历史，完事</div>
        </div>
      </div>
      <details class="av-fold"><summary>这一步的最小代码</summary><div class="av-fold-body"><pre>const message = await streamAssistantResponse(
    context, config, signal, emit, streamFn);
newMessages.push(message);
// 没有 toolCall → hasMoreToolCalls = false
// → while 条件为假，循环根本不转</pre></div></details>
    </div>

    <div class="av3-pane" data-av3-stage="tools">
      <div class="av3-note">加工具调用：while 循环开始真正干活。新增三件——toolCall 过滤、executeToolCalls（默认并行、顺序回填）、结果回填进上下文。</div>
      <div class="av-flow">
        <div class="av-stage av-node k-core">
          <div class="av-name">streamAssistantResponse</div>
          <div class="av-sub">同①，但现在 stopReason 可能是 toolUse</div>
        </div>
        <div class="av-down is-accent"><span class="av-alabel">toolUse</span></div>
        <div class="av-stage av-node av3-delta">
          <div class="av-name">filter(toolCall) + executeToolCalls</div>
          <div class="av-sub">并行 Promise.all；sequential 工具时走串行路径</div>
          <details class="av-fold"><summary>新增的核心几行</summary><div class="av-fold-body"><pre>const toolCalls = message.content
    .filter((c) => c.type === "toolCall");
const executedToolBatch = await executeToolCalls(
    currentContext, message, config, signal, emit);
hasMoreToolCalls = !executedToolBatch.terminate;
for (const result of executedToolBatch.messages) {
    currentContext.messages.push(result);
    newMessages.push(result);
}</pre><code>terminate</code> 标志位是关键：某个工具可以宣告"终止整个 agent"（比如自定义的 exit 工具），循环就此收敛。</div></details>
        </div>
        <div class="av-down is-green"><span class="av-alabel">结果回填</span></div>
        <div class="av-stage av-node k-data">
          <div class="av-name">messages + toolResults</div>
          <div class="av-sub">下一圈 while：带着工具结果的上下文再调一次 LLM</div>
        </div>
        <div class="av-rail"><span class="av-rlabel">TOOL RESULT 回环</span></div>
      </div>
    </div>

    <div class="av3-pane" data-av3-stage="full">
      <div class="av3-note">加错误处理、steering、压缩：全部是在②的骨架上"加挂件"，循环本体一行不改。错误处理加在 stopReason 分支，steering 加在 turn 间隙，压缩和重试加在最外层。</div>
      <div class="av-layers">
        <div class="av-layer l-core">
          <div class="av-l-head"><span class="av-l-name">外层挂件</span><span class="av-badge">＋新增</span></div>
          <div class="av-l-desc">_handlePostAgentRun：可重试错误 → _prepareRetry（2s/4s/8s 退避）；_checkCompaction（阈值触发摘要）；hasQueuedMessages（follow-up 续跑）。</div>
        </div>
        <div class="av-l-arrow"><span class="av-alabel">continue()</span></div>
        <div class="av-layer l-bus">
          <div class="av-l-head"><span class="av-l-name">turn 间隙挂件</span><span class="av-badge">＋新增</span></div>
          <div class="av-l-desc">turn_end 之后 <code>pendingMessages = getSteeringMessages()</code>——用户半路插的话在这里进上下文，不打断当前工具批次。</div>
          <details class="av-fold"><summary>steering 的完整路径</summary><div class="av-fold-body">入队：<code>AgentSession._queueSteer → agent.steer() → steeringQueue.enqueue()</code>。消费：runLoop 每个 turn 结束时 <code>drain()</code>，在下个 turn 开头作为 user 消息 emit 并 push。UI 侧：_steeringMessages 数组跟踪"还没送达的"消息，message_start 事件确认送达后移除。</div></details>
        </div>
        <div class="av-l-arrow"><span class="av-alabel">进入下个 turn 前</span></div>
        <div class="av-layer l-infra">
          <div class="av-l-head"><span class="av-l-name">stopReason 分支挂件</span><span class="av-badge">＋新增</span></div>
          <div class="av-l-desc">error/aborted → 立即 turn_end + agent_end（内层返回）；length（截断）→ <code>failToolCallsFromTruncatedMessage</code> 把残缺的 toolCall 全部转成错误结果，不执行。</div>
          <details class="av-fold"><summary>为什么 length 要特殊处理</summary><div class="av-fold-body">输出被 max_tokens 截断时，toolCall 的 JSON 可能只剩半截。pi 不猜参数，直接把整批 toolCall 标记为失败结果喂回去，让模型看到"你的调用被截断了"自己重发。</div></details>
        </div>
      </div>
    </div>
  </div>
  <div class="av-foot">演进的关键认识：①→②动的是循环条件（toolResult 驱动回环），②→③动的全是挂载点——pi 把可扩展性做成了"在固定位置挂钩子"，而不是改循环本身。</div>
</div>

朴素的同步实现能跑，但很快你会发现什么都做不了：想按 ESC 中断？想边生成边流式显示？想在模型跑工具的半路上插一句话？这些都需要把"发生了一件事"和"如何呈现这件事"解耦。pi 的解法是事件总线（`event-bus.js`）——它的实现朴素到只有几十行：直接包了一个 Node.js 的 `EventEmitter`，`emit` 同步分发，唯一加的料是把每个 handler 包进 try/catch，保证一个订阅者抛错不会炸掉整个进程：

```javascript
on: (channel, handler) => {
    const safeHandler = async (data) => {
        try {
            await handler(data);
        } catch (err) {
            console.error(`Event handler error (${channel}):`, err);
        }
    };
    emitter.on(channel, safeHandler);
    return () => emitter.off(channel, safeHandler);   // 返回退订函数
},
```

事件名没有枚举约束，就是字符串 channel；但生命周期事件的命名是稳定的：`agent_start` →（`turn_start` → `message_start`/`message_update`/`message_end` → `tool_execution_start`/`tool_execution_end` → `turn_end`）× N → `agent_end` → `agent_settled`。TUI、日志、扩展系统全部订阅这一条流，所以同一个核心能配四种完全不同的前端（交互式 TUI、`pi -p` 脚本打印、RPC 进程集成、SDK 嵌入），核心一行不改。

上一节那条真实的 bash 报错记录其实展示了同一个哲学——杀掉一个跑了一半的任务常常比让它带着错误信息跑完更贵，把纠错机会留给模型自己往往更划算。

## 三、Provider 层：挡住模型 API 差异的墙

看上面 assistant 消息里的 `"api": "openai-completions", "provider": "ollama-local", "model": "glm-5.2:cloud"` 这几个字段——同一套统一消息格式，跑在 OpenAI 协议上、经由 ollama 代理接到云模型。这就是 Provider 层存在的意义：主循环只认统一格式，provider 负责"翻译出去"（统一格式 → 对方 API 请求）和"翻译回来"（流式响应 → 统一格式的 assistant 消息）。

pi 的这层不在主包里，而是拆成了独立依赖 `@earendil-works/pi-ai`，内部再分三层：API 层（每个线上协议一个适配器模块，各自导出统一签名的 `stream`/`streamSimple`）、Provider 层（auth + baseUrl + 模型目录，把调用委托给 API 适配器）、Model 层（一个值对象决定自己走哪个适配器）。支持的协议列表本身就是一份业界现状清单：

```typescript
export type KnownApi = "openai-completions" | "mistral-conversations"
  | "openai-responses" | "azure-openai-responses" | "openai-codex-responses"
  | "anthropic-messages" | "bedrock-converse-stream"
  | "google-generative-ai" | "google-vertex" | "pi-messages";
```

`stream()` 的签名是"同步返回一个事件流对象、内部异步推事件"——调用方拿到 `AssistantMessageEventStream` 就能立刻开始渲染，token 到一点拼一点。流上的事件协议是所有适配器共享的：先 `start`，再按 `contentIndex` 发块级的 `text_start`/`text_delta`/`text_end`、`thinking_*`、`toolcall_*`，终态只能是 `done` 或 `error`。这个协议就是 TUI 能逐字渲染、又不必关心底下是哪家模型的原因。

统一消息格式本身（`pi-ai/types.d.ts`，节选）长这样，注意 `thinkingSignature` 这种字段——它存 Anthropic 的加密思考签名，回放历史时必须原样带回，否则 API 会拒绝：

```typescript
export interface ThinkingContent {
  type: "thinking"; thinking: string;
  thinkingSignature?: string; redacted?: boolean;
}
export interface ToolCall {
  type: "toolCall"; id: string; name: string;
  arguments: Record<string, any>; thoughtSignature?: string;
}
export interface AssistantMessage {
  role: "assistant";
  content: (TextContent | ThinkingContent | ToolCall)[];
  api: Api; provider: ProviderId; model: string;
  usage: Usage; stopReason: StopReason; timestamp: number;
}
export type StopReason = "pending" | "stop" | "length" | "toolUse"
                       | "error" | "aborted" | "deferred";
```

往下看两个主流协议各自怎么适配的，这两段是理解"翻译层到底在翻什么"的关键。

**OpenAI chat.completions 方向**。请求组装时工具定义转成 `{type: "function", function: {name, description, parameters, strict}}` 数组，`strict` 字段只在对方支持时才带（"Some reject unknown fields"——pi 源码里的原注释，兼容性防御无处不在）。流式回来时最难的是 `delta.tool_calls` 的聚合：OpenAI 把一次工具调用拆成多个增量片段发过来，pi 用"index 优先、id 兜底"的双重索引把它们拼回块：

```javascript
const toolCallBlocksByIndex = new Map();  // key: toolCall.index
const toolCallBlocksById   = new Map();   // key: toolCall.id

let block = streamIndex !== undefined
    ? toolCallBlocksByIndex.get(streamIndex) : undefined;
if (!block && toolCall.id) block = toolCallBlocksById.get(toolCall.id);
if (!block) { block = { type: "toolCall", id: toolCall.id || "", name,
                        arguments: {}, partialArgs: "", streamIndex };
              blocks.push(block); }

// 参数是流式 JSON 片段，边拼边做增量解析
if (toolCall.function?.arguments) {
    block.partialArgs = (block.partialArgs ?? "") + toolCall.function.arguments;
    block.arguments = parseStreamingJson(block.partialArgs);
}
```

为什么需要双重索引：不是所有实现都老老实实填 `index`，有些代理只给 `id`，有些只给 `index`。块结束时 `finishBlock` 会做最终解析并 `delete block.partialArgs`——会话文件里只留干净的 `arguments`，流式期间的脚手架字段全部拆掉。

**Anthropic Messages 方向**。映射规则里最有代表性的是 tool_result：pi 内部每条工具结果是独立的 `role: "toolResult"` 消息，而 Anthropic 协议要求工具结果必须作为 `user` 角色消息里的 content block 出现，所以适配器要把连续的 toolResult 合并成一条 user 消息：

```javascript
// 内部: [assistant(tool_use), toolResult, toolResult]
// 协议: [assistant(content: [tool_use × 2]),
//        user(content: [{type:"tool_result", tool_use_id, content, is_error} × 2])]
```

还有一类映射是缓存打点。Anthropic 的 prompt caching 靠在消息里插 `cache_control` 标记，pi 的打点位置是精心选的：system prompt 第一块、最后一个工具定义、最后一条 user 消息的最后一个 block——正好是"稳定前缀"的三个端点。而 OpenAI 方向不用手动打点，靠 `prompt_cache_key`（会话 ID）让服务端自动关联缓存。thinking 块的映射还有个细节：没有 signature 的 thinking（比如中断后的残块）会被降级成普通 text，因为 Anthropic 拒绝无签名的 thinking 回放。

模型注册表是这层的另一半（`pi-ai/providers/data/*.json`，35 家厂商，自动生成）。每条登记长这样，主循环靠 `contextWindow` 决定何时压缩，靠 `cost` 五元组算钱：

```json
"claude-haiku-4-5": {
  "id": "claude-haiku-4-5", "api": "anthropic-messages",
  "provider": "anthropic", "baseUrl": "https://api.anthropic.com",
  "reasoning": true, "input": ["text", "image"],
  "cost": { "input": 1, "output": 5, "cacheRead": 0.1, "cacheWrite": 1.25 },
  "contextWindow": 200000, "maxTokens": 64000
}
```

个性差异不写死在代码里，而是塞进每个模型的 `compat` 字段（20 多项开关：`supportsStore`、`maxTokensField` 用 `max_tokens` 还是 `max_completion_tokens`、thinking 格式十一种变体……），按 provider 名和 baseUrl 关键字自动探测。这是"支持得太泛会陷入兼容性泥潭"的一个解法：协议只有几种，怪癖全部数据化。

最后是重试，pi 做了两层，参数都值得抄。HTTP 层（`provider-retry.js`，注释明说"镜像 OpenAI/Anthropic SDK 的 pinned 策略"）：408/409/429/5xx 和网络错误可重试，退避是 `min(0.5 × 2^n, 8)` 秒再乘 `(1 - random() × 0.25)` 的抖动（0.5s/1s/2s/4s/8s 封顶）；服务器通过 `Retry-After` 要求等超过 60 秒时直接失败上抛，不无限耗着。agent 层（`retryAssistantCall`）：对整条失败的 assistant 消息重试，默认 3 次、2s/4s/8s 退避，用两条大正则分类——配额类错误（`insufficient_quota`、`billing`、`available balance`……）绝不重试，过载类（`overloaded`、`429`、`stream ended before message_stop`……）重试。还有个实现细节：pi 显式传 `maxRetries: 0` 关掉官方 SDK 的内建重试，因为它自己的退避 sleep 能被 AbortSignal 打断，SDK 的不能——用户按 ESC 时重试等待必须立刻让路。

## 四、System Prompt：模型"是谁"

pi 的 `system-prompt.js` 只有 109 行，拼装结构是固定的四段：基础指令（"You are an expert coding assistant operating inside pi, a coding agent harness..."）+ 工具清单（每个工具的 description 拼成 `- read: ...` 列表，没有 snippet 的自定义工具不列）+ 使用守则（"Be concise"、"Show file paths clearly"，以及条件性的"用 bash 做 ls/rg/find"——只在没装那三个专用工具时才出现）+ 一段"问 pi 自身用法时读哪个文档"的路由说明。

项目级指令的注入格式是这样的（`resource-loader.js` 会按 `AGENTS.override.md > AGENTS.md > CLAUDE.md` 的优先级，从工作目录逐级向上收集）：

```text
<project_context>

Project-specific instructions and guidelines:

<project_instructions path="/path/to/AGENTS.md">
...文件原文...
</project_instructions>

</project_context>
```

给上下文块套上明确的 XML 边界是个务实的小技巧：模型更容易把它当成"参考资料"而不是"必须立刻执行的指令"，一定程度上抑制文件内容里的提示注入。skills 的注入同理，用 `<available_skills><skill><name>` 的结构列出名字和描述，模型需要时自己用 read 去加载全文——按需注入而不是全量塞进来。

有意思的是 pi 在这里反而不搞模板系统：没有 `{{cwd}}` 占位符，工作目录就是一行纯字符串拼接 `prompt += "\nCurrent working directory: " + cwd.replace(/\\/g, "/")`（Windows 反斜杠归一化）。真正的缓存考量在 Provider 层解决（上一节的 `prompt_cache_key` 和 `cache_control` 打点），system prompt 只要内容确定就行。

一个很实际的考量仍然成立：system prompt 和对话前缀逐字节稳定，才能命中 provider 的 prompt caching，长会话能省大笔费用和延迟。pi 的做法值得注意——它把"会变的东西"（项目上下文、skills 列表）都放在 prompt 尾部拼接，"不变的基础指令"始终在头部，缓存前缀的断裂面被压到最小。

## 五、工具层：四个工具就能干活

pi 内置七个工具：`read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`。真正不可或缺的是前四个，后三个是便利性优化（省 token、输出更结构化）。每个工具三件套：TypeBox 写的 JSON Schema（给模型）、执行函数（给循环）、description 文案（进 system prompt 的工具清单）。description 不是装饰，是运行时行为的一部分——工具描述里直接引用了截断常量，模型因此"知道"输出会被截到多长、该什么时候主动分段。

**read 的截断与续读**。常量在 `truncate.js` 里：`DEFAULT_MAX_LINES = 2000` 行、`DEFAULT_MAX_BYTES = 50 * 1024`（50KB），先到者为准。截断不是默默砍掉就完事，而是给模型一个可执行的下一步——这是工具设计里非常值得学的一笔：

```javascript
if (truncation.truncatedBy === "lines") {
    outputText += `\n\n[Showing lines ${startLineDisplay}-${endLineDisplay} ` +
        `of ${totalFileLines}. Use offset=${nextOffset} to continue.]`;
} else {
    outputText += `\n\n[Showing lines ... (${formatSize(DEFAULT_MAX_BYTES)} limit). ` +
        `Use offset=${nextOffset} to continue.]`;
}
```

更极端的边界也有兜底：单行就超过 50KB 时（比如 minified JS），read 会直接放弃并指路——"Use bash: sed -n '120p' file | head -c 51200"。工具没有说"失败了，你自己想办法"，而是每次拒绝都附带替代方案，模型循环才不会卡死。

**bash 的超时与流式回传**。超时参数是可选的（schema 里明写 "no default timeout"），实现是 `setTimeout` 到点杀整棵进程树——`spawn` 时用 `detached: true` 建独立进程组就是为了这一刻能连带子孙进程一起杀，而不是只杀外壳留下孤儿：

```javascript
if (timeoutMs !== undefined) {
    timeoutHandle = setTimeout(() => {
        timedOut = true;
        if (child.pid) killProcessTree(child.pid);
    }, timeoutMs);
}
// 进程退出后检查 timedOut 标志
if (timedOut) throw new Error(`timeout:${timeout}`);
```

输出回传走 `OutputAccumulator` + 100ms 节流：stdout/stderr 的每个 data 块先进滚动缓冲区，凑够 100ms 才给 TUI 发一次快照（`BASH_UPDATE_THROTTLE_MS = 100`），超过 50KB 自动开始写临时文件、结束时把完整输出路径附在结果里。这里还有个容易忽略的细节——pi 用 `getShellConfig(options?.shellPath)` 决定用哪个 shell，我本机就在 `~/.pi/agent/settings.json` 里配了 `shellPath` 指向 Git Bash，Windows 默认 shell 跑不了多少正经命令，这个配置点是 Windows 用户的第一个必改项。

**edit 的匹配与容错**。参数 schema 的原文把约束写得明明白白：

```typescript
const replaceEditSchema = Type.Object({
    oldText: Type.String({
        description: "Exact text for one targeted replacement. It must be " +
            "unique in the original file and must not overlap with any other " +
            "edits[].oldText in the same call.",
    }),
    newText: Type.String({ description: "Replacement text for this targeted edit." }),
});
```

`edits` 数组一次可以带多组替换，但都对着"原始文件"匹配而不是增量应用——两处改动挨得近就要求合并成一条。还有一个专门伺候模型的预处理函数，它处理的是真实世界里模型不守规矩的情况（源码注释点名了 Opus 4.6 和 GLM-5.1）：

```typescript
function prepareEditArguments(input) {
    const args = input;
    // Some models (Opus 4.6, GLM-5.1) send edits as a JSON string instead of an array
    if (typeof args.edits === "string") {
        try {
            const parsed = JSON.parse(args.edits);
            if (Array.isArray(parsed)) args.edits = parsed;
        } catch { }
    }
    // 旧格式 top-level oldText/newText 兼容
    ...
}
```

要澄清一个流传很广的说法：**pi 并没有实现"必须先 read 才能 edit"的强校验**。`edit.js` 的执行路径就是 access 检查 → 读文件 → `applyEditsToNormalizedContent` 应用编辑 → 写回，全程没有查询"这个文件之前 read 过没有"的状态（某些别的 agent 比如 ZCode 有这个机制，但 pi 选择靠 oldText 必须逐字符命中的约束本身来兜底——没读过文件就编不出唯一的 oldText）。它有的是另一个保护：`withFileMutationQueue(absolutePath, ...)` 把同一文件的并发变更串行化，防止两个工具调用交错写坏文件。

`edit` 的参数格式本身是个经典权衡。行号定位省 token 但模型数行号经常数错；精确字符串替换多花一点 token 换高得多的成功率。下面是真实会话里的一次 edit 调用（脱敏，节选），它在改一个第三方库的 bug，`newText` 里那段英文注释是模型在解释自己为什么这么改（PEFT 的 `inference_mode` 继承问题会导致优化器为空、训练静默失效）——工具调用的参数本身就是推理过程的载体：

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

## 六、会话管理：持久化、恢复与压缩

append-only JSONL 带来的能力链前面说过：持久化 → 恢复 → 分支（`parentId` 树从某点复制出新文件，`/fork` 出的会话头还会带 `parentSession` 字段指向源文件）。真正难的是压缩（compaction）。

pi 的自动触发条件是一个具体的公式：`contextTokens > contextWindow - reserveTokens`，其中 `reserveTokens` 默认 **16384**（给模型回复预留的空间），`keepRecentTokens` 默认 **20000**（最近一段不动、只压缩更早的部分）。压缩发生时会话文件里追加一个 `CompactionEntry`，老消息不从文件里删——它们只是"不再发给 LLM"：

```text
压缩前：
  entry:  0     1     2     3      4     5     6      7      8     9
        ┌─────┬─────┬─────┬─────┬──────┬─────┬─────┬──────┬──────┬─────┐
        │ hdr │ usr │ ass │ tool │ usr │ ass │ tool │ tool │ ass │ tool│
        └─────┴─────┴─────┴─────┴──────┴─────┴─────┴──────┴──────┴─────┘
                └────────┬───────┘ └──────────────┬──────────────┘
               被摘要的部分              保留的部分（从 firstKeptEntryId 起）

压缩后：末尾追加一个 cmp 条目；下次加载时 LLM 看到
        系统提示 + summary + 从 firstKeptEntryId 开始的消息
```

`CompactionEntry` 的结构（`session-manager.ts`）：

```typescript
interface CompactionEntry {
  type: "compaction";
  id: string; parentId: string; timestamp: number;
  summary: string;
  firstKeptEntryId: string;   // 保留消息的起点
  tokensBefore: number;       // 被替换掉的压缩前上下文量
  usage?: Usage;              // 生成摘要这次调用的开销
}
```

摘要不是"把对话总结一下"这么随意，pi 用一个结构化模板约束输出（Goal / Constraints / Progress 的 Done/In Progress/Blocked / Key Decisions / Next Steps / Critical Context），末尾还强制带上两个机器可读的清单：`<read-files>`（读过的文件路径）和 `<modified-files>`（改过的文件）——这两个清单会跨多次压缩累积传递，是模型在丢失细节后仍能"知道去哪里找"的生命线。生成摘要前，对话先被 `serializeConversation()` 拍平成 `[User]: ...` / `[Assistant tool calls]: read(path="foo.ts")` 的文本，其中工具结果截到 2000 字符。

重复压缩的边界处理很见功力：第二次压缩的摘要范围从**上一次的 `firstKeptEntryId`** 开始算，而不是从上一个压缩条目开始——这样上次幸存下来的消息这次也会被纳入摘要，不会出现"既没被摘要、又没被保留"的幽灵区间。

除了阈值触发的 compaction，还有手动 `/compact [instructions]`（可以给摘要加聚焦指令，`enabled: false` 也照样能用），以及一套独立的分支摘要机制：`/tree` 导航到另一条分支时，pi 会提议把"你正在离开的那条分支"（从旧叶子回到共同祖先的路径）总结成 `BranchSummaryEntry` 追加到新位置——三段式（找共同祖先 → 沿路径收集 → 按 token 预算从最新优先纳入）和 compaction 同构，等于把"压缩"复用成了"换脑子"。

本质都是同一个取舍：压缩保住了会话的续航，代价是细节的永久丢失，只能靠结构化摘要（尤其是文件清单和关键决策）缓解。会话文件里逐条记录的 `usage` 在这里派上第二个用场：`tokensBefore` 加上逐条 usage 就能监控 token 增长曲线，决定阈值调松还是调紧。

## 七、权限与安全：信任要分层

先说一个会颠覆直觉的事实：**pi 没有内置的 permissions/allow 规则系统，也没有沙箱**（settings.json 里根本不存在 `permissions.allow` 这类字段，官方 security.md 明说 "It is not a sandbox"）。它的安全模型比传闻的简单得多，也诚实得多——两条防线，各管一段。

第一条是**目录信任**（`trust-manager.js`）。存储文件 `~/.pi/agent/trust.json` 的结构简单到极致：`{ "规范化绝对路径": true | false }`，值只允许布尔。查找不是 glob 也不是前缀匹配，而是从当前目录**逐级向上找最近的已登记祖先**：

```javascript
let currentDir = normalizeCwd(cwd);
while (true) {
    const value = data[currentDir];
    if (value === true || value === false)
        return { path: currentDir, decision: value };
    const parentDir = dirname(currentDir);
    if (parentDir === currentDir) return null;
    currentDir = parentDir;
}
```

这个设计防的是一个具体攻击面：恶意仓库在 `.pi/` 下塞 settings、extensions、skills、SYSTEM.md，在仓库里放嘱托型的 AGENTS.md——不信任的目录里这些资源一概不加载。多进程并发写 trust.json 用 `proper-lockfile` 文件锁串行化。值得注意的边界：**AGENTS.md 这类 context 文件不受信任门控、总是加载**——因为它们只是作为"参考资料"进上下文，真正的执行通道（工具）在另一道防线上。

第二条是**工具确认，但它整个外包给了扩展系统**。`agent.beforeToolCall` 钩子在每次工具执行前触发，若任何扩展注册了 `tool_call` handler，就发出 `{type: "tool_call", toolName, toolCallId, input}` 事件；扩展返回 `{ block: true, reason: "..." }` 可以拦截，还可以原地改写 `event.input` 实现参数纠正。弹窗能力由 UI API 的 `ui.confirm(title, message)` 提供，官方示例 `permission-gate.ts` 演示的就是"拦危险命令 + 弹确认"的完整实现。换句话说，pi 核心只提供拦截点，确认策略（哪些命令要问、记住哪些答案）全部是扩展的事——这和它"功能不进核心"的一贯哲学完全一致。

第三条算半个：**输出防护靠截断而非过滤**。read/bash 的 2000 行 / 50KB 截断保护的是上下文不被撑爆；对提示注入（read 的文件内容里藏着"忽略之前的指令"），pi 的缓解就是上一节说的 XML 边界包裹 + 工具调用对用户完全可见。它不假装能防住，把最终监督权留给屏幕前的人。真要硬隔离，文档指路给 OS 级方案（容器、micro-VM）。

一个能随意执行 shell 命令和改文件的程序，安全设计不是可选项——但 pi 的答案是把"必须进核心的"压到最少（信任表 + 拦截点），其余交给可审计的扩展层。这比堆一整套 permission DSL 更容易验证正确性。

## 八、扩展机制：决定上限的取舍

pi 最有意思的取舍在这里。它的扩展系统允许 TypeScript 代码订阅事件总线、增删工具、改写 system prompt、拦截工具调用（上一节的 `tool_call` 拦截点就是给扩展用的），功能上几乎无所不能——然后它把 subagent、plan mode 这些别家做进核心的东西都留给了扩展或第三方包。理由是：核心里的每个功能都是所有用户必须背负的复杂度，而扩展里的功能只属于需要它的人。pi 的 skills 机制（把常用工作流写成 Markdown 说明书，启动时只把 name/description 以 `<available_skills>` 结构注入、模型需要时自己 read 全文）是同一哲学的延续——很多"功能"其实只是一段 prompt，根本不需要代码。

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
