"""
CheckerAgent - Executes OSINT Verification Checks
===================================================
Receives CheckTask messages, calls the appropriate tool function,
returns CheckResult. No LLM needed — pure network I/O.
"""

import json

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import CheckTask, CheckResult
from tools import (
    whois_lookup, check_ssl_cert, dns_records,
    http_headers, wayback_check, page_content_scan,
    reverse_ip_lookup, security_audit,
    robots_sitemap_scan, subdomain_enum, cors_check,
    port_scan, path_discovery,
    cms_version_detect, login_security_check, subdomain_content_scan,
    xss_reflection_check, sqli_check,
    open_redirect_check, http_methods_check, js_secrets_scanner,
    email_spoofing_test, waf_detection, rate_limit_check,
    dns_zone_transfer, breach_check,
)


TOOL_DISPATCH = {
    "whois_lookup": whois_lookup,
    "check_ssl_cert": check_ssl_cert,
    "dns_records": dns_records,
    "http_headers": http_headers,
    "wayback_check": wayback_check,
    "page_content_scan": page_content_scan,
    "reverse_ip_lookup": reverse_ip_lookup,
    "security_audit": security_audit,
    "robots_sitemap_scan": robots_sitemap_scan,
    "subdomain_enum": subdomain_enum,
    "cors_check": cors_check,
    "port_scan": port_scan,
    "path_discovery": path_discovery,
    "cms_version_detect": cms_version_detect,
    "login_security_check": login_security_check,
    "subdomain_content_scan": subdomain_content_scan,
    "xss_reflection_check": xss_reflection_check,
    "sqli_check": sqli_check,
    "open_redirect_check": open_redirect_check,
    "http_methods_check": http_methods_check,
    "js_secrets_scanner": js_secrets_scanner,
    "email_spoofing_test": email_spoofing_test,
    "waf_detection": waf_detection,
    "rate_limit_check": rate_limit_check,
    "dns_zone_transfer": dns_zone_transfer,
    "breach_check": breach_check,
}


class CheckerAgent(RoutedAgent):

    def __init__(self):
        super().__init__("CheckerAgent")

    @message_handler
    async def handle_check_task(
        self, message: CheckTask, ctx: MessageContext
    ) -> CheckResult:
        print(f"    [CHECKER] Task {message.task_id}: {message.tool_name}", flush=True)

        tool_fn = TOOL_DISPATCH.get(message.tool_name)
        if not tool_fn:
            return CheckResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": f"Unknown tool: {message.tool_name}"}),
            )

        try:
            args = json.loads(message.arguments_json)
            result_dict = await tool_fn(**args)

            return CheckResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=True,
                result_json=json.dumps(result_dict, default=str),
            )

        except Exception as e:
            print(f"    [CHECKER] Task {message.task_id} error: {e}", flush=True)
            return CheckResult(
                task_id=message.task_id,
                tool_name=message.tool_name,
                success=False,
                result_json=json.dumps({"error": str(e)}),
            )
