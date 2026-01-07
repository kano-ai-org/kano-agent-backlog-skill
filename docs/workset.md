# Workset (Execution Layer)

## 概觀
Workset 提供本地「工作記憶」快取，讓 agent 能在可丟棄、本地 only 的沙盒執行細粒度工作，然後將成果 promote 回 canonical（item/ADR/worklog）。

## 關鍵鐵律
- **Cache 是可丟棄的**：`.cache/` 不入 git，隨時可重建。
- **Canonical promotion 是必須的**：決策、狀態、可共享成果必須寫回 backlog item 或 ADR，不能只留在 cache。
- **Plan mode 優先**：agent 啟動 workset 後，應先讀 `plan.md` checklist，避免 drift。

## 腳本

### 1. `workset_init.py` – 初始化工作集
```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_init.py \
  --item <id/uid/id@uidshort> \
  --agent <agent-name>
```

建立結構：
```
_kano/backlog/sandboxes/.cache/<uid>/
  meta.json          # created, agent, refreshed
  plan.md            # Plan Checklist template
  notes.md           # Notes template (mark 'Decision:' for ADR promotion)
  deliverables/      # Files to promote
```

寫入 worklog：`Workset initialized: ...`

### 2. `workset_next.py` – 顯示計劃清單
```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_next.py \
  --item <id/uid/id@uidshort>
```

從 `plan.md` 解析並顯示 checklist 項目（以 `- ` 開頭的行）。

### 3. `workset_refresh.py` – 刷新元資料時間戳
```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_refresh.py \
  --item <id/uid/id@uidshort> \
  --agent <agent-name>
```

更新 `meta.json` 的 `refreshed` timestamp，並寫入 worklog：`Workset refreshed: ...`

### 4. `workset_promote.py` – 提升可交付成果到 canonical
```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_promote.py \
  --item <id/uid/id@uidshort> \
  --agent <agent-name> \
  [--dry-run]
```

掃描 `deliverables/`，對每個檔案呼叫 `workitem_attach_artifact.py`，將檔案附加到 item 並寫入 worklog summary：`Promoted deliverables (N): ...`

## 用法流程

1. **開票**：`workitem_create.py` (Epic/Feature/Task)
2. **初始化 workset**：`workset_init.py --item <id> --agent <name>`
3. **讀計劃**：`workset_next.py --item <id>` → 取得 plan checklist
4. **工作**：在 `.cache/<uid>/` 下撰寫檔案、notes、deliverables
5. **提升**：`workset_promote.py --item <id> --agent <name>` → 附加到 artifacts + worklog
6. **可選 ADR**：若 `notes.md` 中有 `Decision:` 標記，可用 `adr init --for <uid>` 創建 ADR（未來功能）

## 自動化與審計
- 所有腳本都透過 `run_with_audit()` 執行，產生 audit log 至 `_kano/backlog/_logs/agent_tools/tool_invocations.jsonl`。
- `promote` 使用 `workitem_attach_artifact.py`，所以自動觸發儀表板刷新（如 `views.auto_refresh=true`）。

## gitignore
已加入：
```
_kano/.cache/
_kano/backlog/sandboxes/.cache/
```

## 限制與未來方向
- **next 過濾**：當前僅列出所有 checklist；可強化為僅顯示未完成項（需 checkbox 語法 `- [ ]`）。
- **Workset TTL**：可加入自動過期機制（`meta.json` + `claim_until`）。
- **ADR auto-creation**：目前僅提示；未來可自動產生 ADR stub 並寫回 frontmatter `decisions` list。

## ADR promotion heuristic

Use `workset_detect_adr.py` to scan `notes.md` for Decision: markers:

```bash
# Text output with suggestions
python skills/kano-agent-backlog-skill/scripts/backlog/workset_detect_adr.py \
  --item KABSD-FTR-0015

# JSON output for automation
python skills/kano-agent-backlog-skill/scripts/backlog/workset_detect_adr.py \
  --item KABSD-FTR-0015 --format json
```

**When Decision: detected**:
- Review the notes and extract rationale
- Create ADR (manual or via `adr_init.py` if available)
- Link ADR back to item frontmatter `decisions:` list
- Append worklog: "Created ADR <id> for decision on <topic>"

## 驗證範例
```bash
# 初始化
python skills/kano-agent-backlog-skill/scripts/backlog/workset_init.py \
  --item KABSD-FTR-0015 --agent copilot

# 列出計劃
python skills/kano-agent-backlog-skill/scripts/backlog/workset_next.py \
  --item KABSD-FTR-0015

# 創建可交付成果
echo "content" > "_kano/backlog/sandboxes/.cache/<uid>/deliverables/result.txt"

# 提升（dry-run）
python skills/kano-agent-backlog-skill/scripts/backlog/workset_promote.py \
  --item KABSD-FTR-0015 --agent copilot --dry-run

# 提升（實際）
python skills/kano-agent-backlog-skill/scripts/backlog/workset_promote.py \
  --item KABSD-FTR-0015 --agent copilot
```

## 與 Roadmap 對應
此實作對應 Epic `KABSD-EPIC-0006` 下的 Feature `KABSD-FTR-0015 (Execution Layer: Workset Cache + Promote)`。
