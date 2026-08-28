"""The Zenith portal page: one self-contained HTML document.

Extracted from `src.main` when the five-locale translation table and the
light/dark palette pushed the markup past the point where it could share a
file with the API. Nothing here imports from the rest of the application -
`render_page` returns the finished document and `src.main` serves it.

Two things in here are load-bearing beyond the visual design:

* `__BUILD_BADGE__` is a placeholder `src.main._build_badge_html` fills in, and
  the `build-badge*` class names it emits are styled below. `tests/
  test_build_info.py` asserts on both.
* Every `onclick`/`id` the original page used still exists. This was a restyle,
  not a rewrite: sign-in, Secret Manager token management, the architecture
  toggle and the registry inspector all behave exactly as they did.
"""

from __future__ import annotations

import json

#: The locales the page can render. `en-US` is the fallback for any key a
#: locale has not translated, so it must stay complete.
SUPPORTED_LOCALES: tuple[str, ...] = ("en-US", "zh-TW", "ja", "ko", "id")


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en-US": {
        "brand_sub": "HR & IT Solution",
        "rail_guest": "Not signed in",
        "rail_guest_sub": "Connect WorkWeek to begin",
        "status_online": "System online",
        "lang_title": "Change language",
        "theme_title": "Toggle ink / washi theme",
        "arch_label": "Architecture",
        "arch_title": "Dev (in-process) vs Production (Agent Registry)",
        "arch_dev": "Dev",
        "arch_prod": "Production",
        "btn_signin": "Sign in & connect",
        "btn_token": "Token",
        "btn_token_title": "FastMCP token settings in Secret Manager",
        "btn_switch": "Switch",
        "btn_switch_title": "Switch user account",
        "btn_signout": "Sign out",
        "hero_eyebrow": "HR & IT intelligent platform",
        "hero_title": "HR Intelligent Solution",
        "hero_desc": "Welcome to the enterprise HR & IT self-service assistant. Ask about leave balances, raise an IT ticket, or look up company policy - in the language you prefer.",
        "modules_heading": "Service modules",
        "nav_all": "All actions",
        "nav_hr": "WorkWeek (HR)",
        "nav_itsm": "ServiceImmediately (ITSM)",
        "nav_policy": "Policies & FAQ",
        "nav_cross": "Cross-system",
        "chat_title": "AI Assistant",
        "chat_ready": "READY",
        "chat_today": "TODAY",
        "typing": "Reasoning and querying FastMCP SaaS...",
        "send": "Send",
        "input_locked": "Sign in and connect WorkWeek above to start chatting...",
        "input_ready": "Ask anything - leave balance, IT ticket, company policy...",
        "welcome": "Welcome to the enterprise HR & IT self-service AI assistant. FastMCP credentials are integrated with Google Cloud Secret Manager. Choose [Sign in & connect] in the top right to begin.",
        "tag_ready": "SYSTEM_READY",
        "references": "References",
        "login_title": "Sign in with corporate email",
        "login_desc": "Personal FastMCP tokens are resolved automatically from Google Cloud Secret Manager. Existing accounts connect in one click.",
        "login_email_label": "Google corporate email",
        "login_email_ph": "your-ldap@google.com",
        "login_token_label": "Personal FastMCP token (X-MCP-Token) - first-time setup",
        "login_token_hint": "Paste your personal FastMCP token once. The service account stores it in Secret Manager for all future logins.",
        "login_connect": "Connect & start",
        "login_save_connect": "Save to Secret Manager & connect",
        "login_need_email": "Please enter your corporate Google email.",
        "login_resolving": "Resolving FastMCP credentials via Secret Manager...",
        "login_first_time": "First-time setup: enter your FastMCP token once to store it in Secret Manager.",
        "login_failed": "Connection failed. Please verify your credentials.",
        "login_network": "Network error contacting the backend.",
        "token_title": "FastMCP token settings",
        "token_desc": "FastMCP credentials stored in Google Cloud Secret Manager and loaded by the Cloud Run service account.",
        "token_account_label": "Authenticated account",
        "token_active_label": "Active Secret Manager token",
        "token_active_fallback": "Active in Secret Manager",
        "token_update_label": "Update personal FastMCP token (mcp_...)",
        "token_update_hint": "Updating here writes a new secret version directly to Secret Manager and updates your live session.",
        "token_save": "Update in Secret Manager",
        "token_need": "Please enter a valid FastMCP token (mcp_...).",
        "token_updating": "Updating Secret Manager and validating FastMCP...",
        "token_failed": "Failed to update the token.",
        "token_network": "Network error updating Secret Manager.",
        "cancel": "Cancel",
        "close": "Close",
        "peek_title": "Show / hide token",
        "msg_connected": "Connected to WorkWeek FastMCP. {name} is bound to employee record {id}.",
        "msg_token_updated": "FastMCP token updated in Secret Manager, bound to {id}.",
        "msg_signed_out": "Signed out. The WorkWeek connection is closed.",
        "msg_arch_prod": "[Architecture: Production] Multi-service Agent Registry (A2A + FastMCP) is active. Fail-fast diagnostics are live.",
        "msg_arch_dev": "[Architecture: Dev] Reverted to the in-process development architecture.",
        "msg_error": "Error: ",
        "msg_unable": "Unable to process the message",
        "msg_network": "Network error communicating with the HR agent backend.",
        "insp_title": "Registry inspector",
        "insp_live": "Live A2A + FastMCP",
        "insp_discovery": "Discovery",
        "insp_total": "Total",
        "insp_agent": "Discovered A2A agent",
        "insp_skills": "Discovered skills",
        "insp_tools": "FastMCP discovered tools",
        "insp_action": "Resolved action",
        "insp_verified": "Verified live execution (zero mock hallucination)",
        "insp_tools_unit": "tools",
        "a_balance_l": "Leave balances",
        "a_balance_d": "How much annual, sick and personal leave is left.",
        "a_balance_p": "What is my current leave balance?",
        "a_vacation_l": "Request vacation",
        "a_vacation_d": "Submit paid time off straight into WorkWeek.",
        "a_vacation_p": "Submit 2 days vacation starting next Monday",
        "a_manager_l": "Manager & department",
        "a_manager_d": "Check your reporting line and org placement.",
        "a_manager_p": "Who is my manager and what is my department?",
        "a_history_l": "Leave history",
        "a_history_d": "Review recent leave requests and their status.",
        "a_history_p": "Show my recent leave request history",
        "a_vpn_l": "Report VPN issue",
        "a_vpn_d": "Raise an incident for connectivity problems.",
        "a_vpn_p": "Create an IT ticket because my VPN connection keeps dropping.",
        "a_laptop_l": "Report laptop issue",
        "a_laptop_d": "Log a hardware fault for repair or replacement.",
        "a_laptop_p": "Create an IT ticket for laptop screen flickering and hardware malfunction.",
        "a_access_l": "Request system access",
        "a_access_d": "Ask for permissions on an enterprise system.",
        "a_access_p": "Create an IT ticket requesting access to enterprise GitHub repository.",
        "a_tickets_l": "My active tickets",
        "a_tickets_d": "List every support ticket still open for you.",
        "a_tickets_p": "List all my active support tickets",
        "a_status_l": "Check ticket status",
        "a_status_d": "Look up the progress of a specific incident.",
        "a_status_p": "What is the status of ticket INC-5001?",
        "a_bereave_l": "Bereavement policy",
        "a_bereave_d": "Entitlement and duration for compassionate leave.",
        "a_bereave_p": "What is the company bereavement leave entitlement policy?",
        "a_remote_l": "Remote work policy",
        "a_remote_d": "Home office equipment rules for remote staff.",
        "a_remote_p": "What is the policy for purchasing home office monitors for remote workers?",
        "a_parental_l": "Parental leave policy",
        "a_parental_d": "Duration and entitlement for new parents.",
        "a_parental_p": "What is the company parental leave duration and entitlement policy?",
        "a_monitor_l": "Order home monitor (UC-2.1)",
        "a_monitor_d": "Verify remote eligibility, then raise the order.",
        "a_monitor_p": "I just read the remote work policy and saw I am eligible for a home office monitor. Can you verify my remote status and order one for me?",
        "a_medical_l": "Medical leave & delegation (UC-2.2)",
        "a_medical_d": "Book the leave and hand over your responsibilities.",
        "a_medical_p": "I need to take short-term medical leave starting next Monday. What is the process, and can you set it up for me?",
        "a_london_l": "London transfer & badge (UC-2.3)",
        "a_london_d": "Allowance, record update and building access.",
        "a_london_p": "I am transferring to the London office next month. Can you tell me the relocation allowance, update my record, and get my building access sorted?",
    },

    "zh-TW": {
        "brand_sub": "人資與資訊服務平台",
        "rail_guest": "尚未登入",
        "rail_guest_sub": "請先連線 WorkWeek",
        "status_online": "系統運作中",
        "lang_title": "切換語言",
        "theme_title": "切換墨色 / 和紙主題",
        "arch_label": "系統架構",
        "arch_title": "開發模式（同進程）與正式模式（Agent Registry）",
        "arch_dev": "開發",
        "arch_prod": "正式",
        "btn_signin": "登入並連線",
        "btn_token": "權杖",
        "btn_token_title": "Secret Manager 的 FastMCP 權杖設定",
        "btn_switch": "切換帳號",
        "btn_switch_title": "切換使用者帳號",
        "btn_signout": "登出",
        "hero_eyebrow": "HR 與 IT 智慧平台",
        "hero_title": "HR 智慧解決方案",
        "hero_desc": "歡迎使用企業 HR 與 IT 自助 AI 助理。您可以查詢休假餘額、申報 IT 問題，或查閱公司政策，並以您慣用的語言取得回覆。",
        "modules_heading": "服務模組",
        "nav_all": "全部服務",
        "nav_hr": "WorkWeek（人資）",
        "nav_itsm": "ServiceImmediately（資訊）",
        "nav_policy": "政策與常見問題",
        "nav_cross": "跨系統流程",
        "chat_title": "AI 智慧助理",
        "chat_ready": "待命中",
        "chat_today": "今天",
        "typing": "正在推理並查詢 FastMCP SaaS…",
        "send": "傳送",
        "input_locked": "請先於右上角登入並連線 WorkWeek，即可開始對話…",
        "input_ready": "有什麼需要協助的？休假餘額、IT 報修、公司政策皆可詢問…",
        "welcome": "歡迎使用企業 HR 與 IT 自助 AI 助理。FastMCP 憑證已整合 Google Cloud Secret Manager。請點選右上角的〔登入並連線〕開始使用。",
        "tag_ready": "系統就緒",
        "references": "參考來源",
        "login_title": "使用公司電子郵件登入",
        "login_desc": "個人 FastMCP 權杖會自動從 Google Cloud Secret Manager 取得，已建檔的帳號可一鍵連線。",
        "login_email_label": "Google 公司電子郵件",
        "login_email_ph": "your-ldap@google.com",
        "login_token_label": "個人 FastMCP 權杖（X-MCP-Token）— 初次設定",
        "login_token_hint": "僅需貼上一次個人 FastMCP 權杖，服務帳戶會將其存入 Secret Manager，供日後登入使用。",
        "login_connect": "連線並開始",
        "login_save_connect": "存入 Secret Manager 並連線",
        "login_need_email": "請輸入您的公司 Google 電子郵件。",
        "login_resolving": "正在透過 Secret Manager 解析 FastMCP 憑證…",
        "login_first_time": "初次設定：請輸入一次 FastMCP 權杖，以便存入 Secret Manager。",
        "login_failed": "連線失敗，請確認您的憑證。",
        "login_network": "與後端連線時發生網路錯誤。",
        "token_title": "FastMCP 權杖設定",
        "token_desc": "FastMCP 憑證儲存於 Google Cloud Secret Manager，並由 Cloud Run 服務帳戶載入。",
        "token_account_label": "已驗證帳號",
        "token_active_label": "目前 Secret Manager 權杖",
        "token_active_fallback": "已於 Secret Manager 啟用",
        "token_update_label": "更新個人 FastMCP 權杖（mcp_…）",
        "token_update_hint": "在此更新會直接於 Secret Manager 寫入新版本，並同步更新您目前的工作階段。",
        "token_save": "更新至 Secret Manager",
        "token_need": "請輸入有效的 FastMCP 權杖（mcp_…）。",
        "token_updating": "正在更新 Secret Manager 並驗證 FastMCP…",
        "token_failed": "權杖更新失敗。",
        "token_network": "更新 Secret Manager 時發生網路錯誤。",
        "cancel": "取消",
        "close": "關閉",
        "peek_title": "顯示 / 隱藏權杖",
        "msg_connected": "已連線至 WorkWeek FastMCP。{name} 已綁定員工編號 {id}。",
        "msg_token_updated": "FastMCP 權杖已更新至 Secret Manager，並綁定 {id}。",
        "msg_signed_out": "已登出，WorkWeek 連線已中斷。",
        "msg_arch_prod": "〔架構：正式模式〕多服務 Agent Registry（A2A + FastMCP）已啟用，快速失敗診斷同步開啟。",
        "msg_arch_dev": "〔架構：開發模式〕已切回同進程的開發架構。",
        "msg_error": "錯誤：",
        "msg_unable": "無法處理此訊息",
        "msg_network": "與 HR 代理後端通訊時發生網路錯誤。",
        "insp_title": "Registry 檢視器",
        "insp_live": "即時 A2A + FastMCP",
        "insp_discovery": "探索",
        "insp_total": "總計",
        "insp_agent": "探索到的 A2A 代理",
        "insp_skills": "探索到的技能",
        "insp_tools": "FastMCP 探索到的工具",
        "insp_action": "解析出的動作",
        "insp_verified": "已驗證實際執行（無模擬資料）",
        "insp_tools_unit": "項工具",
        "a_balance_l": "查詢休假餘額",
        "a_balance_d": "查看特休、病假與事假的剩餘天數。",
        "a_balance_p": "我目前的休假餘額還有多少？",
        "a_vacation_l": "申請特休",
        "a_vacation_d": "直接於 WorkWeek 送出休假申請。",
        "a_vacation_p": "請幫我申請下週一開始的兩天特休",
        "a_manager_l": "主管與部門",
        "a_manager_d": "確認您的匯報主管與組織單位。",
        "a_manager_p": "我的主管是誰？我隸屬哪個部門？",
        "a_history_l": "請假紀錄",
        "a_history_d": "檢視近期請假申請與其審核狀態。",
        "a_history_p": "請顯示我近期的請假申請紀錄",
        "a_vpn_l": "VPN 問題報修",
        "a_vpn_d": "為連線異常建立 IT 事件單。",
        "a_vpn_p": "我的 VPN 連線一直斷線，請幫我開一張 IT 工單。",
        "a_laptop_l": "筆電硬體報修",
        "a_laptop_d": "登錄硬體故障以進行維修或更換。",
        "a_laptop_p": "我的筆電螢幕閃爍且硬體異常，請幫我開一張 IT 工單。",
        "a_access_l": "申請系統權限",
        "a_access_d": "為企業系統申請存取權限。",
        "a_access_p": "請幫我開一張 IT 工單，申請企業 GitHub 儲存庫的存取權限。",
        "a_tickets_l": "我的待處理工單",
        "a_tickets_d": "列出所有尚未結案的支援工單。",
        "a_tickets_p": "請列出我所有進行中的支援工單",
        "a_status_l": "查詢工單進度",
        "a_status_d": "查看特定事件單的處理狀態。",
        "a_status_p": "工單 INC-5001 目前的處理狀態如何？",
        "a_bereave_l": "喪假政策",
        "a_bereave_d": "喪假的給假天數與適用資格。",
        "a_bereave_p": "公司的喪假天數與請假規定是什麼？",
        "a_remote_l": "遠距工作政策",
        "a_remote_d": "遠距員工的居家辦公設備規範。",
        "a_remote_p": "公司對遠距工作者採購居家辦公螢幕的政策是什麼？",
        "a_parental_l": "育嬰假政策",
        "a_parental_d": "新手父母的給假期間與適用資格。",
        "a_parental_p": "公司的育嬰假期間與相關權益規定是什麼？",
        "a_monitor_l": "申請居家螢幕（UC-2.1）",
        "a_monitor_d": "確認遠距資格後代為送出採購。",
        "a_monitor_p": "我剛看完遠距工作政策，發現我符合申請居家辦公螢幕的資格。可以幫我確認遠距身分並代為訂購嗎？",
        "a_medical_l": "病假與職務代理（UC-2.2）",
        "a_medical_d": "同時完成請假與職務交接。",
        "a_medical_p": "我下週一開始需要請短期病假，流程是什麼？可以幫我一併處理嗎？",
        "a_london_l": "倫敦調任與門禁（UC-2.3）",
        "a_london_d": "搬遷補助、資料更新與門禁申請。",
        "a_london_p": "我下個月要調任倫敦辦公室。可以告訴我搬遷補助的規定、更新我的員工資料，並協助辦理門禁權限嗎？",
    },

    "ja": {
        "brand_sub": "人事・IT サービス基盤",
        "rail_guest": "未サインイン",
        "rail_guest_sub": "WorkWeek に接続してください",
        "status_online": "システム稼働中",
        "lang_title": "言語を切り替える",
        "theme_title": "墨 / 和紙テーマを切り替える",
        "arch_label": "アーキテクチャ",
        "arch_title": "開発（インプロセス）と本番（Agent Registry）",
        "arch_dev": "開発",
        "arch_prod": "本番",
        "btn_signin": "サインインして接続",
        "btn_token": "トークン",
        "btn_token_title": "Secret Manager の FastMCP トークン設定",
        "btn_switch": "アカウント切替",
        "btn_switch_title": "ユーザーアカウントを切り替える",
        "btn_signout": "サインアウト",
        "hero_eyebrow": "人事・IT インテリジェント基盤",
        "hero_title": "HR インテリジェント ソリューション",
        "hero_desc": "人事・IT セルフサービス AI アシスタントへようこそ。休暇残日数の確認、IT 障害の起票、社内規程の照会を、ご希望の言語でご利用いただけます。",
        "modules_heading": "サービスモジュール",
        "nav_all": "すべての操作",
        "nav_hr": "WorkWeek（人事）",
        "nav_itsm": "ServiceImmediately（IT）",
        "nav_policy": "規程・よくある質問",
        "nav_cross": "システム横断",
        "chat_title": "AI アシスタント",
        "chat_ready": "待機中",
        "chat_today": "本日",
        "typing": "推論して FastMCP SaaS に問い合わせています…",
        "send": "送信",
        "input_locked": "右上からサインインし、WorkWeek に接続すると会話を開始できます…",
        "input_ready": "ご質問をどうぞ — 休暇残日数、IT 起票、社内規程など…",
        "welcome": "人事・IT セルフサービス AI アシスタントへようこそ。FastMCP 認証情報は Google Cloud Secret Manager と連携しています。右上の〔サインインして接続〕からお始めください。",
        "tag_ready": "システム準備完了",
        "references": "参照",
        "login_title": "社用メールでサインイン",
        "login_desc": "個人の FastMCP トークンは Google Cloud Secret Manager から自動的に取得されます。登録済みのアカウントはワンクリックで接続できます。",
        "login_email_label": "Google 社用メールアドレス",
        "login_email_ph": "your-ldap@google.com",
        "login_token_label": "個人 FastMCP トークン（X-MCP-Token）— 初回設定",
        "login_token_hint": "個人の FastMCP トークンを一度だけ貼り付けてください。サービスアカウントが Secret Manager に保存し、次回以降のサインインで利用します。",
        "login_connect": "接続して開始",
        "login_save_connect": "Secret Manager に保存して接続",
        "login_need_email": "社用の Google メールアドレスを入力してください。",
        "login_resolving": "Secret Manager 経由で FastMCP 認証情報を解決しています…",
        "login_first_time": "初回設定：FastMCP トークンを一度入力すると Secret Manager に保存されます。",
        "login_failed": "接続に失敗しました。認証情報をご確認ください。",
        "login_network": "バックエンドとの通信でネットワークエラーが発生しました。",
        "token_title": "FastMCP トークン設定",
        "token_desc": "FastMCP 認証情報は Google Cloud Secret Manager に保存され、Cloud Run のサービスアカウントが読み込みます。",
        "token_account_label": "認証済みアカウント",
        "token_active_label": "有効な Secret Manager トークン",
        "token_active_fallback": "Secret Manager で有効",
        "token_update_label": "個人 FastMCP トークンを更新（mcp_…）",
        "token_update_hint": "ここで更新すると Secret Manager に新しいバージョンが書き込まれ、現在のセッションも更新されます。",
        "token_save": "Secret Manager を更新",
        "token_need": "有効な FastMCP トークン（mcp_…）を入力してください。",
        "token_updating": "Secret Manager を更新し、FastMCP を検証しています…",
        "token_failed": "トークンの更新に失敗しました。",
        "token_network": "Secret Manager の更新でネットワークエラーが発生しました。",
        "cancel": "キャンセル",
        "close": "閉じる",
        "peek_title": "トークンの表示 / 非表示",
        "msg_connected": "WorkWeek FastMCP に接続しました。{name} は従業員レコード {id} に紐付けられています。",
        "msg_token_updated": "FastMCP トークンを Secret Manager で更新し、{id} に紐付けました。",
        "msg_signed_out": "サインアウトしました。WorkWeek との接続を終了しました。",
        "msg_arch_prod": "〔アーキテクチャ：本番〕マルチサービスの Agent Registry（A2A + FastMCP）が有効です。フェイルファスト診断も稼働しています。",
        "msg_arch_dev": "〔アーキテクチャ：開発〕インプロセスの開発構成に戻しました。",
        "msg_error": "エラー：",
        "msg_unable": "メッセージを処理できません",
        "msg_network": "HR エージェントのバックエンドとの通信でネットワークエラーが発生しました。",
        "insp_title": "レジストリ インスペクター",
        "insp_live": "ライブ A2A + FastMCP",
        "insp_discovery": "探索",
        "insp_total": "合計",
        "insp_agent": "検出された A2A エージェント",
        "insp_skills": "検出されたスキル",
        "insp_tools": "FastMCP で検出されたツール",
        "insp_action": "解決されたアクション",
        "insp_verified": "実行を検証済み（モックなし）",
        "insp_tools_unit": "件のツール",
        "a_balance_l": "休暇残日数",
        "a_balance_d": "年次・病気・私用休暇の残日数を確認します。",
        "a_balance_p": "現在の休暇残日数を教えてください。",
        "a_vacation_l": "有給休暇の申請",
        "a_vacation_d": "WorkWeek に直接、有給休暇を申請します。",
        "a_vacation_p": "来週の月曜日から2日間の有給休暇を申請してください。",
        "a_manager_l": "上長と部署",
        "a_manager_d": "レポートラインと所属組織を確認します。",
        "a_manager_p": "私の上長は誰で、所属部署はどこですか。",
        "a_history_l": "休暇申請履歴",
        "a_history_d": "最近の休暇申請とその状況を確認します。",
        "a_history_p": "最近の休暇申請の履歴を表示してください。",
        "a_vpn_l": "VPN 障害の報告",
        "a_vpn_d": "接続障害のインシデントを起票します。",
        "a_vpn_p": "VPN の接続が頻繁に切れるため、IT チケットを作成してください。",
        "a_laptop_l": "ノート PC の故障報告",
        "a_laptop_d": "ハードウェア故障を修理・交換のため登録します。",
        "a_laptop_p": "ノート PC の画面がちらつき、ハードウェアの不具合があるため IT チケットを作成してください。",
        "a_access_l": "システム権限の申請",
        "a_access_d": "社内システムのアクセス権限を申請します。",
        "a_access_p": "社内 GitHub リポジトリへのアクセス権限を申請する IT チケットを作成してください。",
        "a_tickets_l": "対応中のチケット",
        "a_tickets_d": "未クローズのサポートチケットを一覧します。",
        "a_tickets_p": "対応中のサポートチケットをすべて一覧表示してください。",
        "a_status_l": "チケット状況の確認",
        "a_status_d": "特定インシデントの進捗を照会します。",
        "a_status_p": "チケット INC-5001 の状況を教えてください。",
        "a_bereave_l": "慶弔休暇の規程",
        "a_bereave_d": "忌引休暇の日数と適用条件。",
        "a_bereave_p": "会社の慶弔（忌引）休暇の日数と適用条件を教えてください。",
        "a_remote_l": "リモートワーク規程",
        "a_remote_d": "在宅勤務者向けの機材に関する規程。",
        "a_remote_p": "リモートワーク社員が在宅用モニターを購入する場合の規程を教えてください。",
        "a_parental_l": "育児休業の規程",
        "a_parental_d": "育児休業の期間と適用条件。",
        "a_parental_p": "会社の育児休業の期間と権利に関する規程を教えてください。",
        "a_monitor_l": "在宅モニターの手配（UC-2.1）",
        "a_monitor_d": "リモート適格性を確認のうえ発注します。",
        "a_monitor_p": "リモートワーク規程を読み、在宅用モニターの対象になると分かりました。私のリモート勤務区分を確認したうえで、1台手配してもらえますか。",
        "a_medical_l": "病気休暇と業務代行（UC-2.2）",
        "a_medical_d": "休暇取得と業務引き継ぎをまとめて行います。",
        "a_medical_p": "来週の月曜日から短期の病気休暇を取る必要があります。手続きを教えていただき、あわせて手配してもらえますか。",
        "a_london_l": "ロンドン異動と入館証（UC-2.3）",
        "a_london_d": "赴任手当・記録更新・入館権限をまとめて処理します。",
        "a_london_p": "来月ロンドンオフィスへ異動します。赴任手当について教えていただき、私の記録を更新し、入館権限の手配もお願いできますか。",
    },

    "ko": {
        "brand_sub": "HR·IT 서비스 플랫폼",
        "rail_guest": "로그인되지 않음",
        "rail_guest_sub": "WorkWeek에 연결해 주세요",
        "status_online": "시스템 정상 운영 중",
        "lang_title": "언어 변경",
        "theme_title": "먹빛 / 화지 테마 전환",
        "arch_label": "아키텍처",
        "arch_title": "개발(인프로세스)과 운영(Agent Registry)",
        "arch_dev": "개발",
        "arch_prod": "운영",
        "btn_signin": "로그인 및 연결",
        "btn_token": "토큰",
        "btn_token_title": "Secret Manager의 FastMCP 토큰 설정",
        "btn_switch": "계정 전환",
        "btn_switch_title": "사용자 계정 전환",
        "btn_signout": "로그아웃",
        "hero_eyebrow": "HR·IT 지능형 플랫폼",
        "hero_title": "HR 지능형 솔루션",
        "hero_desc": "기업 HR·IT 셀프서비스 AI 어시스턴트입니다. 휴가 잔여일수 확인, IT 장애 접수, 사내 규정 조회를 원하시는 언어로 이용하실 수 있습니다.",
        "modules_heading": "서비스 모듈",
        "nav_all": "전체 작업",
        "nav_hr": "WorkWeek (인사)",
        "nav_itsm": "ServiceImmediately (IT)",
        "nav_policy": "규정 및 FAQ",
        "nav_cross": "시스템 연계",
        "chat_title": "AI 어시스턴트",
        "chat_ready": "준비됨",
        "chat_today": "오늘",
        "typing": "추론하며 FastMCP SaaS에 질의하는 중…",
        "send": "보내기",
        "input_locked": "우측 상단에서 로그인하고 WorkWeek에 연결하면 대화를 시작할 수 있습니다…",
        "input_ready": "무엇이든 물어보세요 — 휴가 잔여일수, IT 접수, 사내 규정…",
        "welcome": "기업 HR·IT 셀프서비스 AI 어시스턴트입니다. FastMCP 자격 증명은 Google Cloud Secret Manager와 연동되어 있습니다. 우측 상단의 [로그인 및 연결]을 눌러 시작하세요.",
        "tag_ready": "시스템 준비 완료",
        "references": "참고 자료",
        "login_title": "회사 이메일로 로그인",
        "login_desc": "개인 FastMCP 토큰은 Google Cloud Secret Manager에서 자동으로 조회됩니다. 등록된 계정은 한 번의 클릭으로 연결됩니다.",
        "login_email_label": "Google 회사 이메일",
        "login_email_ph": "your-ldap@google.com",
        "login_token_label": "개인 FastMCP 토큰(X-MCP-Token) — 최초 설정",
        "login_token_hint": "개인 FastMCP 토큰을 한 번만 입력하세요. 서비스 계정이 Secret Manager에 저장해 이후 로그인에 사용합니다.",
        "login_connect": "연결하고 시작",
        "login_save_connect": "Secret Manager에 저장 후 연결",
        "login_need_email": "회사 Google 이메일을 입력해 주세요.",
        "login_resolving": "Secret Manager를 통해 FastMCP 자격 증명을 확인하는 중…",
        "login_first_time": "최초 설정: FastMCP 토큰을 한 번 입력하면 Secret Manager에 저장됩니다.",
        "login_failed": "연결에 실패했습니다. 자격 증명을 확인해 주세요.",
        "login_network": "백엔드 통신 중 네트워크 오류가 발생했습니다.",
        "token_title": "FastMCP 토큰 설정",
        "token_desc": "FastMCP 자격 증명은 Google Cloud Secret Manager에 저장되며 Cloud Run 서비스 계정이 불러옵니다.",
        "token_account_label": "인증된 계정",
        "token_active_label": "활성 Secret Manager 토큰",
        "token_active_fallback": "Secret Manager에서 활성",
        "token_update_label": "개인 FastMCP 토큰 업데이트(mcp_…)",
        "token_update_hint": "여기서 업데이트하면 Secret Manager에 새 버전이 기록되고 현재 세션도 갱신됩니다.",
        "token_save": "Secret Manager 업데이트",
        "token_need": "유효한 FastMCP 토큰(mcp_…)을 입력해 주세요.",
        "token_updating": "Secret Manager를 업데이트하고 FastMCP를 검증하는 중…",
        "token_failed": "토큰 업데이트에 실패했습니다.",
        "token_network": "Secret Manager 업데이트 중 네트워크 오류가 발생했습니다.",
        "cancel": "취소",
        "close": "닫기",
        "peek_title": "토큰 표시 / 숨기기",
        "msg_connected": "WorkWeek FastMCP에 연결되었습니다. {name} 님이 사번 {id}에 연결되었습니다.",
        "msg_token_updated": "FastMCP 토큰이 Secret Manager에서 업데이트되어 {id}에 연결되었습니다.",
        "msg_signed_out": "로그아웃되었습니다. WorkWeek 연결이 해제되었습니다.",
        "msg_arch_prod": "[아키텍처: 운영] 멀티 서비스 Agent Registry(A2A + FastMCP)가 활성화되었습니다. 페일패스트 진단도 동작합니다.",
        "msg_arch_dev": "[아키텍처: 개발] 인프로세스 개발 구성으로 되돌렸습니다.",
        "msg_error": "오류: ",
        "msg_unable": "메시지를 처리할 수 없습니다",
        "msg_network": "HR 에이전트 백엔드와 통신 중 네트워크 오류가 발생했습니다.",
        "insp_title": "레지스트리 인스펙터",
        "insp_live": "실시간 A2A + FastMCP",
        "insp_discovery": "탐색",
        "insp_total": "합계",
        "insp_agent": "탐색된 A2A 에이전트",
        "insp_skills": "탐색된 스킬",
        "insp_tools": "FastMCP 탐색 도구",
        "insp_action": "결정된 작업",
        "insp_verified": "실제 실행 검증됨(모의 응답 없음)",
        "insp_tools_unit": "개 도구",
        "a_balance_l": "휴가 잔여일수",
        "a_balance_d": "연차·병가·개인 휴가 잔여일수를 확인합니다.",
        "a_balance_p": "현재 제 휴가 잔여일수는 얼마인가요?",
        "a_vacation_l": "연차 신청",
        "a_vacation_d": "WorkWeek에 바로 연차를 신청합니다.",
        "a_vacation_p": "다음 주 월요일부터 이틀간 연차를 신청해 주세요.",
        "a_manager_l": "상사 및 부서",
        "a_manager_d": "보고 라인과 소속 조직을 확인합니다.",
        "a_manager_p": "제 상사는 누구이며 소속 부서는 어디인가요?",
        "a_history_l": "휴가 신청 이력",
        "a_history_d": "최근 휴가 신청과 진행 상태를 확인합니다.",
        "a_history_p": "최근 휴가 신청 이력을 보여 주세요.",
        "a_vpn_l": "VPN 장애 접수",
        "a_vpn_d": "연결 장애에 대한 인시던트를 접수합니다.",
        "a_vpn_p": "VPN 연결이 계속 끊겨서 IT 티켓을 생성해 주세요.",
        "a_laptop_l": "노트북 장애 접수",
        "a_laptop_d": "하드웨어 결함을 수리·교체용으로 등록합니다.",
        "a_laptop_p": "노트북 화면이 깜박이고 하드웨어 오작동이 있어 IT 티켓을 생성해 주세요.",
        "a_access_l": "시스템 권한 신청",
        "a_access_d": "사내 시스템 접근 권한을 요청합니다.",
        "a_access_p": "사내 GitHub 저장소 접근 권한을 요청하는 IT 티켓을 생성해 주세요.",
        "a_tickets_l": "진행 중인 티켓",
        "a_tickets_d": "아직 종료되지 않은 지원 티켓을 나열합니다.",
        "a_tickets_p": "진행 중인 지원 티켓을 모두 보여 주세요.",
        "a_status_l": "티켓 상태 확인",
        "a_status_d": "특정 인시던트의 진행 상황을 조회합니다.",
        "a_status_p": "INC-5001 티켓의 처리 상태는 어떻게 되나요?",
        "a_bereave_l": "경조 휴가 규정",
        "a_bereave_d": "상을 당했을 때의 휴가 일수와 적용 요건.",
        "a_bereave_p": "회사의 경조(상) 휴가 일수와 적용 규정은 어떻게 되나요?",
        "a_remote_l": "재택근무 규정",
        "a_remote_d": "재택 직원의 사무 기기 관련 규정.",
        "a_remote_p": "재택근무자가 홈오피스 모니터를 구매할 때의 회사 규정은 무엇인가요?",
        "a_parental_l": "육아휴직 규정",
        "a_parental_d": "출산·육아 시 휴직 기간과 적용 요건.",
        "a_parental_p": "회사의 육아휴직 기간과 권리에 관한 규정은 어떻게 되나요?",
        "a_monitor_l": "홈오피스 모니터 신청 (UC-2.1)",
        "a_monitor_d": "재택 자격을 확인한 뒤 주문을 진행합니다.",
        "a_monitor_p": "재택근무 규정을 읽어 보니 홈오피스 모니터 지원 대상인 것 같습니다. 제 재택근무 상태를 확인하고 한 대 주문해 주시겠어요?",
        "a_medical_l": "병가 및 업무 위임 (UC-2.2)",
        "a_medical_d": "휴가 신청과 업무 인수인계를 함께 처리합니다.",
        "a_medical_p": "다음 주 월요일부터 단기 병가를 써야 합니다. 절차가 어떻게 되며, 함께 처리해 주실 수 있나요?",
        "a_london_l": "런던 전근 및 출입증 (UC-2.3)",
        "a_london_d": "이전 수당, 기록 갱신, 건물 출입 권한.",
        "a_london_p": "다음 달 런던 사무실로 전근합니다. 이전 수당을 알려 주시고, 제 기록을 갱신하고, 건물 출입 권한도 처리해 주시겠어요?",
    },

    "id": {
        "brand_sub": "Platform Layanan SDM & TI",
        "rail_guest": "Belum masuk",
        "rail_guest_sub": "Hubungkan WorkWeek untuk mulai",
        "status_online": "Sistem aktif",
        "lang_title": "Ganti bahasa",
        "theme_title": "Ganti tema tinta / kertas washi",
        "arch_label": "Arsitektur",
        "arch_title": "Dev (dalam proses) vs Produksi (Agent Registry)",
        "arch_dev": "Dev",
        "arch_prod": "Produksi",
        "btn_signin": "Masuk & hubungkan",
        "btn_token": "Token",
        "btn_token_title": "Pengaturan token FastMCP di Secret Manager",
        "btn_switch": "Ganti akun",
        "btn_switch_title": "Ganti akun pengguna",
        "btn_signout": "Keluar",
        "hero_eyebrow": "Platform cerdas SDM & TI",
        "hero_title": "Solusi Cerdas SDM",
        "hero_desc": "Selamat datang di asisten AI swalayan SDM & TI. Tanyakan sisa cuti, laporkan gangguan TI, atau cari kebijakan perusahaan dalam bahasa yang Anda pilih.",
        "modules_heading": "Modul layanan",
        "nav_all": "Semua tindakan",
        "nav_hr": "WorkWeek (SDM)",
        "nav_itsm": "ServiceImmediately (TI)",
        "nav_policy": "Kebijakan & FAQ",
        "nav_cross": "Lintas sistem",
        "chat_title": "Asisten AI",
        "chat_ready": "SIAP",
        "chat_today": "HARI INI",
        "typing": "Menalar dan meminta data ke FastMCP SaaS...",
        "send": "Kirim",
        "input_locked": "Masuk dan hubungkan WorkWeek di kanan atas untuk mulai mengobrol...",
        "input_ready": "Tanyakan apa saja - sisa cuti, tiket TI, kebijakan perusahaan...",
        "welcome": "Selamat datang di asisten AI swalayan SDM & TI. Kredensial FastMCP telah terintegrasi dengan Google Cloud Secret Manager. Pilih [Masuk & hubungkan] di kanan atas untuk memulai.",
        "tag_ready": "SISTEM_SIAP",
        "references": "Referensi",
        "login_title": "Masuk dengan email perusahaan",
        "login_desc": "Token FastMCP pribadi diambil otomatis dari Google Cloud Secret Manager. Akun yang sudah terdaftar terhubung dalam satu klik.",
        "login_email_label": "Email perusahaan Google",
        "login_email_ph": "your-ldap@google.com",
        "login_token_label": "Token FastMCP pribadi (X-MCP-Token) - penyiapan pertama",
        "login_token_hint": "Tempelkan token FastMCP pribadi Anda satu kali. Akun layanan akan menyimpannya di Secret Manager untuk login berikutnya.",
        "login_connect": "Hubungkan & mulai",
        "login_save_connect": "Simpan ke Secret Manager & hubungkan",
        "login_need_email": "Silakan masukkan email Google perusahaan Anda.",
        "login_resolving": "Mengambil kredensial FastMCP melalui Secret Manager...",
        "login_first_time": "Penyiapan pertama: masukkan token FastMCP sekali untuk disimpan di Secret Manager.",
        "login_failed": "Koneksi gagal. Silakan periksa kredensial Anda.",
        "login_network": "Kesalahan jaringan saat menghubungi backend.",
        "token_title": "Pengaturan token FastMCP",
        "token_desc": "Kredensial FastMCP disimpan di Google Cloud Secret Manager dan dimuat oleh akun layanan Cloud Run.",
        "token_account_label": "Akun terautentikasi",
        "token_active_label": "Token Secret Manager aktif",
        "token_active_fallback": "Aktif di Secret Manager",
        "token_update_label": "Perbarui token FastMCP pribadi (mcp_...)",
        "token_update_hint": "Memperbarui di sini menulis versi rahasia baru langsung ke Secret Manager dan memperbarui sesi Anda.",
        "token_save": "Perbarui di Secret Manager",
        "token_need": "Silakan masukkan token FastMCP yang valid (mcp_...).",
        "token_updating": "Memperbarui Secret Manager dan memvalidasi FastMCP...",
        "token_failed": "Gagal memperbarui token.",
        "token_network": "Kesalahan jaringan saat memperbarui Secret Manager.",
        "cancel": "Batal",
        "close": "Tutup",
        "peek_title": "Tampilkan / sembunyikan token",
        "msg_connected": "Terhubung ke WorkWeek FastMCP. {name} tertaut ke data karyawan {id}.",
        "msg_token_updated": "Token FastMCP diperbarui di Secret Manager, tertaut ke {id}.",
        "msg_signed_out": "Anda telah keluar. Koneksi WorkWeek ditutup.",
        "msg_arch_prod": "[Arsitektur: Produksi] Agent Registry multi-layanan (A2A + FastMCP) aktif. Diagnostik fail-fast menyala.",
        "msg_arch_dev": "[Arsitektur: Dev] Kembali ke arsitektur pengembangan dalam proses.",
        "msg_error": "Kesalahan: ",
        "msg_unable": "Tidak dapat memproses pesan",
        "msg_network": "Kesalahan jaringan saat berkomunikasi dengan backend agen SDM.",
        "insp_title": "Inspektur Registry",
        "insp_live": "A2A + FastMCP langsung",
        "insp_discovery": "Penemuan",
        "insp_total": "Total",
        "insp_agent": "Agen A2A yang ditemukan",
        "insp_skills": "Keahlian yang ditemukan",
        "insp_tools": "Alat FastMCP yang ditemukan",
        "insp_action": "Tindakan yang ditentukan",
        "insp_verified": "Eksekusi langsung terverifikasi (tanpa data tiruan)",
        "insp_tools_unit": "alat",
        "a_balance_l": "Sisa cuti",
        "a_balance_d": "Lihat sisa cuti tahunan, sakit, dan pribadi.",
        "a_balance_p": "Berapa sisa cuti saya saat ini?",
        "a_vacation_l": "Ajukan cuti",
        "a_vacation_d": "Kirim pengajuan cuti langsung ke WorkWeek.",
        "a_vacation_p": "Ajukan cuti 2 hari mulai Senin depan",
        "a_manager_l": "Atasan & departemen",
        "a_manager_d": "Periksa jalur pelaporan dan unit organisasi Anda.",
        "a_manager_p": "Siapa atasan saya dan di departemen mana saya bekerja?",
        "a_history_l": "Riwayat cuti",
        "a_history_d": "Tinjau pengajuan cuti terakhir dan statusnya.",
        "a_history_p": "Tampilkan riwayat pengajuan cuti saya baru-baru ini",
        "a_vpn_l": "Laporkan gangguan VPN",
        "a_vpn_d": "Buat insiden untuk masalah konektivitas.",
        "a_vpn_p": "Buatkan tiket TI karena koneksi VPN saya terus terputus.",
        "a_laptop_l": "Laporkan gangguan laptop",
        "a_laptop_d": "Catat kerusakan perangkat keras untuk perbaikan.",
        "a_laptop_p": "Buatkan tiket TI untuk layar laptop yang berkedip dan kerusakan perangkat keras.",
        "a_access_l": "Minta akses sistem",
        "a_access_d": "Ajukan izin akses ke sistem perusahaan.",
        "a_access_p": "Buatkan tiket TI untuk meminta akses ke repositori GitHub perusahaan.",
        "a_tickets_l": "Tiket aktif saya",
        "a_tickets_d": "Daftar semua tiket dukungan yang masih terbuka.",
        "a_tickets_p": "Tampilkan semua tiket dukungan saya yang masih aktif",
        "a_status_l": "Cek status tiket",
        "a_status_d": "Lihat perkembangan sebuah insiden tertentu.",
        "a_status_p": "Bagaimana status tiket INC-5001?",
        "a_bereave_l": "Kebijakan cuti duka",
        "a_bereave_d": "Hak dan lama cuti untuk keperluan duka.",
        "a_bereave_p": "Bagaimana kebijakan hak cuti duka di perusahaan?",
        "a_remote_l": "Kebijakan kerja jarak jauh",
        "a_remote_d": "Aturan perangkat kantor rumah bagi pekerja remote.",
        "a_remote_p": "Bagaimana kebijakan pembelian monitor kantor rumah untuk pekerja jarak jauh?",
        "a_parental_l": "Kebijakan cuti melahirkan",
        "a_parental_d": "Lama dan hak cuti bagi orang tua baru.",
        "a_parental_p": "Bagaimana kebijakan lama dan hak cuti melahirkan di perusahaan?",
        "a_monitor_l": "Pesan monitor rumah (UC-2.1)",
        "a_monitor_d": "Verifikasi kelayakan remote, lalu buat pesanan.",
        "a_monitor_p": "Saya baru membaca kebijakan kerja jarak jauh dan tampaknya saya berhak atas monitor kantor rumah. Bisakah Anda memverifikasi status remote saya dan memesankan satu untuk saya?",
        "a_medical_l": "Cuti sakit & delegasi (UC-2.2)",
        "a_medical_d": "Ajukan cuti sekaligus serahkan tanggung jawab.",
        "a_medical_p": "Saya perlu mengambil cuti sakit jangka pendek mulai Senin depan. Bagaimana prosesnya, dan bisakah Anda mengaturnya untuk saya?",
        "a_london_l": "Pindah ke London & akses gedung (UC-2.3)",
        "a_london_d": "Tunjangan pindah, pembaruan data, dan akses gedung.",
        "a_london_p": "Bulan depan saya pindah ke kantor London. Bisakah Anda memberi tahu tunjangan relokasi, memperbarui data saya, dan mengurus akses gedung saya?",
    },
}


