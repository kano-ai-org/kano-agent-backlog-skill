# kano-agent-backlog-skill

**Local-first backlog + decision trail for agent collaboration.**  
把「聊天室裡蒸發的討論、取捨、決策」變成可追溯的工程資產，讓 agent 在寫任何 code 前先把「要做什麼、為什麼、怎麼驗收」留下來。

> Code 可以重寫；決策蒸發就真的沒了。

English version: `README.en.md`

## 這是什麼

`kano-agent-backlog-skill` 是一個 **Agent Skill bundle**（以 `SKILL.md` 為核心），用來引導/約束 agent 遵守一套「工項先行」的工作流：

- 寫 code 前先建立/更新 work item（Epic/Feature/UserStory/Task/Bug）
- 重要決策用 Worklog（append-only）或 ADR 記錄並互相連結
- 以 Ready gate 確保每張票都有最小可驗收資訊（Context/Goal/Approach/Acceptance/Risks）
- 搭配 Obsidian + Dataview，把本地檔案直接當 Dashboard（人類可介入、可 review）

此 skill 主打 **local-first**：不需要先導入 Jira / Azure Boards 才能開始有紀律地協作。

## 你為什麼會想要它

如果你遇過以下狀況，這個 skill 會有感：

- 討論完架構，過幾天已經不記得「為什麼不用另一個方案」
- agent 產出能跑，但後續維護像考古：缺少當時的脈絡與取捨
- 需求一改就全線回歸聊天室，影響面無法快速回溯
- 你想把 agent 當隊友，但你被迫當「人肉記憶體」補上下文

目標很單純：把「蒸發的上下文」變成 **可搜尋、可連結、可追溯** 的檔案系統資產。

## 你會得到什麼（已實作）

- `SKILL.md`: agent 行為規範與工作流（planning-before-coding、Ready gate、worklog 規則）
- `references/schema.md`: item types、state、命名、frontmatter 最小欄位
- `references/templates.md`: work item / ADR 模板
- `references/workflow.md`: SOP（何時建票、何時寫決策、如何收斂）
- `references/views.md`: Obsidian Dataview 查詢/視圖模式
- `scripts/backlog/`: backlog helpers (create_item, update_state, validate_ready, generate_view, test_scripts)
- `scripts/fs/`: file ops (cp_file, mv_file, rm_file, trash_item)
- `scripts/logging/`: audit logging (audit_logger, run_with_audit)

（可選）在你的專案內建立 `_kano/backlog/`，把 item、ADR、views 與工具腳本放在那裡，skill 會以此作為 system-of-record。

## 快速上手（5 分鐘看到效果）

1) 把 backlog 放進你的 repo（建議路徑）：`_kano/backlog/`
2) （可選）用 Obsidian 打開 repo，啟用 Dataview plugin
3) 開啟 `_kano/backlog/views/Dashboard.md` 或使用 `references/views.md` 的查詢建立自己的視圖
4) 在任何 code change 前，要求 agent 先依 `references/templates.md` 建一張 Task/Bug，並填滿 Ready gate
5) 討論出關鍵取捨時：在該票 Worklog 追加一行，必要時新增 ADR 並互相連結

## 建議的 backlog 結構（在你的專案內）

```text
_kano/backlog/
  _meta/                 # schema, conventions, indexes registry
  items/
    epics/<bucket>/
    features/<bucket>/
    userstories/<bucket>/
    tasks/<bucket>/
    bugs/<bucket>/
  decisions/             # ADRs
  views/                 # Obsidian Dataview dashboards / generated views
  tools/                 # optional helper scripts (state transition, view generation)
```

> bucket 以每 100 張票分桶（`0000`, `0100`, `0200`, ...），避免單一資料夾過大。

## 這個 repo 有什麼（source of truth）

- 行為規範：`SKILL.md`
- 參考文件：`references/`

如果你在找「如何實際落地的 `_kano/backlog` 範例」，請參考本 skill 的 demo host repo（或把 `references/templates.md` 直接當作初始化腳本的輸入）。


## 參考

- Agent Skill 官方概念參考（Anthropic/Claude）：https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- 本 skill 參考索引：`REFERENCE.md`（此 repo 使用多檔案 `references/` 以利按需載入）

## Roadmap（方向，不是承諾）

- 提供可重用的 `_kano/backlog` bootstrap assets（模板 + tools）以便一鍵初始化
- 更嚴謹但更輕量的 Ready gate/validator（仍保持 local-first）

## Contributing

歡迎 PR，但請遵守一個原則：**不要把它變成另一套 Jira。**  
我們的核心是「留下決策與驗收」，不是把流程變成宗教。

## License

MIT
