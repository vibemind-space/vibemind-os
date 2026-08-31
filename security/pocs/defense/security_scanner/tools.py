"""
Security Scanning Tools
========================
Pure async functions that perform actual network checks.
Each returns a dict of findings.
"""

import asyncio
import json
import os
import socket
import ssl
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model

from openai import AsyncOpenAI


# ================================================================
# TOOL: scan_port
# ================================================================

async def scan_port(host: str, port: int, timeout: float = 3.0) -> dict:
    """Check if a TCP port is open on a target host."""
    KNOWN_SERVICES = {
        22: "ssh", 80: "http", 443: "https", 8080: "http-alt",
        8443: "https-alt", 3306: "mysql", 5432: "postgresql",
        6379: "redis", 27017: "mongodb", 50051: "grpc",
        2379: "etcd", 9090: "prometheus", 8500: "consul",
        2375: "docker-unencrypted", 2376: "docker-encrypted",
        5000: "docker-registry",
    }

    result = {
        "host": host,
        "port": port,
        "state": "closed",
        "service_hint": KNOWN_SERVICES.get(port, "unknown"),
        "banner": None,
    }

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        result["state"] = "open"

        # Try banner grab
        try:
            banner_data = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            if banner_data:
                result["banner"] = banner_data.decode("utf-8", errors="replace").strip()
        except (asyncio.TimeoutError, Exception):
            pass

        writer.close()
        await writer.wait_closed()

    except asyncio.TimeoutError:
        result["state"] = "filtered"
    except ConnectionRefusedError:
        result["state"] = "closed"
    except OSError:
        result["state"] = "filtered"

    return result


# ================================================================
# TOOL: check_grpc_auth
# ================================================================

async def check_grpc_auth(host: str, port: int = 50051) -> dict:
    """Test if a gRPC endpoint requires authentication."""
    result = {
        "host": host,
        "port": port,
        "grpc_reachable": False,
        "auth_required": False,
        "tls_required": False,
        "details": "",
        "vulnerability": None,
    }

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0,
        )

        # Send HTTP/2 connection preface + empty SETTINGS frame
        h2_preface = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
        settings_frame = b"\x00\x00\x00"  # length=0
        settings_frame += b"\x04"          # type=SETTINGS
        settings_frame += b"\x00"          # flags=0
        settings_frame += b"\x00\x00\x00\x00"  # stream_id=0

        writer.write(h2_preface + settings_frame)
        await writer.drain()

        try:
            response = await asyncio.wait_for(reader.read(4096), timeout=3.0)
            if response:
                result["grpc_reachable"] = True
                result["tls_required"] = False
                result["auth_required"] = False
                result["details"] = (
                    f"gRPC server responded on plaintext connection. "
                    f"Response size: {len(response)} bytes. "
                    f"No TLS, no authentication barrier detected."
                )
                result["vulnerability"] = (
                    "CRITICAL: gRPC endpoint accepts plaintext connections "
                    "without authentication. Any network client can connect "
                    "and register agents, subscribe to topics, send/receive messages."
                )
        except asyncio.TimeoutError:
            result["details"] = "Server accepted connection but did not respond to HTTP/2 preface."

        writer.close()
        await writer.wait_closed()

    except ConnectionRefusedError:
        result["details"] = f"Connection refused on {host}:{port}"
    except asyncio.TimeoutError:
        result["details"] = f"Connection timed out to {host}:{port}"
    except OSError as e:
        result["details"] = f"OS error: {e}"

    return result


# ================================================================
# TOOL: check_tls
# ================================================================

async def check_tls(host: str, port: int) -> dict:
    """Check if a service uses TLS encryption."""
    result = {
        "host": host,
        "port": port,
        "tls_enabled": False,
        "tls_version": None,
        "cipher": None,
        "cert_subject": None,
        "plaintext_open": False,
        "vulnerability": None,
    }

    # Try TLS connection
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context),
            timeout=5.0,
        )
        result["tls_enabled"] = True

        ssl_object = writer.transport.get_extra_info("ssl_object")
        if ssl_object:
            result["tls_version"] = ssl_object.version()
            cipher_info = ssl_object.cipher()
            if cipher_info:
                result["cipher"] = cipher_info[0]
            cert = ssl_object.getpeercert()
            if cert:
                subject = dict(x[0] for x in cert.get("subject", ()))
                result["cert_subject"] = subject.get("commonName", str(subject))

        writer.close()
        await writer.wait_closed()

    except (ssl.SSLError, ConnectionRefusedError, asyncio.TimeoutError, OSError):
        # TLS failed -- check plaintext
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0,
            )
            result["plaintext_open"] = True
            result["vulnerability"] = (
                f"Service on {host}:{port} accepts plaintext connections. "
                f"No TLS encryption detected. Data in transit is unprotected."
            )
            writer.close()
            await writer.wait_closed()
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            pass

    return result


