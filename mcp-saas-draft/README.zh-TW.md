# SaaS MCP 整合與 Google ADK 代理工具 (`mcp-saas-draft`)

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [繁體中文 (台灣)](README.zh-TW.md) | [Bahasa Indonesia](README.id.md)

---

## 📌 概述
本模組提供生產環境等級的 **Model Context Protocol (MCP)** 整合方案，用於將 **Google ADK (Agent Development Kit)** 與 **Google GenAI (Gemini)** 代理連接至企業 SaaS 入口網站（`https://mock-saas.aishprabhat.demo.altostrat.com/`）。

本套件直接對接兩個線上的 **FastMCP** Streamable HTTP 微服務：
1. **WorkWeek HCM MCP**：員工個人資料查詢、即時休假與病假餘額、請假申請及聯絡資訊更新。
2. **ServiceImmediately ITSM MCP**：IT 支援工單查詢、建立新工單、工單留言與狀態生命週期轉換。

---

## ⚡ 核心架構與身份驗證注意事項（重要！）

> [!IMPORTANT]
> **為何必須使用 `X-MCP-Token` 且絕對不能發送標準 `Authorization` 標頭：**
> - 該 SaaS 入口網站部署於 Google Cloud 基礎架構後端。
> - FastMCP 終端節點（`/work-week/mcp/` 與 `/service-immediately/mcp/`）已設定**繞過 Identity-Aware Proxy (IAP)**。
> - 但若請求中夾帶標準的 `Authorization` 標頭，**Google Frontend (GFE)** 會自動進行攔截，並嘗試將其作為 Google OIDC 登入 JWT 進行解析驗證。
> - 因此發送 `Authorization: Bearer <mcp_token>` 會導致 GFE 回傳 `401 Invalid IAP credentials: Unable to parse JWT` 錯誤。
> - **解決方案**：權杖**必須僅**透過自訂標頭 `X-MCP-Token` 傳遞：
>   ```http
>   X-MCP-Token: mcp_your_token_here
>   Accept: application/json
>   ```
>   **切勿**包含 `Authorization` 標頭。

### 伺服器終端節點（Endpoints）
- **WorkWeek 伺服器**：`https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/`
- **ServiceImmediately 伺服器**：`https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/`
- **傳輸協議**：Stateless Streamable HTTP (JSON-RPC 2.0)

---

## 🛠️ 提供之 MCP 工具清單

### 📅 WorkWeek HCM 工具 (`/work-week/mcp/`)
| 工具名稱 | 參數 | 說明 |
| :--- | :--- | :--- |
| `get_current_employee_id` | 無 | 取得目前已驗證工作階段之員工編號（例如：`EMP-509`）。 |
| `get_employee_balances` | `employee_id` | 查詢剩餘年假（Vacation）與病假（Sick）天數餘額。 |
| `request_time_off` | `start_date`, `end_date`, `leave_type`, `days`, `employee_id` | 提交請假申請（日期格式：`YYYY-MM-DD`，類別：`'Vacation'` 或 `'Sick'`）。 |
| `get_personal_info` | `employee_id` | 取得員工住址與聯絡電話。 |
| `update_personal_info` | `address`, `phone`, `employee_id` | 更新員工住址（最少 5 個字元）與 E.164 格式電話。 |
| `get_leave_requests` | `employee_id` | 查詢該員工所有請假歷史紀錄。 |
| `cancel_leave_request` | `request_id`, `employee_id` | 取消已申請之請假並返還休假天數。 |

### 🎫 ServiceImmediately ITSM 工具 (`/service-immediately/mcp/`)
| 工具名稱 | 參數 | 說明 |
| :--- | :--- | :--- |
| `list_tickets` | `employee_id` | 列出該員工提出之所有支援工單。 |
| `create_ticket` | `category`, `short_description`, `priority`, `assignment_group`, `requested_by` | 建立新支援工單（`priority`：`'1 - Critical'`, `'2 - High'`, `'3 - Moderate'`, `'4 - Low'`）。 |
| `add_ticket_comment` | `ticket_id`, `comment`, `author` | 於工單活動歷程中新增留言。 |
| `update_ticket_status` | `ticket_id`, `status`, `resolution_notes`, `updated_by` | 更新工單生命週期狀態（`New` ➔ `In Progress` ➔ `Resolved` ➔ `Closed`）。 |

---

## 🚀 快速開始與手動測試指南

### 1. 安裝相依套件
```bash
pip install -r requirements.txt
```

### 2. 設定環境變數（可選）
程式碼內已預載團隊指派之權杖，但您可依需求覆寫：
```bash
export SAAS_MCP_CREDENTIAL="mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"
```

### 3. 執行互動式手動測試指令稿
```bash
# 互動式選單模式
python manual_test_mcp.py

# 或一次執行全數測試
python manual_test_mcp.py --all
```

**線上即時驗證通過之實際資料：**
- 登入員工：`EMP-509` (`Romij Employee`)
- 辦公室地址：`Singapore Office, 80 Pasir Panjang Rd, Singapore`
- 年假餘額：`15.0 days remaining (5.0/20.0 used)`
- 現存工單：`INC0003359` (HR Services), `INC0003333` (Inquiry / Help)

---

## 🤖 Google ADK 代理整合範例

### 選項 A：使用 Google ADK `McpToolset`
```python
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

workweek_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/",
        headers={"X-MCP-Token": "mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"}
    )
)

serviceimmediately_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/",
        headers={"X-MCP-Token": "mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA"}
    )
)

agent = Agent(
    name="enterprise_assistant",
    model="gemini-3.5-flash",
    instruction="協助同仁處理 WorkWeek 請假手續與 ServiceImmediately IT 支援工單之企業助理。",
    tools=[workweek_mcp, serviceimmediately_mcp]
)
```

### 選項 B：使用 Google GenAI SDK (`google-genai`)
```python
from google import genai
from src.adk_tools import ALL_SAAS_ADK_TOOLS

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="請幫我查詢在 WorkWeek 中還有幾天年假可以使用？",
    config={"tools": ALL_SAAS_ADK_TOOLS, "temperature": 0.1}
)
print(response.text)
```