CHAT_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Zenith Enterprise HR &amp; IT Portal</title>

  <script>
    // Before first paint, deliberately. Reading the stored theme in
    // DOMContentLoaded means a dark-mode user watches the page flash washi
    // white first, which is exactly the jarring transition the aesthetic is
    // trying to avoid.
    (function () {
      try {
        var stored = localStorage.getItem('zenith_theme');
        var dark = stored ? stored === 'dark'
          : window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (dark) { document.documentElement.classList.add('dark'); }
      } catch (e) { /* private mode: light mode is a fine default */ }
    })();
  </script>

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;500;600&family=Inter:wght@400;500;600&family=Noto+Sans+TC:wght@400;500;600&family=Noto+Sans+JP:wght@400;500;600&family=Noto+Sans+KR:wght@400;500;600&display=swap">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=block">

  <style>
    /* ---------------------------------------------------------------------
       Wabi-Sabi palette. Every colour the page uses is a custom property, so
       the theme switch is one class on <html> rather than a second stylesheet
       - and the 500ms transition below can carry all of them at once.
       --------------------------------------------------------------------- */
    :root {
      --bg-background: #fbf9f4;
      --color-surface: #fbf9f4;
      --color-surface-lowest: #ffffff;
      --color-surface-low: #f5f3ee;
      --color-surface-container: #f0eee9;
      --color-surface-high: #eae8e3;
      --color-surface-highest: #e4e2dd;
      --color-surface-variant: #e4e2dd;
      --color-primary: #1d1e1b;
      --color-primary-container: #323330;
      --color-on-primary: #ffffff;
      --color-on-surface: #1b1c19;
      --color-on-surface-variant: #454742;
      --color-secondary: #5c614d;
      --color-secondary-container: #e0e5cc;
      --color-on-secondary-container: #626753;
      --color-secondary-fixed-dim: #c4c9b1;
      --color-outline: #767872;
      --color-outline-variant: #c6c7c0;
      --color-border-subtle: rgba(30, 31, 14, 0.1);

      /* Semantic accents. Muted to sit inside the palette rather than shout
         over it - an error still has to read as an error, but a warm clay is
         enough for that and a pure #ef4444 is not what this page is. */
      --color-danger: #8f4b3f;
      --color-danger-soft: rgba(143, 75, 63, 0.1);
      --color-success: #4d6b45;
      --color-success-soft: rgba(77, 107, 69, 0.1);
      --color-notice: #8a6d3b;
      --color-notice-soft: rgba(138, 109, 59, 0.12);
      --shadow-soft: 0 1px 2px rgba(30, 31, 14, 0.04), 0 8px 24px rgba(30, 31, 14, 0.05);
    }

    html.dark {
      --bg-background: #181916;
      --color-surface: #20211d;
      --color-surface-lowest: #141512;
      --color-surface-low: #252722;
      --color-surface-container: #2d2f28;
      --color-surface-high: #35372e;
      --color-surface-highest: #3f4238;
      --color-surface-variant: #2e3029;
      --color-primary: #edebe6;
      --color-primary-container: #282a24;
      --color-on-primary: #181916;
      --color-on-surface: #edebe6;
      --color-on-surface-variant: #a6a89f;
      --color-secondary: #8f9975;
      --color-secondary-container: #323826;
      --color-on-secondary-container: #c4c9b1;
      --color-secondary-fixed-dim: #5c614d;
      --color-outline: #5c5f55;
      --color-outline-variant: #3e4039;
      --color-border-subtle: rgba(237, 235, 230, 0.1);

      --color-danger: #d99e92;
      --color-danger-soft: rgba(217, 158, 146, 0.12);
      --color-success: #a8c39f;
      --color-success-soft: rgba(168, 195, 159, 0.12);
      --color-notice: #d6b77c;
      --color-notice-soft: rgba(214, 183, 124, 0.14);
      --shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 24px rgba(0, 0, 0, 0.25);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', 'Noto Sans TC', 'Noto Sans JP', 'Noto Sans KR',
                   -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: var(--bg-background);
      color: var(--color-on-surface);
      min-height: 100vh;
      overscroll-behavior: none;
      -webkit-font-smoothing: antialiased;
    }

    /* One rule carries the whole theme change. Scoped to the properties that
       actually differ so it never animates a layout-affecting value. */
    body, aside, header, main, .panel, .card, .chip, .bubble, .modal,
    .field input, .badge, .rail-link, .divider {
      transition: background-color 0.5s ease, color 0.5s ease,
                  border-color 0.5s ease, box-shadow 0.5s ease;
    }
    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; animation: none !important; }
    }

    .serif {
      font-family: 'Source Serif 4', 'Noto Serif TC', Georgia, serif;
      font-weight: 500;
      letter-spacing: -0.01em;
    }

    .material-symbols-outlined {
      font-family: 'Material Symbols Outlined';
      font-weight: normal;
      font-style: normal;
      line-height: 1;
      letter-spacing: normal;
      text-transform: none;
      display: inline-block;
      white-space: nowrap;
      word-wrap: normal;
      direction: ltr;
      font-variation-settings: 'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24;
      /* The ligature names are English words. Until the font arrives they
         would render as the literal text "beach_access", so the glyph stays
         transparent and reserves its box instead. */
      color: transparent;
    }
    .fonts-ready .material-symbols-outlined { color: inherit; }

    ::-webkit-scrollbar { width: 6px; height: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
      background: var(--color-outline-variant);
      border-radius: 3px;
    }

    /* --- Sidebar ------------------------------------------------------- */
    aside {
      position: fixed; left: 0; top: 0; bottom: 0; width: 272px; z-index: 50;
      background: var(--color-surface-low);
      border-right: 1px solid var(--color-border-subtle);
      display: flex; flex-direction: column; padding-top: 44px;
    }
    .brand { padding: 0 32px; margin-bottom: 48px; display: flex; flex-direction: column; gap: 4px; }
    .brand-name { font-size: 1.5rem; color: var(--color-primary); }
    .brand-sub {
      font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.18em;
      color: var(--color-secondary); font-weight: 600;
    }
    .rail { flex: 1; padding: 0 32px; display: flex; flex-direction: column; gap: 22px; overflow-y: auto; }
    .rail-link {
      display: flex; flex-direction: column; gap: 3px; cursor: pointer;
      background: none; border: none; text-align: left; padding: 0;
      color: var(--color-on-surface-variant); font: inherit;
    }
    .rail-num {
      font-size: 0.62rem; letter-spacing: 0.22em; text-transform: uppercase;
      color: var(--color-on-surface-variant); opacity: 0.7;
    }
    .rail-label { font-size: 0.95rem; }
    .rail-link:hover .rail-label { color: var(--color-primary); }
    .rail-link.active { color: var(--color-primary); font-weight: 600; }
    .rail-link.active .rail-num { color: var(--color-secondary); opacity: 1; }

    .rail-foot {
      padding: 28px 32px; margin-top: auto;
      border-top: 1px solid var(--color-border-subtle);
      display: flex; flex-direction: column; gap: 3px;
    }
    .rail-foot .who { font-size: 0.85rem; color: var(--color-primary); font-weight: 500; }
    .rail-foot .what { font-size: 0.72rem; color: var(--color-on-surface-variant); }

    /* --- Header -------------------------------------------------------- */
    .shell { padding-left: 272px; }
    header {
      position: fixed; top: 0; left: 272px; right: 0; height: 76px; z-index: 40;
      background: color-mix(in srgb, var(--bg-background) 82%, transparent);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
      border-bottom: 1px solid var(--color-border-subtle);
      display: flex; align-items: center; justify-content: space-between;
      gap: 16px; padding: 0 32px;
    }
    .live { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
    .dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--color-secondary);
      box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-secondary) 60%, transparent);
      animation: breathe 3.5s ease-in-out infinite;
    }
    @keyframes breathe {
      0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-secondary) 55%, transparent); }
      50% { box-shadow: 0 0 0 5px transparent; }
    }
    .live-text {
      font-size: 0.68rem; letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--color-on-surface-variant); font-weight: 600;
    }
    .head-right { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; justify-content: flex-end; }
    .sep { width: 1px; height: 20px; background: var(--color-border-subtle); }

    .badge {
      font-size: 0.68rem; padding: 4px 11px; border-radius: 999px; font-weight: 600;
      background: var(--color-secondary-container);
      color: var(--color-on-secondary-container);
      border: 1px solid var(--color-border-subtle);
      white-space: nowrap;
    }
    .build-badge {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      letter-spacing: 0.02em; text-decoration: none; cursor: help;
    }
    .build-badge:hover { background: var(--color-surface-highest); }
    /* Clay, not blue: "running my uncommitted edits" is the state a developer
       most needs to notice, and it must not read as a clean deploy. */
    .build-badge-dirty {
      background: var(--color-notice-soft); color: var(--color-notice);
      border-color: color-mix(in srgb, var(--color-notice) 35%, transparent);
    }
    .build-badge-dirty:hover { background: color-mix(in srgb, var(--color-notice) 22%, transparent); }
    .build-badge-unknown {
      background: transparent; color: var(--color-on-surface-variant);
      border-color: var(--color-outline-variant);
    }

    select.lang, .icon-btn, .ghost-btn {
      background: var(--color-surface-low); color: var(--color-on-surface);
      border: 1px solid var(--color-border-subtle);
      border-radius: 999px; font: inherit; font-size: 0.75rem;
      padding: 6px 12px; cursor: pointer;
    }
    select.lang:focus, .icon-btn:focus-visible, .ghost-btn:focus-visible {
      outline: none; border-color: var(--color-secondary);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-secondary) 22%, transparent);
    }
    .icon-btn {
      padding: 7px; display: inline-flex; align-items: center; justify-content: center;
      color: var(--color-on-surface-variant); background: transparent; border-color: transparent;
    }
    .icon-btn:hover { background: var(--color-surface-container); color: var(--color-primary); }
    .ghost-btn:hover { background: var(--color-surface-container); color: var(--color-primary); }
    .ghost-btn.danger { color: var(--color-danger); border-color: color-mix(in srgb, var(--color-danger) 35%, transparent); }
    .ghost-btn.danger:hover { background: var(--color-danger-soft); }

    .solid-btn {
      background: var(--color-primary); color: var(--color-on-primary);
      border: 1px solid var(--color-primary); border-radius: 999px;
      font: inherit; font-size: 0.78rem; font-weight: 600;
      padding: 8px 18px; cursor: pointer;
      display: inline-flex; align-items: center; gap: 7px;
    }
    .solid-btn:hover { background: var(--color-primary-container); border-color: var(--color-primary-container); color: #fff; }
    html.dark .solid-btn:hover { color: var(--color-primary); }
    .solid-btn:disabled { opacity: 0.55; cursor: not-allowed; }

    .who-chip {
      display: flex; align-items: center; gap: 8px; font-size: 0.75rem;
      background: var(--color-surface-low); border: 1px solid var(--color-border-subtle);
      border-radius: 999px; padding: 5px 12px; color: var(--color-on-surface-variant);
    }
    .who-chip strong { color: var(--color-primary); font-weight: 600; }

    .arch {
      display: flex; align-items: center; gap: 9px;
      background: var(--color-surface-low); border: 1px solid var(--color-border-subtle);
      border-radius: 999px; padding: 4px 12px;
    }
    .arch-label { font-size: 0.68rem; font-weight: 600; color: var(--color-on-surface-variant); }
    .switch { position: relative; display: inline-block; width: 34px; height: 19px; flex-shrink: 0; }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute; inset: 0; cursor: pointer; border-radius: 999px;
      background: var(--color-surface-highest); border: 1px solid var(--color-outline-variant);
      transition: background-color 0.3s ease, border-color 0.3s ease;
    }
    .slider:before {
      content: ""; position: absolute; height: 11px; width: 11px; left: 3px; bottom: 3px;
      border-radius: 50%; background: var(--color-on-surface-variant);
      transition: transform 0.3s ease, background-color 0.3s ease;
    }
    .switch input:checked + .slider { background: var(--color-secondary); border-color: var(--color-secondary); }
    .switch input:checked + .slider:before { transform: translateX(15px); background: var(--color-surface-lowest); }
    .switch input:focus-visible + .slider { box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-secondary) 25%, transparent); }

    /* --- Workspace ------------------------------------------------------ */
    main { padding-top: 76px; min-height: 100vh; background: var(--bg-background); }
    .inner { max-width: 1440px; margin: 0 auto; padding: 44px 32px 32px; display: flex; flex-direction: column; gap: 40px; }

    .hero { display: flex; flex-direction: column; gap: 14px; max-width: 720px; }
    .hero-eyebrow {
      font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase;
      color: var(--color-secondary); font-weight: 700;
    }
    .hero-title { font-size: 2.35rem; color: var(--color-primary); line-height: 1.15; }
    .hero-desc { font-size: 0.95rem; color: var(--color-on-surface-variant); line-height: 1.75; }
    .divider { height: 1px; background: var(--color-outline); opacity: 0.18; }

    .grid { display: grid; grid-template-columns: minmax(0, 4fr) minmax(0, 8fr); gap: 28px; align-items: start; }
    .col-head { font-size: 1.1rem; color: var(--color-primary); margin-bottom: 16px; }

    .card {
      position: relative; width: 100%; text-align: left; overflow: hidden;
      background: var(--color-surface-low); border: 1px solid var(--color-border-subtle);
      border-radius: 12px; padding: 16px 18px; cursor: pointer; font: inherit;
      display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px;
    }
    .card:hover { background: var(--color-surface-container); }
    .card:before {
      content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
      background: var(--color-secondary);
      transform: scaleY(0); transform-origin: top; transition: transform 0.45s ease;
    }
    .card:hover:before, .card:focus-visible:before { transform: scaleY(1); }
    .card:focus-visible { outline: none; border-color: var(--color-secondary); }
    .card .material-symbols-outlined { font-size: 22px; color: var(--color-secondary); }
    .card-title { font-size: 0.95rem; color: var(--color-primary); font-weight: 500; }
    .card-desc { font-size: 0.8rem; color: var(--color-on-surface-variant); line-height: 1.5; }

    .panel {
      display: flex; flex-direction: column; overflow: hidden;
      background: var(--color-surface-lowest);
      border: 1px solid var(--color-border-subtle);
      border-radius: 14px; box-shadow: var(--shadow-soft);
      height: calc(100vh - 250px); min-height: 560px;
    }
    .panel-head {
      height: 62px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between;
      padding: 0 22px; background: var(--color-surface-low);
      border-bottom: 1px solid var(--color-border-subtle);
    }
    .panel-head .who-line { display: flex; align-items: center; gap: 12px; }
    .avatar {
      width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      background: var(--color-secondary-container); color: var(--color-on-secondary-container);
    }
    .avatar .material-symbols-outlined { font-size: 18px; }
    .avatar.user { background: var(--color-primary); color: var(--color-on-primary); }
    .panel-title { font-size: 0.95rem; color: var(--color-primary); }
    .panel-status { font-size: 0.66rem; letter-spacing: 0.16em; color: var(--color-secondary); font-weight: 700; }

    .stream { flex: 1; overflow-y: auto; padding: 24px 22px; display: flex; flex-direction: column; gap: 22px; }
    .day {
      display: flex; align-items: center; justify-content: center; position: relative;
      font-size: 0.64rem; letter-spacing: 0.16em; font-weight: 700; color: var(--color-outline);
    }
    .day:before { content: ""; position: absolute; inset-inline: 0; height: 1px; background: var(--color-outline-variant); opacity: 0.4; }
    .day span { position: relative; background: var(--color-surface-lowest); padding: 0 14px; }

    .msg { display: flex; align-items: flex-start; gap: 14px; }
    .msg.user { flex-direction: row-reverse; }
    .msg-body { display: flex; flex-direction: column; gap: 6px; max-width: 84%; min-width: 0; }
    .msg.user .msg-body { align-items: flex-end; }

    /* The agent speaks in the page's own voice - a hairline rule rather than a
       bubble, so a grounded policy answer reads as a document and not as chat
       chrome. The employee gets the bubble; the asymmetry is the point. */
    .bubble {
      font-size: 0.9rem; line-height: 1.7; white-space: pre-wrap; word-break: break-word;
      color: var(--color-on-surface);
    }
    .msg.agent .bubble { position: relative; padding-left: 16px; }
    .msg.agent .bubble:before {
      content: ""; position: absolute; left: 0; top: 2px; bottom: 2px; width: 2px;
      border-radius: 2px; background: var(--color-secondary-fixed-dim);
    }
    .msg.user .bubble {
      background: var(--color-surface-high); padding: 11px 16px;
      border-radius: 16px; border-top-right-radius: 4px;
    }
    .meta { display: flex; gap: 7px; flex-wrap: wrap; font-size: 0.64rem; color: var(--color-on-surface-variant); }
    .tag {
      background: var(--color-surface-container); padding: 2px 8px; border-radius: 5px;
      letter-spacing: 0.04em; border: 1px solid var(--color-border-subtle);
    }
    .citations {
      margin-top: 10px; padding-top: 10px; font-size: 0.8rem;
      border-top: 1px solid var(--color-border-subtle); line-height: 1.6;
    }
    .citations a { color: var(--color-secondary); text-decoration: underline; text-underline-offset: 3px; }
    .citations a:hover { color: var(--color-primary); }

    .fail-fast {
      border-left-color: var(--color-danger) !important;
      background: var(--color-danger-soft); padding: 12px 16px; border-radius: 10px;
    }
    .msg.agent .fail-fast:before { background: var(--color-danger); }

    .inspector {
      margin-top: 12px; padding: 10px 14px; font-size: 0.76rem; line-height: 1.6;
      background: var(--color-surface-low); border: 1px solid var(--color-border-subtle);
      border-radius: 10px; color: var(--color-on-surface-variant);
    }
    .inspector summary {
      cursor: pointer; font-weight: 600; color: var(--color-secondary);
      display: flex; align-items: center; gap: 8px; user-select: none; flex-wrap: wrap;
    }
    .inspector summary:hover { color: var(--color-primary); }
    .inspector code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.74rem; color: var(--color-primary);
    }

    .typing {
      display: none; padding: 0 22px 10px; font-size: 0.8rem;
      color: var(--color-on-surface-variant); font-style: italic;
    }

    .composer { flex-shrink: 0; padding: 14px 16px; border-top: 1px solid var(--color-border-subtle); background: var(--color-surface-lowest); }
    .composer-inner {
      display: flex; align-items: center; gap: 6px; padding: 5px 8px 5px 14px;
      background: var(--color-surface-container); border-radius: 12px;
      border: 1px solid transparent;
    }
    .composer-inner:focus-within { border-color: var(--color-secondary); }
    .composer input[type="text"] {
      flex: 1; min-width: 0; background: transparent; border: none; outline: none;
      color: var(--color-primary); font: inherit; font-size: 0.9rem; height: 38px;
    }
    .composer input::placeholder { color: var(--color-outline); }
    .composer input:disabled { cursor: not-allowed; }
    .send-btn {
      flex-shrink: 0; width: 38px; height: 38px; border-radius: 10px; border: none;
      background: var(--color-primary); color: var(--color-on-primary);
      cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
    }
    .send-btn:hover { background: var(--color-primary-container); color: #fff; }
    html.dark .send-btn:hover { color: var(--color-primary); }
    .send-btn .material-symbols-outlined { font-size: 19px; }

    /* --- Modals --------------------------------------------------------- */
    .overlay {
      display: none; position: fixed; inset: 0; z-index: 1000;
      background: color-mix(in srgb, var(--bg-background) 55%, rgba(0, 0, 0, 0.55));
      backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
      align-items: center; justify-content: center; padding: 20px;
    }
    .modal {
      width: 100%; max-width: 500px; padding: 26px;
      background: var(--color-surface-lowest);
      border: 1px solid var(--color-border-subtle);
      border-radius: 16px; box-shadow: var(--shadow-soft);
      max-height: 90vh; overflow-y: auto;
    }
    .modal h2 { font-size: 1.15rem; color: var(--color-primary); margin-bottom: 8px; }
    .modal-desc { font-size: 0.82rem; color: var(--color-on-surface-variant); line-height: 1.6; margin-bottom: 20px; }
    .modal-desc strong { color: var(--color-primary); font-weight: 600; }
    .field { margin-bottom: 16px; }
    .field label { display: block; font-size: 0.76rem; color: var(--color-on-surface-variant); margin-bottom: 7px; }
    .field input {
      width: 100%; padding: 10px 13px; font: inherit; font-size: 0.88rem;
      background: var(--color-surface-low); color: var(--color-on-surface);
      border: 1px solid var(--color-outline-variant); border-radius: 9px; outline: none;
    }
    .field input:focus { border-color: var(--color-secondary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-secondary) 18%, transparent); }
    .secret-wrap { position: relative; display: flex; align-items: center; }
    .secret-wrap input { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; padding-right: 42px; }
    .peek {
      position: absolute; right: 8px; background: transparent; border: none;
      color: var(--color-on-surface-variant); cursor: pointer; padding: 5px;
      display: inline-flex; align-items: center;
    }
    .peek:hover { color: var(--color-primary); }
    .peek .material-symbols-outlined { font-size: 18px; }
    .hint { font-size: 0.74rem; color: var(--color-on-surface-variant); margin-top: 7px; line-height: 1.55; }
    .status-box { display: none; padding: 9px 13px; border-radius: 9px; font-size: 0.8rem; margin-top: 14px; line-height: 1.5; }
    .status-box.info { display: block; background: var(--color-secondary-container); color: var(--color-on-secondary-container); }
    .status-box.warn { display: block; background: var(--color-notice-soft); color: var(--color-notice); }
    .status-box.err { display: block; background: var(--color-danger-soft); color: var(--color-danger); }
    .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 22px; }
    .mono-pill {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.82rem;
      color: var(--color-success); background: var(--color-success-soft);
      border: 1px solid color-mix(in srgb, var(--color-success) 30%, transparent);
      padding: 4px 11px; border-radius: 7px; display: inline-block; word-break: break-all;
    }

    /* --- Narrow screens -------------------------------------------------- */
    @media (max-width: 1023px) {
      aside {
        position: static; width: auto; inset: auto; padding-top: 20px;
        border-right: none; border-bottom: 1px solid var(--color-border-subtle);
      }
      .brand { margin-bottom: 18px; padding: 0 20px; }
      .rail { flex-direction: row; gap: 20px; padding: 0 20px 14px; overflow-x: auto; }
      .rail-link { flex-shrink: 0; }
      .rail-foot { display: none; }
      .shell { padding-left: 0; }
      header { position: sticky; top: 0; left: auto; height: auto; padding: 12px 20px; flex-wrap: wrap; }
      main { padding-top: 0; }
      .inner { padding: 28px 20px; gap: 28px; }
      .grid { grid-template-columns: minmax(0, 1fr); }
      .hero-title { font-size: 1.8rem; }
      .panel { height: auto; min-height: 520px; }
    }
  </style>