# ================================================================
# TOOL: check_docker_bind
# ================================================================

async def check_docker_bind(host: str, ports: list = None) -> dict:
    """Check if Docker-related ports are exposed."""
    if ports is None:
        ports = [2375, 2376, 4243, 5000, 50051]

    result = {
        "host": host,
        "docker_api_exposed": False,
        "docker_api_port": None,
        "exposed_ports": [],
        "vulnerability": None,
    }

    docker_api_ports = {2375, 2376, 4243}
    vulnerabilities = []

    for port in ports:
        port_result = {"port": port, "reachable": False}
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=2.0,
            )
            port_result["reachable"] = True
            writer.close()
            await writer.wait_closed()

            if port in docker_api_ports:
                result["docker_api_exposed"] = True
                result["docker_api_port"] = port
                vulnerabilities.append(
                    f"Docker API exposed on port {port}. "
                    f"Allows unauthenticated container management."
                )
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            pass

        result["exposed_ports"].append(port_result)

    if vulnerabilities:
        result["vulnerability"] = " | ".join(vulnerabilities)

    return result


# ================================================================
# TOOL: think (OpenAI chain-of-thought reasoning)
# ================================================================

async def think(reasoning_prompt: str, llm_client: AsyncOpenAI) -> dict:
    """Use OpenAI to reason step-by-step about security implications."""
    response = await llm_client.chat.completions.create(
        model=get_model("default", "poc_security_scanner"),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior security analyst. Think step-by-step about "
                    "the security implications of the findings presented.\n\n"
                    "Structure your response as:\n"
                    "REASONING:\n"
                    "- Step 1: ...\n"
                    "- Step 2: ...\n\n"
                    "CONCLUSION: <one sentence summary>\n\n"
                    "SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW|INFO>\n"
                ),
            },
            {"role": "user", "content": reasoning_prompt},
        ],
    )

    text = response.choices[0].message.content.strip()

    reasoning = text
    conclusion = ""
    severity = "INFO"

    if "CONCLUSION:" in text:
        parts = text.split("CONCLUSION:")
        reasoning = parts[0].strip()
        remainder = parts[1].strip()
        if "SEVERITY:" in remainder:
            conclusion_parts = remainder.split("SEVERITY:")
            conclusion = conclusion_parts[0].strip()
            severity = conclusion_parts[1].strip().split()[0] if conclusion_parts[1].strip() else "INFO"
        else:
            conclusion = remainder

    return {
        "reasoning": reasoning,
        "conclusion": conclusion,
        "severity_assessment": severity,
    }


# ================================================================
# OPENAI TOOL DEFINITIONS (for function calling)
# ================================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "scan_port",
            "description": "Check if a TCP port is open on a target host. Returns port state, service hint, and banner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Target hostname or IP"},
                    "port": {"type": "integer", "description": "TCP port number"},
                },
                "required": ["host", "port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_grpc_auth",
            "description": "Test if a gRPC endpoint requires authentication. Sends HTTP/2 preface to check if server responds without auth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Target hostname or IP"},
                    "port": {"type": "integer", "description": "gRPC port (default 50051)"},
                },
                "required": ["host"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_tls",
            "description": "Check if a service uses TLS encryption. Attempts TLS handshake, falls back to plaintext check.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Target hostname or IP"},
                    "port": {"type": "integer", "description": "Port to check"},
                },
                "required": ["host", "port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_docker_bind",
            "description": "Check if Docker API ports are exposed (2375, 2376, etc). Detects unauthenticated Docker API access.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Target hostname or IP"},
                    "ports": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Ports to check. Defaults to common Docker ports.",
                    },
                },
                "required": ["host"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Reason step-by-step about security implications of findings. Use this to deeply analyze what scan results mean.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning_prompt": {
                        "type": "string",
                        "description": "Detailed description of findings to reason about",
                    },
                },
                "required": ["reasoning_prompt"],
            },
        },
    },
]
