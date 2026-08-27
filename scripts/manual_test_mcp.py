#!/usr/bin/env python3
"""
Interactive Manual Test Runner for Live SaaS MCP Integration & Google ADK Tools.
Connects directly to https://mock-saas.aishprabhat.demo.altostrat.com/
using the custom X-MCP-Token header specified in the OpenAPI documentation.
"""

import sys
import json
import asyncio
import argparse
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.tools.adk_tools import (
    get_current_employee_id,
    get_employee_balances,
    request_time_off,
    get_personal_info,
    update_personal_info,
    get_leave_requests,
    cancel_leave_request,
    list_tickets,
    create_ticket,
    add_ticket_comment,
    update_ticket_status,
)
from src.tools.saas_mcp_client import saas_mcp_client


async def run_test_case(name: str, coro):
    print(f"\n=======================================================")
    print(f"▶ Running: {name}")
    print(f"=======================================================")
    try:
        res = await coro
        print(f"Status: \033[92mSUCCESS\033[0m")
        print(f"Result Payload:\n{json.dumps(res, indent=2, ensure_ascii=False)}")
        return True
    except Exception as e:
        print(f"Status: \033[91mERROR\033[0m -> {e}")
        return False


async def run_all_tests():
    print("=======================================================")
    print("  LIVE SAAS FAST-MCP & ADK TOOLS MANUAL TEST SUITE     ")
    print(f"  Target URL: {saas_mcp_client.base_url}")
    print(f"  Token:      {saas_mcp_client.mcp_token[:10]}...{saas_mcp_client.mcp_token[-6:]}")
    print("=======================================================")

    results = []

    # 1. Resolve Session Employee ID
    results.append(("WorkWeek: Get Current Employee ID", await run_test_case(
        "WorkWeek Get Current Employee ID",
        get_current_employee_id()
    )))

    # 2. WorkWeek Balances
    results.append(("WorkWeek: Get Balances", await run_test_case(
        "WorkWeek Get Balances",
        get_employee_balances()
    )))

    # 3. WorkWeek Personal Contact Info
    results.append(("WorkWeek: Get Personal Info", await run_test_case(
        "WorkWeek Get Personal Info",
        get_personal_info()
    )))

    # 4. WorkWeek Leave History
    results.append(("WorkWeek: Get Leave Requests", await run_test_case(
        "WorkWeek Get Leave Requests",
        get_leave_requests()
    )))

    # 5. ServiceImmediately List Tickets
    results.append(("ServiceImmediately: List Tickets", await run_test_case(
        "ServiceImmediately List Tickets",
        list_tickets()
    )))

    print("\n=======================================================")
    print("  MANUAL TEST EXECUTION SUMMARY")
    print("=======================================================")
    for name, status in results:
        status_str = "\033[92mPASS [OK]\033[0m" if status else "\033[91mFAIL\033[0m"
        print(f"  • {name:<40} {status_str}")
    print("=======================================================\n")


async def interactive_menu():
    while True:
        print("\n=== Live SaaS MCP ADK Tools Interactive Test ===")
        print("1. [WorkWeek] Resolve Current Employee ID (get_current_employee_id)")
        print("2. [WorkWeek] Check Vacation & Sick Balances (get_employee_balances)")
        print("3. [WorkWeek] View Personal Contact Info (get_personal_info)")
        print("4. [WorkWeek] View Leave Requests History (get_leave_requests)")
        print("5. [WorkWeek] Request Time Off (request_time_off)")
        print("6. [WorkWeek] Cancel Leave Request (cancel_leave_request)")
        print("7. [ITSM] List Employee Support Tickets (list_tickets)")
        print("8. [ITSM] Create New Support Ticket (create_ticket)")
        print("9. [ITSM] Add Comment to Ticket (add_ticket_comment)")
        print("10. [ITSM] Update Ticket Status (update_ticket_status)")
        print("A. Run All Read Tests Sequentially")
        print("Q. Quit")

        choice = input("\nEnter your choice: ").strip().upper()
        if choice == "1":
            await run_test_case("WorkWeek Get Current Employee ID", get_current_employee_id())
        elif choice == "2":
            await run_test_case("WorkWeek Get Balances", get_employee_balances())
        elif choice == "3":
            await run_test_case("WorkWeek Get Personal Info", get_personal_info())
        elif choice == "4":
            await run_test_case("WorkWeek Get Leave Requests", get_leave_requests())
        elif choice == "5":
            s_date = input("Enter start date (YYYY-MM-DD) [Default: 2026-10-05]: ").strip() or "2026-10-05"
            e_date = input("Enter end date (YYYY-MM-DD) [Default: 2026-10-06]: ").strip() or "2026-10-06"
            days = float(input("Enter days [Default: 2.0]: ").strip() or "2.0")
            await run_test_case("WorkWeek Request Time Off", request_time_off(
                start_date=s_date, end_date=e_date, leave_type="Vacation", days=days
            ))
        elif choice == "6":
            req_id = int(input("Enter request ID to cancel: ").strip())
            await run_test_case("WorkWeek Cancel Leave", cancel_leave_request(request_id=req_id))
        elif choice == "7":
            await run_test_case("ITSM List Tickets", list_tickets())
        elif choice == "8":
            desc = input("Enter ticket description [Default: VPN connectivity issue]: ").strip() or "VPN connectivity issue"
            await run_test_case("ITSM Create Ticket", create_ticket(
                category="Hardware", short_description=desc, priority="3 - Moderate"
            ))
        elif choice == "9":
            tid = input("Enter Ticket ID [Default: INC0003359]: ").strip() or "INC0003359"
            comment = input("Enter comment [Default: Technician dispatched]: ").strip() or "Technician dispatched"
            await run_test_case("ITSM Add Comment", add_ticket_comment(ticket_id=tid, comment=comment))
        elif choice == "10":
            tid = input("Enter Ticket ID [Default: INC0003359]: ").strip() or "INC0003359"
            status = input("Enter new status (In Progress / Resolved / Closed) [Default: In Progress]: ").strip() or "In Progress"
            await run_test_case("ITSM Update Status", update_ticket_status(ticket_id=tid, status=status))
        elif choice == "A":
            await run_all_tests()
        elif choice == "Q":
            print("Exiting test runner.")
            break
        else:
            print("Invalid choice. Please select a valid option.")


def main():
    parser = argparse.ArgumentParser(description="Manual Test Runner for Live SaaS MCP Tools")
    parser.add_argument("--all", action="store_true", help="Run all read test cases sequentially")
    args = parser.parse_args()

    if args.all:
        asyncio.run(run_all_tests())
    else:
        asyncio.run(interactive_menu())


if __name__ == "__main__":
    main()
