# SaaS MCP 연동 및 Google ADK 에이전트 도구 (`mcp-saas-draft`)

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [繁體中文 (台灣)](README.zh-TW.md) | [Bahasa Indonesia](README.id.md)

---

## 📌 개요
본 모듈은 기업용 SaaS 포털(`https://mock-saas.aishprabhat.demo.altostrat.com/`)과 **Google ADK (Agent Development Kit)** 및 **Google GenAI (Gemini)** 에이전트를 연결하는 프로덕션 레벨의 **Model Context Protocol (MCP)** 통합 패키지입니다.

두 개의 라이브 **FastMCP** Streamable HTTP 마이크로서비스를 직접 연동합니다:
1. **WorkWeek HCM MCP**: 사원 프로필 조회, 실시간 휴가/병가 잔고 조회, 휴가 신청 및 연락처 관리
2. **ServiceImmediately ITSM MCP**: IT 지원 티켓 목록 조회, 신규 티켓 생성, 댓글 추가 및 상태 변경

---

## ⚡ 핵심 아키텍처 및 인증 주의사항 (중요!)

> [!IMPORTANT]
> **왜 `X-MCP-Token`을 사용해야 하고 표준 `Authorization` 헤더를 보내면 안 될까요?**
> - SaaS 포털 도메인은 Google Cloud 인프라 뒤에 호스팅되어 있습니다.
> - FastMCP 엔드포인트(`/work-week/mcp/`, `/service-immediately/mcp/`)는 **Identity-Aware Proxy (IAP) 바이패스**가 설정되어 있습니다.
> - 하지만 요청에 표준 `Authorization` 헤더가 포함되어 있으면, **Google Frontend (GFE)**가 이를 가로채 구글 OIDC 로그인 JWT로 파싱 및 검증하려고 시도합니다.
> - 따라서 `Authorization: Bearer <mcp_token>`을 보내면 GFE가 `401 Invalid IAP credentials: Unable to parse JWT` 에러를 발생시킵니다.
> - **해결책**: 반드시 커스텀 헤더인 `X-MCP-Token`을 통해서만 토큰을 전송해야 합니다:
>   ```http
>   X-MCP-Token: mcp_your_token_here
>   Accept: application/json
>   ```
>   `Authorization` 헤더는 **절대로 포함하지 마십시오**.

### 엔드포인트 URL
- **WorkWeek 서버**: `https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/`
- **ServiceImmediately 서버**: `https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/`
- **전송 프로토콜**: Stateless Streamable HTTP (JSON-RPC 2.0)

---

## 🛠️ 제공되는 MCP 도구 목록

### 📅 WorkWeek HCM 도구 (`/work-week/mcp/`)
| 도구명 | 파라미터 | 설명 |
| :--- | :--- | :--- |
| `get_current_employee_id` | 없음 | 인증된 세션의 사원 ID를 확인합니다 (예: `EMP-509`). |
| `get_employee_balances` | `employee_id` | 잔여 휴가 및 병가 잔고(일수)를 조회합니다. |
| `request_time_off` | `start_date`, `end_date`, `leave_type`, `days`, `employee_id` | 휴가를 신청합니다 (날짜 형식: `YYYY-MM-DD`, 휴가 종류: `'Vacation'` 또는 `'Sick'`). |
| `get_personal_info` | `employee_id` | 사원의 주소 및 전화번호를 조회합니다. |
| `update_personal_info` | `address`, `phone`, `employee_id` | 주소(최소 5자) 및 E.164 전화번호를 수정합니다. |
| `get_leave_requests` | `employee_id` | 과거 및 현재의 휴가 신청 이력을 조회합니다. |
| `cancel_leave_request` | `request_id`, `employee_id` | 휴가 신청을 취소하고 잔여 일수를 복원합니다. |

### 🎫 ServiceImmediately ITSM 도구 (`/service-immediately/mcp/`)
| 도구명 | 파라미터 | 설명 |
| :--- | :--- | :--- |
| `list_tickets` | `employee_id` | 사원이 등록한 모든 인시던트 티켓 목록을 조회합니다. |
| `create_ticket` | `category`, `short_description`, `priority`, `assignment_group`, `requested_by` | 신규 지원 티켓을 생성합니다 (`priority`: `'1 - Critical'`, `'2 - High'`, `'3 - Moderate'`, `'4 - Low'`). |
| `add_ticket_comment` | `ticket_id`, `comment`, `author` | 티켓 히스토리에 댓글을 작성합니다. |
| `update_ticket_status` | `ticket_id`, `status`, `resolution_notes`, `updated_by` | 티켓 상태를 변경합니다 (`New` ➔ `In Progress` ➔ `Resolved` ➔ `Closed`). |

---

## 🚀 빠른 시작 및 수동 테스트 가이드

### 1. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정 (선택 사항)
기본값으로 팀 토큰이 내장되어 있으나, 필요 시 재지정할 수 있습니다:
```bash
export SAAS_MCP_CREDENTIAL="mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"
```

### 3. 대화형 수동 테스트 스크립트 실행
```bash
# 대화형 메뉴 모드 실행
python manual_test_mcp.py

# 또는 모든 테스트 일괄 실행
python manual_test_mcp.py --all
```

**실제 라이브 응답 검증 완료 내역:**
- 로그인 사원: `EMP-509` (`Romij Employee`)
- 등록 사무소: `Singapore Office, 80 Pasir Panjang Rd, Singapore`
- 휴가 잔고: `15.0 days remaining (5.0/20.0 used)`
- 인시던트 티켓: `INC0003359` (HR Services), `INC0003333` (Inquiry / Help)

---

## 🤖 Google ADK 에이전트 연동 방법

### 옵션 A: Google ADK `McpToolset` 사용
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
    instruction="WorkWeek 휴가 신청 및 ServiceImmediately IT 티켓을 처리하는 에이전트입니다.",
    tools=[workweek_mcp, serviceimmediately_mcp]
)
```

### 옵션 B: Google GenAI SDK (`google-genai`) 사용
```python
from google import genai
from src.adk_tools import ALL_SAAS_ADK_TOOLS

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="WorkWeek에서 내 잔여 휴가 일수가 얼마나 남았는지 확인해줘.",
    config={"tools": ALL_SAAS_ADK_TOOLS, "temperature": 0.1}
)
print(response.text)
```
