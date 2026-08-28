# SaaS MCP 統合および Google ADK エージェントツール (`mcp-saas-draft`)

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [繁體中文 (台灣)](README.zh-TW.md) | [Bahasa Indonesia](README.id.md)

---

## 📌 概要
本モジュールは、企業向け SaaS ポータル（`https://mock-saas.aishprabhat.demo.altostrat.com/`）と **Google ADK (Agent Development Kit)** および **Google GenAI (Gemini)** エージェントを接続する本番対応の **Model Context Protocol (MCP)** 統合パッケージです。

2 つの稼働中 **FastMCP** Streamable HTTP マイクロサービスを直接連携します:
1. **WorkWeek HCM MCP**: 従業員プロファイル管理、リアルタイム有給・病気休暇残高、休暇申請、連絡先更新。
2. **ServiceImmediately ITSM MCP**: IT サポートチケット照会、新規インシデント作成、コメント追加、ステータス遷移。

---

## ⚡ アーキテクチャと認証に関する重要な注意事項

> [!IMPORTANT]
> **なぜ `X-MCP-Token` が必須で、標準の `Authorization` ヘッダーを送信してはならないのか:**
> - 対象の SaaS ポータルは Google Cloud インフラ上でホストされています。
> - FastMCP エンドポイント（`/work-week/mcp/` および `/service-immediately/mcp/`）は **Identity-Aware Proxy (IAP) のバイパス**が設定されています。
> - しかし、リクエストに標準の `Authorization` ヘッダーが含まれていると、**Google Frontend (GFE)** がそれをインターセプトし、Google ログイン OIDC JWT として検証しようとします。
> - その結果、`Authorization: Bearer <mcp_token>` を送信すると、GFE が `401 Invalid IAP credentials: Unable to parse JWT` エラーを返します。
> - **解決策**: トークンは必ずカスタムヘッダー **`X-MCP-Token`** 経由でのみ送信してください:
>   ```http
>   X-MCP-Token: mcp_your_token_here
>   Accept: application/json
>   ```
>   `Authorization` ヘッダーは**絶対に含めないでください**。

### エンドポイント
- **WorkWeek サーバー**: `https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/`
- **ServiceImmediately サーバー**: `https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/`
- **トランスポート方式**: Stateless Streamable HTTP (JSON-RPC 2.0)

---

## 🛠️ 利用可能な MCP ツール一覧

### 📅 WorkWeek HCM ツール (`/work-week/mcp/`)
| ツール名 | パラメータ | 説明 |
| :--- | :--- | :--- |
| `get_current_employee_id` | なし | 認証されたユーザーセッションの従業員 ID を解決します（例: `EMP-509`）。 |
| `get_employee_balances` | `employee_id` | 残りの有給休暇および病気休暇の残高（日数）を取得します。 |
| `request_time_off` | `start_date`, `end_date`, `leave_type`, `days`, `employee_id` | 休暇申請を提出します（日付形式: `YYYY-MM-DD`、休暇種別: `'Vacation'` または `'Sick'`）。 |
| `get_personal_info` | `employee_id` | 従業員の現住所および電話番号を取得します。 |
| `update_personal_info` | `address`, `phone`, `employee_id` | 住所（5文字以上）および E.164 電話番号を更新します。 |
| `get_leave_requests` | `employee_id` | 過去および現在のすべての休暇申請履歴を取得します。 |
| `cancel_leave_request` | `request_id`, `employee_id` | 申請中の休暇をキャンセルし、日数を残高に返還します。 |

### 🎫 ServiceImmediately ITSM ツール (`/service-immediately/mcp/`)
| ツール名 | パラメータ | 説明 |
| :--- | :--- | :--- |
| `list_tickets` | `employee_id` | 従業員が申請したすべてのインシデントチケットを一覧表示します。 |
| `create_ticket` | `category`, `short_description`, `priority`, `assignment_group`, `requested_by` | 新しいサポートチケットを作成します（`priority`: `'1 - Critical'`, `'2 - High'`, `'3 - Moderate'`, `'4 - Low'`）。 |
| `add_ticket_comment` | `ticket_id`, `comment`, `author` | チケットのアクティビティログにコメントを追加します。 |
| `update_ticket_status` | `ticket_id`, `status`, `resolution_notes`, `updated_by` | チケットのステータスを更新します（`New` ➔ `In Progress` ➔ `Resolved` ➔ `Closed`）。 |

---

## 🚀 クイックスタート & 手動テスト手順

### 1. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定 (任意)
デフォルトでチームのトークンが組み込まれていますが、必要に応じて上書きできます:
```bash
export SAAS_MCP_CREDENTIAL="mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"
```

### 3. 手動テストスクリプトの実行
```bash
# 対話式メニューモード
python manual_test_mcp.py

# または全テストを一括順次実行
python manual_test_mcp.py --all
```

**実環境での検証済みライブデータ:**
- 認証従業員: `EMP-509` (`Romij Employee`)
- 登録オフィス: `Singapore Office, 80 Pasir Panjang Rd, Singapore`
- 有給休暇残高: `15.0 days remaining (5.0/20.0 used)`
- チケット履歴: `INC0003359` (HR Services), `INC0003333` (Inquiry / Help)

---

## 🤖 Google ADK エージェントへの統合方法

### オプション A: Google ADK `McpToolset` の利用
```python
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

workweek_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/",
        headers={"X-MCP-Token": "mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"}
    )
)

serviceimmediately_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/",
        headers={"X-MCP-Token": "mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"}
    )
)

agent = Agent(
    name="enterprise_assistant",
    model="gemini-3.5-flash",
    instruction="WorkWeekの休暇管理およびServiceImmediatelyのITサポートチケットを処理するエージェントです。",
    tools=[workweek_mcp, serviceimmediately_mcp]
)
```

### オプション B: Google GenAI SDK (`google-genai`) の利用
```python
from google import genai
from src.adk_tools import ALL_SAAS_ADK_TOOLS

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="WorkWeekで現在の残りの有給休暇日数を教えてください。",
    config={"tools": ALL_SAAS_ADK_TOOLS, "temperature": 0.1}
)
print(response.text)
```
