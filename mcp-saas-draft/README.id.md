# Integrasi SaaS MCP & Alat Agen Google ADK (`mcp-saas-draft`)

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [繁體中文 (台灣)](README.zh-TW.md) | [Bahasa Indonesia](README.id.md)

---

## 📌 Ringkasan
Modul ini menyediakan integrasi **Model Context Protocol (MCP)** tingkat produksi yang menghubungkan agen **Google ADK (Agent Development Kit)** dan **Google GenAI (Gemini)** ke portal SaaS perusahaan (`https://mock-saas.aishprabhat.demo.altostrat.com/`).

Modul ini menghubungkan dua layanan mikro FastMCP Streamable HTTP secara langsung:
1. **WorkWeek HCM MCP**: Manajemen profil karyawan, saldo cuti tahunan & sakit real-time, pengajuan cuti, dan pembaruan kontak.
2. **ServiceImmediately ITSM MCP**: Pelacakan tiket dukungan IT, pembuatan insiden baru, penambahan komentar, dan transisi status siklus hidup.

---

## ⚡ Arsitektur Penting & Catatan Otentikasi

> [!IMPORTANT]
> **Mengapa `X-MCP-Token` wajib digunakan dan header standar `Authorization` TIDAK BOLEH dikirimkan:**
> - Portal SaaS dihosting di belakang infrastruktur Google Cloud.
> - Titik akhir FastMCP (`/work-week/mcp/` dan `/service-immediately/mcp/`) telah dikonfigurasi untuk **melewati Identity-Aware Proxy (IAP)**.
> - Namun, jika permintaan menyertakan header standar `Authorization`, **Google Frontend (GFE)** akan mencegat permintaan tersebut dan mencoba memvalidasinya sebagai Google OIDC JWT.
> - Jika Anda mengirimkan `Authorization: Bearer <mcp_token>`, GFE akan menolak permintaan dengan kesalahan `401 Invalid IAP credentials: Unable to parse JWT`.
> - **Solusi**: Kirimkan token Anda **hanya** melalui tajuk kustom `X-MCP-Token`:
>   ```http
>   X-MCP-Token: mcp_your_token_here
>   Accept: application/json
>   ```
>   **JANGAN PERNAH** menyertakan header `Authorization`.

### Titik Akhir (Endpoints)
- **Server WorkWeek**: `https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/`
- **Server ServiceImmediately**: `https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/`
- **Protokol Transportasi**: Stateless Streamable HTTP (JSON-RPC 2.0)

---

## 🛠️ Daftar Alat MCP yang Tersedia

### 📅 Alat WorkWeek HCM (`/work-week/mcp/`)
| Nama Alat | Parameter | Deskripsi |
| :--- | :--- | :--- |
| `get_current_employee_id` | *Tidak ada* | Mengambil ID karyawan dari sesi pengguna yang terotentikasi (contoh: `EMP-509`). |
| `get_employee_balances` | `employee_id` | Mengambil sisa saldo cuti tahunan dan cuti sakit (dalam hari). |
| `request_time_off` | `start_date`, `end_date`, `leave_type`, `days`, `employee_id` | Mengajukan cuti (Format tanggal: `YYYY-MM-DD`, jenis cuti: `'Vacation'` atau `'Sick'`). |
| `get_personal_info` | `employee_id` | Mengambil rincian kontak pribadi (alamat rumah dan nomor telepon). |
| `update_personal_info` | `address`, `phone`, `employee_id` | Memperbarui kontak pribadi (alamat minimal 5 karakter, format telepon E.164). |
| `get_leave_requests` | `employee_id` | Mengambil riwayat pengajuan cuti karyawan. |
| `cancel_leave_request` | `request_id`, `employee_id` | Membatalkan pengajuan cuti yang tertunda/disetujui dan mengembalikan hari cuti. |

### 🎫 Alat ServiceImmediately ITSM (`/service-immediately/mcp/`)
| Nama Alat | Parameter | Deskripsi |
| :--- | :--- | :--- |
| `list_tickets` | `employee_id` | Menampilkan semua tiket insiden yang diajukan oleh karyawan. |
| `create_ticket` | `category`, `short_description`, `priority`, `assignment_group`, `requested_by` | Membuat tiket bantuan baru (`priority`: `'1 - Critical'`, `'2 - High'`, `'3 - Moderate'`, `'4 - Low'`). |
| `add_ticket_comment` | `ticket_id`, `comment`, `author` | Menambahkan catatan atau komentar pada riwayat aktivitas tiket. |
| `update_ticket_status` | `ticket_id`, `status`, `resolution_notes`, `updated_by` | Memperbarui status tiket (`New` ➔ `In Progress` ➔ `Resolved` ➔ `Closed`). |

---

## 🚀 Panduan Memulai Cepat & Pengujian Manual

### 1. Instalasi Dependensi
```bash
pip install -r requirements.txt
```

### 2. Atur Variabel Lingkungan (Opsional)
Token tim sudah disematkan secara default, tetapi Anda dapat menimpanya jika diperlukan:
```bash
export SAAS_MCP_CREDENTIAL="mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"
```

### 3. Jalankan Pengujian Manual Interaktif
```bash
# Mode menu interaktif
python manual_test_mcp.py

# Atau jalankan semua pengujian sekaligus
python manual_test_mcp.py --all
```

**Data Langsung yang Telah Terverifikasi:**
- Karyawan Terotentikasi: `EMP-509` (`Romij Employee`)
- Alamat Kantor: `Singapore Office, 80 Pasir Panjang Rd, Singapore`
- Saldo Cuti: `15.0 days remaining (5.0/20.0 used)`
- Tiket Aktif: `INC0003359` (HR Services), `INC0003333` (Inquiry / Help)

---

## 🤖 Integrasi dengan Agen Google ADK

### Opsi A: Menggunakan Google ADK `McpToolset`
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
    instruction="Bantu karyawan mengelola cuti WorkWeek dan tiket dukungan IT ServiceImmediately.",
    tools=[workweek_mcp, serviceimmediately_mcp]
)
```

### Opsi B: Menggunakan Google GenAI SDK (`google-genai`)
```python
from google import genai
from src.adk_tools import ALL_SAAS_ADK_TOOLS

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Berapa hari sisa cuti liburan saya di WorkWeek?",
    config={"tools": ALL_SAAS_ADK_TOOLS, "temperature": 0.1}
)
print(response.text)
```
