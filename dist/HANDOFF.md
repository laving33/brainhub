# BrainHub 交接給 SO platform — 打包資訊

date: 2026-07-14 · from: chief · 源碼基線: git `d708407`（tools/brainhub，工作區乾淨）

## 出貨物（就這一個檔）

```
/home/aworkr/aworkr/tools/brainhub/dist/brainhub-1.6.0.tar.gz
```

| 項目 | 值 |
|---|---|
| 版本 | 1.6.0 |
| 大小 | 1,538,352 bytes（~1.5 MB） |
| 檔數 | 201 |
| SHA-256 | `80353ce9d849ba3f0cee859847da4049a0baaf48ee8202a8947f588c6b00d05e` |

## 需求（客戶端）

- **Python 3.10+，純標準庫**——引擎/CLI/viewer 零第三方依賴，解壓即用（已實測裸 python3 全流程）。
- 選配：PDF 匯出需要一支 chrome wrapper（env `BRAINHUB_CHROME_PDF` 指過去；沒有只失去 PDF 下載）。
- 選配：MCP server 給 agent 用 → `pip install ./mcp_package`（唯一依賴 `mcp>=1.0.0`）。

## 安裝（客戶端三行）

```bash
tar xzf brainhub-1.6.0.tar.gz
cd brainhub-1.6.0
python3 brainhub.py init ~/team-brain     # 完整步驟見包內 README.md
```

## 包內文件（都在 tarball 裡，客戶自足）

| 檔 | 用途 |
|---|---|
| `README.md` | 安裝/quickstart/agent 接法/white-label 配置表/維護者導覽 |
| `BRAINHUB.md` | 架構與設計契約（workspace 佈局、provenance、非目標） |
| `BRAINHUB-SCHEMA.md` | agent 面 schema 說明（init 時會複製進 workspace） |
| `LICENSE` | **每份拷貝必帶**（MIT；上游版權宣告＋aworkr.ai 並列） |
| `skills/brainhub-*` ×5 | Claude Code agent skills，客戶 symlink 進 `~/.claude/skills` 即用 |
| `tests/`（943 綠） | 維護者驗收基線：`python3 -m pytest tests/` |

## White-label（客戶換品牌，零代碼）

| 要換 | 怎麼換 |
|---|---|
| 渲染文件/PDF 上的 logo | 換 `mcp_package/brainhub_core/vendor/brand-logo.svg`，或 env `BRAINHUB_BRAND_LOGO=/path.svg` |
| viewer 的 logo | workspace 根目錄放 `logo.svg` |
| 內嵌字型 | env `BRAINHUB_BRAND_FONTS=/fonts-dir`（缺席優雅降級） |
| PDF 匯出 | env `BRAINHUB_CHROME_PDF=/path/chrome-wrapper` |
| 預設 workspace | env `BRAINHUB_HOME=/path` |

包內預設＝中性 BrainHub 標，**零 aworkr 字樣**（render 產物實測過）。

## 部署前提（一行，包內 README 已載明）

內網信任環境專用：viewer 預設 bind `127.0.0.1`，寫入端點無認證——**不可對公網開 port**。

## 重建 / 改版（SO platform 端）

```bash
cd /home/aworkr/aworkr/tools/brainhub
./scripts/make_dist.sh          # 產出 dist/brainhub-<版本>.tar.gz
```

版本號讀自 `mcp_package/pyproject.toml`。腳本內建**五道出貨閘**，任一失敗即拒出包：
① 無 `.git`（commit 訊息含內部案名，NDA）② 無 aworkr logo ③ 無 fleet 專用 hook
④ 上游身分只准在 LICENSE ⑤ **零客戶名**。閘首跑就抓過兩個真洩漏——別繞過它手動打包。

## 刻意不在包內的東西（別「補」回去）

`.git`（NDA 歷史）、`.venv`、`wire-artifact-intercept.py`（aworkr fleet 專用）、
`aworkr-logo-*.svg`（我方品牌）、`tests/test_brand_assets.py`（比對 aworkr 內部 SSOT，客戶端必失敗）。

## 驗證基線（出貨前已做，重打包後照跑）

1. 解壓樹跑測試：`python3 -m pytest tests/` → **943 passed**（無 git 環境）
2. 裸 python3 smoke：init → publish → read → search 全通
3. render 一份 md → 產物含 `BrainHub logo`、`aworkr` 出現 0 次