</head>

<body>
  <aside>
    <div class="brand">
      <span class="brand-name serif">Zenith Portal</span>
      <span class="brand-sub" data-i18n="brand_sub">HR &amp; IT Solution</span>
    </div>
    <nav class="rail" id="rail"></nav>
    <div class="rail-foot">
      <span class="who" id="railWho" data-i18n="rail_guest">Not signed in</span>
      <span class="what" id="railWhat" data-i18n="rail_guest_sub">Connect WorkWeek to begin</span>
    </div>
  </aside>

  <div class="shell">
    <header>
      <div class="live">
        <span class="dot"></span>
        <span class="live-text" data-i18n="status_online">System online</span>
        __BUILD_BADGE__
      </div>

      <div class="head-right">
        <select class="lang" id="langSelect" onchange="changeLanguage(this.value)" data-i18n-title="lang_title">
          <option value="en-US">English (US)</option>
          <option value="zh-TW">繁體中文 (TW)</option>
          <option value="ja">日本語</option>
          <option value="ko">한국어</option>
          <option value="id">Bahasa Indonesia</option>
        </select>

        <button class="icon-btn" onclick="toggleTheme()" data-i18n-title="theme_title" aria-label="Toggle theme">
          <span class="material-symbols-outlined" id="themeIcon">dark_mode</span>
        </button>

        <span class="sep"></span>

        <div class="arch" data-i18n-title="arch_title">
          <span class="arch-label" data-i18n="arch_label">Architecture</span>
          <label class="switch">
            <input type="checkbox" id="registryToggle" onchange="handleRegistryToggle(this.checked)">
            <span class="slider"></span>
          </label>
          <span class="badge" id="registryBadge" data-i18n="arch_dev">Dev</span>
        </div>

        <span class="sep"></span>

        <div id="unauthControls">
          <button class="solid-btn" onclick="openLoginModal()">
            <span class="material-symbols-outlined" style="font-size:16px">key</span>
            <span data-i18n="btn_signin">Sign in &amp; connect</span>
          </button>
        </div>

        <div id="authControls" style="display:none; align-items:center; gap:10px;">
          <div class="who-chip">
            <span class="material-symbols-outlined" style="font-size:15px">person</span>
            <strong id="userDisplayName">User</strong>
            <span id="userEmailSpan">(email)</span>
            <span class="badge" id="userEmpBadge">EMP-509</span>
          </div>
          <button class="ghost-btn" onclick="openTokenModal()" data-i18n-title="btn_token_title" data-i18n="btn_token">Token</button>
          <button class="ghost-btn" onclick="openLoginModal()" data-i18n-title="btn_switch_title" data-i18n="btn_switch">Switch</button>
          <button class="ghost-btn danger" onclick="logout()" data-i18n="btn_signout">Sign out</button>
        </div>
      </div>
    </header>

    <main>
      <div class="inner">
        <div class="hero">
          <span class="hero-eyebrow" data-i18n="hero_eyebrow">HR &amp; IT intelligent platform</span>
          <h1 class="hero-title serif" data-i18n="hero_title">HR intelligent solution</h1>
          <p class="hero-desc" data-i18n="hero_desc">Welcome to the enterprise HR &amp; IT self-service assistant.</p>
        </div>

        <div class="divider"></div>

        <div class="grid">
          <section>
            <h2 class="col-head serif" data-i18n="modules_heading">Service modules</h2>
            <div id="actionList"></div>
          </section>

          <section class="panel">
            <div class="panel-head">
              <div class="who-line">
                <div class="avatar"><span class="material-symbols-outlined">smart_toy</span></div>
                <span class="panel-title serif" data-i18n="chat_title">AI assistant</span>
              </div>
              <span class="panel-status" id="chatStatus" data-i18n="chat_ready">READY</span>
            </div>

            <div class="stream" id="chatWindow">
              <div class="day"><span data-i18n="chat_today">TODAY</span></div>
            </div>

            <div class="typing" id="typingIndicator" data-i18n="typing">Reasoning and querying FastMCP...</div>

            <form class="composer" id="chatForm" onsubmit="event.preventDefault(); sendMessage();">
              <div class="composer-inner">
                <input type="text" id="userInput" autocomplete="off" disabled>
                <button type="submit" class="send-btn" data-i18n-title="send">
                  <span class="material-symbols-outlined">arrow_upward</span>
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </main>
  </div>

  <div class="overlay" id="loginModal">
    <div class="modal">
      <h2 class="serif" data-i18n="login_title">Sign in with corporate email</h2>
      <div class="modal-desc" data-i18n="login_desc">Personal FastMCP tokens are resolved automatically from Google Cloud Secret Manager.</div>
      <div class="field">
        <label for="loginEmail" data-i18n="login_email_label">Google corporate email</label>
        <input type="text" id="loginEmail" placeholder="your-ldap@google.com" autocomplete="off" data-i18n-placeholder="login_email_ph">
      </div>
      <div id="tokenRegistrationGroup" style="display:none;">
        <div class="field">
          <label for="loginToken" data-i18n="login_token_label">Personal FastMCP token - first-time setup</label>
          <div class="secret-wrap">
            <input type="password" id="loginToken" placeholder="mcp_..." autocomplete="off">
            <button type="button" class="peek" onclick="toggleTokenVis()" data-i18n-title="peek_title">
              <span class="material-symbols-outlined">visibility</span>
            </button>
          </div>
          <div class="hint" data-i18n="login_token_hint">Paste your token once; it is stored in Secret Manager for future logins.</div>
        </div>
      </div>
      <div class="status-box" id="loginStatus"></div>
      <div class="modal-actions">
        <button class="ghost-btn" onclick="closeLoginModal()" data-i18n="cancel">Cancel</button>
        <button class="solid-btn" id="btnDoLogin" onclick="handleConnect()" data-i18n="login_connect">Connect &amp; start</button>
      </div>
    </div>
  </div>

  <div class="overlay" id="tokenModal">
    <div class="modal">
      <h2 class="serif" data-i18n="token_title">FastMCP token settings</h2>
      <div class="modal-desc" data-i18n="token_desc">Credentials are held in Google Cloud Secret Manager and loaded by the Cloud Run service account.</div>
      <div class="field">
        <label data-i18n="token_account_label">Authenticated account</label>
        <div id="tokenModalEmail" style="color:var(--color-primary); font-weight:600; font-size:0.88rem; padding:3px 0;"></div>
      </div>
      <div class="field">
        <label data-i18n="token_active_label">Active Secret Manager token</label>
        <div><span class="mono-pill" id="tokenModalCurrent"></span></div>
      </div>
      <div class="field">
        <label for="tokenUpdateInput" data-i18n="token_update_label">Update personal FastMCP token</label>
        <div class="secret-wrap">
          <input type="password" id="tokenUpdateInput" placeholder="mcp_..." autocomplete="off">
          <button type="button" class="peek" onclick="toggleTokenUpdateVis()" data-i18n-title="peek_title">
            <span class="material-symbols-outlined">visibility</span>
          </button>
        </div>
        <div class="hint" data-i18n="token_update_hint">Saving writes a new secret version and refreshes your live session.</div>
      </div>
      <div class="status-box" id="tokenUpdateStatus"></div>
      <div class="modal-actions">
        <button class="ghost-btn" onclick="closeTokenModal()" data-i18n="close">Close</button>
        <button class="solid-btn" id="btnDoUpdateToken" onclick="handleUpdateToken()" data-i18n="token_save">Update in Secret Manager</button>
      </div>
    </div>
  </div>

  <script>
    /* =====================================================================
       Translations.

       `en-US` is the fallback for every other locale, so it has to stay
       complete; `t(key)` falls back to it and then to the key itself, which
       makes an untranslated string visible in review rather than blank in
       production.

       The quick actions carry a translated *prompt* as well as a translated
       label. The agent answers in the language it was asked in, so sending
       English text from a Korean button would return a Korean speaker an
       English receipt - the exact defect the outbound localisation work was
       meant to close.
       ===================================================================== */
    const I18N = __I18N__;

    //: Nav rail. `all` is a filter that hides nothing, so it is a category
    //  like any other rather than a special case in `filterCategory`.
    const CATEGORIES = [
      { id: 'all', key: 'nav_all' },
      { id: 'hr', key: 'nav_hr' },
      { id: 'itsm', key: 'nav_itsm' },
      { id: 'policy', key: 'nav_policy' },
      { id: 'cross', key: 'nav_cross' }
    ];

    //: The quick actions, rendered from data rather than written out as
    //  markup - five locales times fifteen buttons is not something to
    //  maintain by hand, and the list has to be rebuilt on every language
    //  change anyway.
    const ACTIONS = [
      { cat: 'hr', icon: 'beach_access', k: 'a_balance' },
      { cat: 'hr', icon: 'flight_takeoff', k: 'a_vacation' },
      { cat: 'hr', icon: 'account_tree', k: 'a_manager' },
      { cat: 'hr', icon: 'history', k: 'a_history' },
      { cat: 'itsm', icon: 'vpn_lock', k: 'a_vpn' },
      { cat: 'itsm', icon: 'laptop_chromebook', k: 'a_laptop' },
      { cat: 'itsm', icon: 'key', k: 'a_access' },
      { cat: 'itsm', icon: 'confirmation_number', k: 'a_tickets' },
      { cat: 'itsm', icon: 'search', k: 'a_status' },
      { cat: 'policy', icon: 'menu_book', k: 'a_bereave' },
      { cat: 'policy', icon: 'home_work', k: 'a_remote' },
      { cat: 'policy', icon: 'child_care', k: 'a_parental' },
      { cat: 'cross', icon: 'desktop_windows', k: 'a_monitor' },
      { cat: 'cross', icon: 'medical_services', k: 'a_medical' },
      { cat: 'cross', icon: 'badge', k: 'a_london' }
    ];

    let locale = 'en-US';
    let activeCat = 'all';

    function t(key) {
      const table = I18N[locale] || I18N['en-US'];
      if (table[key] !== undefined) { return table[key]; }
      if (I18N['en-US'][key] !== undefined) { return I18N['en-US'][key]; }
      return key;
    }

    function fill(key, values) {
      let out = t(key);
      Object.keys(values || {}).forEach(function (name) {
        out = out.split('{' + name + '}').join(values[name]);
      });
      return out;
    }

    // --- Language -------------------------------------------------------

    function detectLocale() {
      const saved = localStorage.getItem('zenith_locale');
      if (saved && I18N[saved]) { return saved; }
      const wanted = navigator.languages || [navigator.language || 'en-US'];
      for (const raw of wanted) {
        if (!raw) { continue; }
        if (I18N[raw]) { return raw; }
        // `zh-Hant-TW`, `ja-JP` and `ko-KR` should all find a home; matching
        // the base subtag is what makes that work without listing variants.
        const base = raw.split('-')[0];
        if (base === 'zh') { return 'zh-TW'; }
        const hit = Object.keys(I18N).find(function (code) { return code.split('-')[0] === base; });
        if (hit) { return hit; }
      }
      return 'en-US';
    }

    function changeLanguage(code) {
      locale = I18N[code] ? code : 'en-US';
      try { localStorage.setItem('zenith_locale', locale); } catch (e) { /* private mode */ }
      applyLanguage();
    }

    function applyLanguage() {
      document.documentElement.lang = locale;
      document.getElementById('langSelect').value = locale;

      document.querySelectorAll('[data-i18n]').forEach(function (el) {
        el.textContent = t(el.getAttribute('data-i18n'));
      });
      document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
        el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
      });
      document.querySelectorAll('[data-i18n-title]').forEach(function (el) {
        el.title = t(el.getAttribute('data-i18n-title'));
      });

      renderRail();
      renderActions();

      // These four are driven by state rather than by a static key, so the
      // sweep above cannot reach them.
      userInput.placeholder = currentUser ? t('input_ready') : t('input_locked');
      document.getElementById('registryBadge').textContent =
        isRegistryMode ? t('arch_prod') : t('arch_dev');
      document.getElementById('btnDoLogin').textContent = t('login_connect');
      renderRailFoot();
    }

    // --- Theme ----------------------------------------------------------

    function toggleTheme() {
      const dark = document.documentElement.classList.toggle('dark');
      try { localStorage.setItem('zenith_theme', dark ? 'dark' : 'light'); } catch (e) { /* private mode */ }
      syncThemeIcon();
    }

    function syncThemeIcon() {
      const dark = document.documentElement.classList.contains('dark');
      // The icon names the destination, not the current state: in ink mode the
      // button offers you the washi paper back.
      document.getElementById('themeIcon').textContent = dark ? 'light_mode' : 'dark_mode';
    }

    // --- Rail & actions --------------------------------------------------

    function renderRail() {
      const rail = document.getElementById('rail');
      rail.innerHTML = '';
      CATEGORIES.forEach(function (cat, i) {
        const btn = document.createElement('button');
        btn.className = 'rail-link' + (cat.id === activeCat ? ' active' : '');
        btn.onclick = function () { filterCategory(cat.id); };
        const num = document.createElement('span');
        num.className = 'rail-num';
        num.textContent = String(i + 1).padStart(2, '0');
        const label = document.createElement('span');
        label.className = 'rail-label';
        label.textContent = t(cat.key);
        btn.appendChild(num);
        btn.appendChild(label);
        rail.appendChild(btn);
      });
    }

    function renderActions() {
      const host = document.getElementById('actionList');
      host.innerHTML = '';
      ACTIONS.filter(function (a) { return activeCat === 'all' || a.cat === activeCat; })
        .forEach(function (a) {
          const card = document.createElement('button');
          card.className = 'card';
          card.type = 'button';
          card.onclick = function () { sendQuick(t(a.k + '_p')); };

          const icon = document.createElement('span');
          icon.className = 'material-symbols-outlined';
          icon.textContent = a.icon;

          const title = document.createElement('span');
          title.className = 'card-title';
          title.textContent = t(a.k + '_l');

          const desc = document.createElement('span');
          desc.className = 'card-desc';
          desc.textContent = t(a.k + '_d');

          card.appendChild(icon);
          card.appendChild(title);
          card.appendChild(desc);
          host.appendChild(card);
        });
    }

    function filterCategory(cat) {
      activeCat = cat;
      renderRail();
      renderActions();
    }

    // --- Auth ------------------------------------------------------------

    const chatWindow = document.getElementById('chatWindow');
    const userInput = document.getElementById('userInput');
    const typingIndicator = document.getElementById('typingIndicator');

    let sessionToken = localStorage.getItem('hr_agent_session_token');
    let currentUser = null;
    let currentMaskedToken = null;
    let isRegistryMode = false;

    function setStatus(el, kind, text) {
      el.className = 'status-box ' + kind;
      el.textContent = text;
    }

    function clearStatus(el) {
      el.className = 'status-box';
      el.textContent = '';
    }

    function openLoginModal() {
      const emailInput = document.getElementById('loginEmail');
      const tokenInput = document.getElementById('loginToken');
      const btn = document.getElementById('btnDoLogin');
      clearStatus(document.getElementById('loginStatus'));
      document.getElementById('tokenRegistrationGroup').style.display = 'none';
      btn.textContent = t('login_connect');

      emailInput.value = currentUser
        ? currentUser.email
        : (localStorage.getItem('hr_agent_custom_email') || '');
      tokenInput.value = localStorage.getItem('hr_agent_custom_mcp_token') || '';
      document.getElementById('loginModal').style.display = 'flex';
    }

    function closeLoginModal() {
      document.getElementById('loginModal').style.display = 'none';
    }

    function toggleTokenVis() {
      const el = document.getElementById('loginToken');
      el.type = el.type === 'password' ? 'text' : 'password';
    }

    function toggleTokenUpdateVis() {
      const el = document.getElementById('tokenUpdateInput');
      el.type = el.type === 'password' ? 'text' : 'password';
    }

    function openTokenModal() {
      clearStatus(document.getElementById('tokenUpdateStatus'));
      document.getElementById('tokenUpdateInput').value = '';
      if (currentUser) {
        document.getElementById('tokenModalEmail').textContent =
          currentUser.name + ' (' + currentUser.email + ')';
        document.getElementById('tokenModalCurrent').textContent =
          currentMaskedToken || t('token_active_fallback');
      }
      document.getElementById('tokenModal').style.display = 'flex';
    }

    function closeTokenModal() {
      document.getElementById('tokenModal').style.display = 'none';
    }

    async function handleUpdateToken() {
      const input = document.getElementById('tokenUpdateInput');
      const statusDiv = document.getElementById('tokenUpdateStatus');
      const btn = document.getElementById('btnDoUpdateToken');
      const token = input.value.trim();

      if (!token) {
        setStatus(statusDiv, 'err', t('token_need'));
        return;
      }

      btn.disabled = true;
      setStatus(statusDiv, 'info', t('token_updating'));

      try {
        const res = await fetch('/auth/update-mcp-token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + sessionToken
          },
          body: JSON.stringify({ mcp_token: token })
        });
        const data = await res.json();
        btn.disabled = false;

        if (res.ok && data.success && data.token) {
          sessionToken = data.token;
          localStorage.setItem('hr_agent_session_token', sessionToken);
          localStorage.setItem('hr_agent_custom_mcp_token', token);
          currentUser = data.user;
          currentMaskedToken = data.token_masked;
          renderAuth(currentUser);
          closeTokenModal();
          appendMessage(fill('msg_token_updated', { id: currentUser.employee_id }), false);
        } else {
          setStatus(statusDiv, 'err', data.detail || t('token_failed'));
        }
      } catch (err) {
        btn.disabled = false;
        setStatus(statusDiv, 'err', t('token_network'));
      }
    }

    async function handleConnect() {
      const emailInput = document.getElementById('loginEmail');
      const tokenInput = document.getElementById('loginToken');
      const statusDiv = document.getElementById('loginStatus');
      const tokenGroup = document.getElementById('tokenRegistrationGroup');
      const btn = document.getElementById('btnDoLogin');

      const email = emailInput.value.trim();
      const token = tokenInput.value.trim();

      if (!email) {
        setStatus(statusDiv, 'err', t('login_need_email'));
        return;
      }

      setStatus(statusDiv, 'info', t('login_resolving'));
      btn.disabled = true;

      try {
        const payload = { email: email };
        if (token) { payload.mcp_token = token; }

        const res = await fetch('/auth/quick-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        btn.disabled = false;

        if (data.needs_mcp_token) {
          tokenGroup.style.display = 'block';
          setStatus(statusDiv, 'warn', t('login_first_time'));
          btn.textContent = t('login_save_connect');
          return;
        }

        if (res.ok && data.success && data.token) {
          sessionToken = data.token;
          localStorage.setItem('hr_agent_session_token', sessionToken);
          localStorage.setItem('hr_agent_custom_email', email);
          if (token) { localStorage.setItem('hr_agent_custom_mcp_token', token); }
          currentUser = data.user;
          currentMaskedToken = data.token_masked || t('token_active_fallback');
          closeLoginModal();
          renderAuth(currentUser);
          appendMessage(
            fill('msg_connected', { name: currentUser.name, id: currentUser.employee_id }),
            false
          );
        } else {
          setStatus(statusDiv, 'err', data.detail || t('login_failed'));
        }
      } catch (err) {
        btn.disabled = false;
        setStatus(statusDiv, 'err', t('login_network'));
      }
    }

    async function checkAuth() {
      if (!sessionToken) { renderUnauth(); return; }
      try {
        const res = await fetch('/auth/me', {
          headers: { 'Authorization': 'Bearer ' + sessionToken }
        });
        const data = await res.json();
        if (data.authenticated && data.user) {
          currentUser = data.user;
          currentMaskedToken = data.token_masked;
          renderAuth(currentUser);
        } else {
          sessionToken = null;
          localStorage.removeItem('hr_agent_session_token');
          renderUnauth();
        }
      } catch (e) {
        renderUnauth();
      }
    }

    function renderRailFoot() {
      const who = document.getElementById('railWho');
      const what = document.getElementById('railWhat');
      if (currentUser) {
        who.textContent = currentUser.name;
        what.textContent = currentUser.employee_id;
      } else {
        who.textContent = t('rail_guest');
        what.textContent = t('rail_guest_sub');
      }
    }

    function renderAuth(user) {
      document.getElementById('unauthControls').style.display = 'none';
      document.getElementById('authControls').style.display = 'flex';
      document.getElementById('userDisplayName').textContent = user.name;
      document.getElementById('userEmailSpan').textContent = '(' + user.email + ')';
      document.getElementById('userEmpBadge').textContent = user.employee_id;
      userInput.disabled = false;
      userInput.placeholder = t('input_ready');
      renderRailFoot();
    }

    function renderUnauth() {
      document.getElementById('unauthControls').style.display = 'block';
      document.getElementById('authControls').style.display = 'none';
      userInput.disabled = true;
      userInput.placeholder = t('input_locked');
      renderRailFoot();
    }

    function logout() {
      sessionToken = null;
      currentUser = null;
      currentMaskedToken = null;
      localStorage.removeItem('hr_agent_session_token');
      localStorage.removeItem('hr_agent_custom_mcp_token');
      renderUnauth();
      appendMessage(t('msg_signed_out'), false);
    }

    function handleRegistryToggle(checked) {
      isRegistryMode = checked;
      document.getElementById('registryBadge').textContent =
        checked ? t('arch_prod') : t('arch_dev');
      appendMessage(checked ? t('msg_arch_prod') : t('msg_arch_dev'), false);
    }

    // --- Chat -------------------------------------------------------------

    function appendMessage(text, isUser, meta = null, citations = [], metadata = {}) {
      const row = document.createElement('div');
      row.className = 'msg ' + (isUser ? 'user' : 'agent');

      const avatar = document.createElement('div');
      avatar.className = 'avatar' + (isUser ? ' user' : '');
      const avatarIcon = document.createElement('span');
      avatarIcon.className = 'material-symbols-outlined';
      avatarIcon.textContent = isUser ? 'person' : 'smart_toy';
      avatar.appendChild(avatarIcon);

      const body = document.createElement('div');
      body.className = 'msg-body';

      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      // textContent, not innerHTML: the agent's reply is model output and may
      // contain a re-identified phone number or a policy quotation. Neither is
      // markup, and treating it as markup is how it becomes an injection.
      bubble.textContent = text;

      if (meta && meta.action === 'FAIL_FAST_REGISTRY_ERROR') {
        bubble.classList.add('fail-fast');
      }

      if (citations && citations.length > 0) {
        const cite = document.createElement('div');
        cite.className = 'citations';
        const label = document.createElement('strong');
        label.textContent = t('references') + ': ';
        cite.appendChild(label);
        citations.forEach(function (c, i) {
          if (i > 0) { cite.appendChild(document.createTextNode(', ')); }
          const a = document.createElement('a');
          a.href = (c && c.url) || '#';
          a.target = '_blank';
          a.rel = 'noopener';
          a.textContent = (c && c.title) || c;
          cite.appendChild(a);
        });
        bubble.appendChild(cite);
      }

      if (metadata && metadata.architecture === 'AGENT_REGISTRY_A2A_MCP') {
        bubble.appendChild(buildInspector(metadata));
      }

      body.appendChild(bubble);

      if (meta) {
        const metaRow = document.createElement('div');
        metaRow.className = 'meta';
        const intentTag = document.createElement('span');
        intentTag.className = 'tag';
        intentTag.textContent = meta.intent || 'AGENT';
        metaRow.appendChild(intentTag);
        if (meta.action) {
          const actionTag = document.createElement('span');
          actionTag.className = 'tag';
          actionTag.textContent = meta.action;
          metaRow.appendChild(actionTag);
        }
        body.appendChild(metaRow);
      }

      row.appendChild(avatar);
      row.appendChild(body);
      chatWindow.appendChild(row);
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function buildInspector(metadata) {
      const a2a = metadata.target_a2a_agent || {};
      const mcp = metadata.target_mcp_tools || {};
      const box = document.createElement('details');
      box.className = 'inspector';

      const summary = document.createElement('summary');
      const title = document.createElement('span');
      title.textContent = t('insp_title');
      const live = document.createElement('span');
      live.className = 'badge';
      live.textContent = t('insp_live');
      const timing = document.createElement('span');
      timing.style.cssText = 'margin-left:auto; font-size:0.7rem; opacity:0.8;';
      timing.textContent = t('insp_discovery') + ': ' + (metadata.discovery_latency_ms || 0)
        + 'ms | ' + t('insp_total') + ': ' + (metadata.total_latency_ms || 0) + 'ms';
      summary.appendChild(title);
      summary.appendChild(live);
      summary.appendChild(timing);
      box.appendChild(summary);

      const rows = document.createElement('div');
      rows.style.cssText = 'margin-top:9px; display:flex; flex-direction:column; gap:5px;';
      const entries = [
        [t('insp_agent'), (a2a.name || 'N/A') + ' (v' + (a2a.version || '0.1.0') + ')'],
        [t('insp_skills'), a2a.skills ? a2a.skills.join(', ') : 'N/A'],
        [t('insp_tools'), (mcp.tools_count || 0) + ' ' + t('insp_tools_unit')
          + ' (' + (mcp.server_path || 'work-week/mcp') + ')'],
        [t('insp_action'), metadata.resolved_action || 'N/A']
      ];
      entries.forEach(function (pair) {
        const line = document.createElement('div');
        const strong = document.createElement('strong');
        strong.textContent = pair[0] + ': ';
        const code = document.createElement('code');
        code.textContent = pair[1];
        line.appendChild(strong);
        line.appendChild(code);
        rows.appendChild(line);
      });

      const verified = document.createElement('div');
      verified.style.cssText = 'color:var(--color-success); font-size:0.72rem; margin-top:4px;';
      verified.textContent = t('insp_verified');
      rows.appendChild(verified);
      box.appendChild(rows);
      return box;
    }

    async function sendMessage() {
      if (!currentUser) { openLoginModal(); return; }
      const text = userInput.value.trim();
      if (!text) { return; }

      appendMessage(text, true);
      userInput.value = '';
      typingIndicator.style.display = 'block';

      const headers = { 'Content-Type': 'application/json' };
      if (sessionToken) { headers['Authorization'] = 'Bearer ' + sessionToken; }

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({
            employee_id: currentUser.employee_id,
            message: text,
            use_agent_registry: isRegistryMode
          })
        });
        const data = await res.json();
        typingIndicator.style.display = 'none';

        if (res.ok) {
          appendMessage(
            data.response, false,
            { intent: data.intent, action: data.action_performed },
            data.citations, data.processing_metadata
          );
        } else {
          appendMessage(t('msg_error') + (data.detail || t('msg_unable')), false);
        }
      } catch (err) {
        typingIndicator.style.display = 'none';
        appendMessage(t('msg_network'), false);
      }
    }

    function sendQuick(prompt) {
      if (!currentUser) { openLoginModal(); return; }
      userInput.value = prompt;
      sendMessage();
    }

    // --- Boot --------------------------------------------------------------

    window.addEventListener('DOMContentLoaded', function () {
      locale = detectLocale();
      syncThemeIcon();
      applyLanguage();
      appendMessage(t('welcome'), false, { intent: t('tag_ready') });
      checkAuth();
    });

    // Material Symbols renders its ligature names as plain English words until
    // the font arrives. The glyphs stay transparent until then, so a slow or
    // blocked fonts.googleapis.com costs icons rather than showing "beach_access".
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        document.body.classList.add('fonts-ready');
      });
      setTimeout(function () { document.body.classList.add('fonts-ready'); }, 3000);
    } else {
      document.body.classList.add('fonts-ready');
    }
  </script>
</body>
</html>"""


def render_page(build_badge_html: str) -> str:
    """The template with the two values only the server can supply filled in.

    The translation table is injected rather than written into the script so
    it can live in Python, where `tests/test_portal_ui.py` can assert that
    every locale is complete. A missing key is otherwise invisible until
    someone switches language in production and reads an English sentence.
    """
    payload = json.dumps(TRANSLATIONS, ensure_ascii=False)
    # `</script>` inside a JSON string would close the block early. No copy
    # contains one today; escaping the angle bracket means a translation added
    # later cannot turn itself into markup.
    payload = payload.replace("<", "\\u003c")
    return CHAT_UI_HTML.replace("__I18N__", payload).replace(
        "__BUILD_BADGE__", build_badge_html
    )
