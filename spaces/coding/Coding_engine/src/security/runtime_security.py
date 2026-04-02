"""
Runtime Security Manager - Runtime security policies and enforcement.

Provides comprehensive runtime security:
- mTLS configuration and certificate management
- Network policy generation and enforcement
- RBAC setup with minimal permissions
- Pod security context configuration
- Seccomp profile management
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import uuid

import structlog

logger = structlog.get_logger()


class SecurityLevel(str, Enum):
    """Security level for runtime policies."""
    RESTRICTED = "restricted"  # Most secure, minimal permissions
    BASELINE = "baseline"  # Standard security
    PRIVILEGED = "privileged"  # For system components only


class NetworkPolicyType(str, Enum):
    """Types of network policies."""
    DEFAULT_DENY = "default-deny"
    ALLOW_SAME_NAMESPACE = "allow-same-namespace"
    ALLOW_INGRESS = "allow-ingress"
    ALLOW_EGRESS = "allow-egress"
    CUSTOM = "custom"


@dataclass
class MTLSConfig:
    """mTLS configuration for a cell."""
    enabled: bool = True
    cert_validity_days: int = 30
    issuer: str = "cell-colony-ca"
    san_dns: List[str] = field(default_factory=list)
    san_ips: List[str] = field(default_factory=list)
    client_auth: bool = True
    min_tls_version: str = "1.2"


@dataclass
class NetworkPolicyConfig:
    """Network policy configuration."""
    policy_type: NetworkPolicyType = NetworkPolicyType.DEFAULT_DENY
    allowed_ingress_namespaces: List[str] = field(default_factory=list)
    allowed_ingress_pods: Dict[str, str] = field(default_factory=dict)
    allowed_egress_namespaces: List[str] = field(default_factory=list)
    allowed_egress_pods: Dict[str, str] = field(default_factory=dict)
    allowed_ports: List[int] = field(default_factory=list)
    allow_dns: bool = True
    allow_internet: bool = False


@dataclass
class RBACConfig:
    """RBAC configuration for a cell."""
    service_account_name: str = ""
    cluster_role: Optional[str] = None
    namespace_roles: List[str] = field(default_factory=list)
    automount_token: bool = False
    token_expiration: int = 3600  # seconds


@dataclass
class PodSecurityConfig:
    """Pod security context configuration."""
    security_level: SecurityLevel = SecurityLevel.BASELINE
    run_as_non_root: bool = True
    run_as_user: Optional[int] = 1000
    run_as_group: Optional[int] = 1000
    fs_group: Optional[int] = 1000
    read_only_root_filesystem: bool = True
    allow_privilege_escalation: bool = False
    drop_capabilities: List[str] = field(default_factory=lambda: ["ALL"])
    add_capabilities: List[str] = field(default_factory=list)
    seccomp_profile: str = "RuntimeDefault"
    apparmor_profile: Optional[str] = None


@dataclass
class SecurityContext:
    """Complete security context for a cell."""
    cell_id: str
    namespace: str
    mtls: MTLSConfig = field(default_factory=MTLSConfig)
    network_policy: NetworkPolicyConfig = field(default_factory=NetworkPolicyConfig)
    rbac: RBACConfig = field(default_factory=RBACConfig)
    pod_security: PodSecurityConfig = field(default_factory=PodSecurityConfig)


class RuntimeSecurityManager:
    """
    Manages runtime security for Cell Colony.

    Responsibilities:
    - Configure mTLS between cells
    - Generate and apply NetworkPolicies
    - Setup ServiceAccounts with minimal RBAC
    - Configure Pod security contexts
    - Manage seccomp profiles
    """

    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.logger = logger.bind(component="RuntimeSecurityManager", namespace=namespace)
        self._security_contexts: Dict[str, SecurityContext] = {}

    def configure_mtls(self, cell_id: str, config: Optional[MTLSConfig] = None) -> Dict[str, Any]:
        """
        Configure mTLS for a cell.

        Returns Istio/Linkerd-style PeerAuthentication and DestinationRule manifests.
        """
        config = config or MTLSConfig()
        self.logger.info("Configuring mTLS", cell_id=cell_id)

        # PeerAuthentication for strict mTLS
        peer_auth = {
            "apiVersion": "security.istio.io/v1beta1",
            "kind": "PeerAuthentication",
            "metadata": {
                "name": f"cell-{cell_id[:8]}-mtls",
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                },
            },
            "spec": {
                "selector": {
                    "matchLabels": {
                        "colony.codingengine.io/cell-id": cell_id[:8],
                    },
                },
                "mtls": {
                    "mode": "STRICT",
                },
            },
        }

        # DestinationRule for mTLS client settings
        dest_rule = {
            "apiVersion": "networking.istio.io/v1beta1",
            "kind": "DestinationRule",
            "metadata": {
                "name": f"cell-{cell_id[:8]}-mtls-rule",
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                },
            },
            "spec": {
                "host": f"cell-{cell_id[:8]}.{self.namespace}.svc.cluster.local",
                "trafficPolicy": {
                    "tls": {
                        "mode": "ISTIO_MUTUAL",
                    },
                },
            },
        }

        return {
            "peer_authentication": peer_auth,
            "destination_rule": dest_rule,
        }

    def apply_network_policies(
        self,
        cell_id: str,
        cell_name: str,
        config: Optional[NetworkPolicyConfig] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate NetworkPolicy manifests for a cell.

        Creates:
        1. Default deny ingress/egress
        2. Allow DNS
        3. Allow specified namespaces/pods
        """
        config = config or NetworkPolicyConfig()
        self.logger.info("Applying network policies", cell_id=cell_id)

        policies = []

        # Default deny all
        default_deny = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"cell-{cell_name}-default-deny",
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                    "colony.codingengine.io/policy-type": "default-deny",
                },
            },
            "spec": {
                "podSelector": {
                    "matchLabels": {
                        "colony.codingengine.io/cell-id": cell_id[:8],
                    },
                },
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [],
                "egress": [],
            },
        }
        policies.append(default_deny)

        # Allow DNS egress
        if config.allow_dns:
            dns_policy = {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": f"cell-{cell_name}-allow-dns",
                    "namespace": self.namespace,
                    "labels": {
                        "colony.codingengine.io/cell-id": cell_id,
                        "colony.codingengine.io/policy-type": "allow-dns",
                    },
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "colony.codingengine.io/cell-id": cell_id[:8],
                        },
                    },
                    "policyTypes": ["Egress"],
                    "egress": [
                        {
                            "to": [{"namespaceSelector": {}}],
                            "ports": [
                                {"protocol": "UDP", "port": 53},
                                {"protocol": "TCP", "port": 53},
                            ],
                        }
                    ],
                },
            }
            policies.append(dns_policy)

        # Allow ingress from same namespace
        if config.policy_type in [NetworkPolicyType.ALLOW_SAME_NAMESPACE, NetworkPolicyType.ALLOW_INGRESS]:
            same_ns_policy = {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": f"cell-{cell_name}-allow-same-ns",
                    "namespace": self.namespace,
                    "labels": {
                        "colony.codingengine.io/cell-id": cell_id,
                        "colony.codingengine.io/policy-type": "allow-same-namespace",
                    },
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "colony.codingengine.io/cell-id": cell_id[:8],
                        },
                    },
                    "policyTypes": ["Ingress"],
                    "ingress": [
                        {
                            "from": [
                                {
                                    "namespaceSelector": {
                                        "matchLabels": {"kubernetes.io/metadata.name": self.namespace}
                                    }
                                }
                            ],
                            "ports": [
                                {"protocol": "TCP", "port": port}
                                for port in config.allowed_ports
                            ] if config.allowed_ports else None,
                        }
                    ],
                },
            }
            # Remove None ports
            if same_ns_policy["spec"]["ingress"][0]["ports"] is None:
                del same_ns_policy["spec"]["ingress"][0]["ports"]
            policies.append(same_ns_policy)

        # Allow specific egress
        if config.allowed_egress_namespaces or config.allowed_egress_pods:
            egress_rules = []

            for ns in config.allowed_egress_namespaces:
                egress_rules.append({
                    "to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": ns}}}]
                })

            for label, value in config.allowed_egress_pods.items():
                egress_rules.append({
                    "to": [{"podSelector": {"matchLabels": {label: value}}}]
                })

            if egress_rules:
                egress_policy = {
                    "apiVersion": "networking.k8s.io/v1",
                    "kind": "NetworkPolicy",
                    "metadata": {
                        "name": f"cell-{cell_name}-allow-egress",
                        "namespace": self.namespace,
                        "labels": {
                            "colony.codingengine.io/cell-id": cell_id,
                            "colony.codingengine.io/policy-type": "allow-egress",
                        },
                    },
                    "spec": {
                        "podSelector": {
                            "matchLabels": {
                                "colony.codingengine.io/cell-id": cell_id[:8],
                            },
                        },
                        "policyTypes": ["Egress"],
                        "egress": egress_rules,
                    },
                }
                policies.append(egress_policy)

        return policies

    def setup_rbac(
        self,
        cell_id: str,
        cell_name: str,
        config: Optional[RBACConfig] = None,
    ) -> Dict[str, Any]:
        """
        Setup RBAC for a cell with minimal permissions.

        Creates:
        1. ServiceAccount
        2. Role with minimal permissions
        3. RoleBinding
        """
        config = config or RBACConfig()
        sa_name = config.service_account_name or f"cell-{cell_name}-sa"

        self.logger.info("Setting up RBAC", cell_id=cell_id, service_account=sa_name)

        # ServiceAccount
        service_account = {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": sa_name,
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                },
                "annotations": {
                    "colony.codingengine.io/created-at": datetime.now(timezone.utc).isoformat(),
                },
            },
            "automountServiceAccountToken": config.automount_token,
        }

        # Role with minimal permissions
        role = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {
                "name": f"cell-{cell_name}-role",
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                },
            },
            "rules": [
                # Read own ConfigMaps
                {
                    "apiGroups": [""],
                    "resources": ["configmaps"],
                    "resourceNames": [f"cell-{cell_name}-config"],
                    "verbs": ["get"],
                },
                # Read own Secrets (through Vault ideally)
                {
                    "apiGroups": [""],
                    "resources": ["secrets"],
                    "resourceNames": [f"cell-{cell_name}-secrets"],
                    "verbs": ["get"],
                },
            ],
        }

        # RoleBinding
        role_binding = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": f"cell-{cell_name}-rolebinding",
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                },
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": sa_name,
                    "namespace": self.namespace,
                },
            ],
            "roleRef": {
                "kind": "Role",
                "name": f"cell-{cell_name}-role",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        }

        return {
            "service_account": service_account,
            "role": role,
            "role_binding": role_binding,
        }

    def apply_security_context(
        self,
        deployment: Dict[str, Any],
        config: Optional[PodSecurityConfig] = None,
    ) -> Dict[str, Any]:
        """
        Apply security context to a deployment.

        Modifies the deployment in place to add:
        - Pod security context
        - Container security context
        - Seccomp profile
        """
        config = config or PodSecurityConfig()
        self.logger.debug("Applying security context", security_level=config.security_level.value)

        # Ensure spec.template.spec exists
        if "spec" not in deployment:
            deployment["spec"] = {}
        if "template" not in deployment["spec"]:
            deployment["spec"]["template"] = {}
        if "spec" not in deployment["spec"]["template"]:
            deployment["spec"]["template"]["spec"] = {}

        pod_spec = deployment["spec"]["template"]["spec"]

        # Pod-level security context
        pod_spec["securityContext"] = {
            "runAsNonRoot": config.run_as_non_root,
            "seccompProfile": {
                "type": config.seccomp_profile,
            },
        }

        if config.run_as_user:
            pod_spec["securityContext"]["runAsUser"] = config.run_as_user
        if config.run_as_group:
            pod_spec["securityContext"]["runAsGroup"] = config.run_as_group
        if config.fs_group:
            pod_spec["securityContext"]["fsGroup"] = config.fs_group

        # Container-level security context
        for container in pod_spec.get("containers", []):
            container["securityContext"] = {
                "allowPrivilegeEscalation": config.allow_privilege_escalation,
                "readOnlyRootFilesystem": config.read_only_root_filesystem,
                "capabilities": {
                    "drop": config.drop_capabilities,
                },
            }

            if config.add_capabilities:
                container["securityContext"]["capabilities"]["add"] = config.add_capabilities

            # Add AppArmor annotation if specified
            if config.apparmor_profile:
                if "annotations" not in deployment["spec"]["template"]["metadata"]:
                    deployment["spec"]["template"]["metadata"]["annotations"] = {}
                deployment["spec"]["template"]["metadata"]["annotations"][
                    f"container.apparmor.security.beta.kubernetes.io/{container['name']}"
                ] = config.apparmor_profile

        return deployment

    def generate_pod_security_policy(
        self,
        name: str,
        level: SecurityLevel = SecurityLevel.BASELINE,
    ) -> Dict[str, Any]:
        """
        Generate PodSecurityPolicy (deprecated in K8s 1.25+) or
        Pod Security Standard labels for namespace.

        For K8s 1.25+, use namespace labels instead.
        """
        # Pod Security Standards (K8s 1.25+)
        namespace_labels = {
            "pod-security.kubernetes.io/enforce": level.value,
            "pod-security.kubernetes.io/enforce-version": "latest",
            "pod-security.kubernetes.io/warn": level.value,
            "pod-security.kubernetes.io/warn-version": "latest",
            "pod-security.kubernetes.io/audit": level.value,
            "pod-security.kubernetes.io/audit-version": "latest",
        }

        # For older K8s, return PSP
        psp = {
            "apiVersion": "policy/v1beta1",
            "kind": "PodSecurityPolicy",
            "metadata": {
                "name": name,
                "annotations": {
                    "seccomp.security.alpha.kubernetes.io/allowedProfiles": "runtime/default",
                },
            },
            "spec": {
                "privileged": False,
                "allowPrivilegeEscalation": False,
                "requiredDropCapabilities": ["ALL"],
                "hostNetwork": False,
                "hostIPC": False,
                "hostPID": False,
                "runAsUser": {
                    "rule": "MustRunAsNonRoot",
                },
                "seLinux": {
                    "rule": "RunAsAny",
                },
                "fsGroup": {
                    "rule": "MustRunAs",
                    "ranges": [{"min": 1, "max": 65535}],
                },
                "supplementalGroups": {
                    "rule": "MustRunAs",
                    "ranges": [{"min": 1, "max": 65535}],
                },
                "volumes": ["configMap", "emptyDir", "projected", "secret", "persistentVolumeClaim"],
                "readOnlyRootFilesystem": True,
            },
        }

        if level == SecurityLevel.RESTRICTED:
            psp["spec"]["volumes"] = ["configMap", "emptyDir", "projected", "secret"]

        return {
            "namespace_labels": namespace_labels,
            "pod_security_policy": psp,
        }

    def generate_seccomp_profile(self, cell_id: str) -> Dict[str, Any]:
        """
        Generate a custom seccomp profile for a cell.

        This is a restrictive profile that only allows necessary syscalls.
        """
        profile = {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_X86", "SCMP_ARCH_ARM64"],
            "syscalls": [
                # Essential syscalls
                {
                    "names": [
                        "read", "write", "close", "fstat", "lseek", "mmap", "mprotect",
                        "munmap", "brk", "rt_sigaction", "rt_sigprocmask", "ioctl",
                        "access", "pipe", "select", "sched_yield", "mremap", "msync",
                        "mincore", "madvise", "dup", "dup2", "nanosleep", "getpid",
                        "sendfile", "socket", "connect", "accept", "sendto", "recvfrom",
                        "sendmsg", "recvmsg", "shutdown", "bind", "listen", "getsockname",
                        "getpeername", "socketpair", "setsockopt", "getsockopt", "clone",
                        "fork", "vfork", "execve", "exit", "wait4", "kill", "uname",
                        "fcntl", "flock", "fsync", "fdatasync", "truncate", "ftruncate",
                        "getdents", "getcwd", "chdir", "fchdir", "rename", "mkdir",
                        "rmdir", "creat", "link", "unlink", "symlink", "readlink",
                        "chmod", "fchmod", "chown", "fchown", "lchown", "umask",
                        "gettimeofday", "getrlimit", "getrusage", "sysinfo", "times",
                        "getuid", "getgid", "setuid", "setgid", "geteuid", "getegid",
                        "getgroups", "setgroups", "getpgrp", "setpgid", "setsid",
                        "getppid", "getpgid", "getsid", "capget", "capset",
                        "rt_sigpending", "rt_sigtimedwait", "rt_sigqueueinfo",
                        "rt_sigsuspend", "sigaltstack", "utime", "mknod", "uselib",
                        "personality", "ustat", "statfs", "fstatfs", "sysfs",
                        "getpriority", "setpriority", "sched_setparam", "sched_getparam",
                        "sched_setscheduler", "sched_getscheduler", "sched_get_priority_max",
                        "sched_get_priority_min", "sched_rr_get_interval", "mlock",
                        "munlock", "mlockall", "munlockall", "vhangup", "pivot_root",
                        "prctl", "arch_prctl", "adjtimex", "setrlimit", "chroot",
                        "sync", "acct", "settimeofday", "mount", "umount2", "swapon",
                        "swapoff", "reboot", "sethostname", "setdomainname", "ioperm",
                        "iopl", "create_module", "init_module", "delete_module",
                        "get_kernel_syms", "query_module", "quotactl", "nfsservctl",
                        "getpmsg", "putpmsg", "afs_syscall", "tuxcall", "security",
                        "gettid", "readahead", "setxattr", "lsetxattr", "fsetxattr",
                        "getxattr", "lgetxattr", "fgetxattr", "listxattr", "llistxattr",
                        "flistxattr", "removexattr", "lremovexattr", "fremovexattr",
                        "tkill", "time", "futex", "sched_setaffinity", "sched_getaffinity",
                        "set_thread_area", "io_setup", "io_destroy", "io_getevents",
                        "io_submit", "io_cancel", "get_thread_area", "lookup_dcookie",
                        "epoll_create", "epoll_ctl_old", "epoll_wait_old", "remap_file_pages",
                        "getdents64", "set_tid_address", "restart_syscall", "semtimedop",
                        "fadvise64", "timer_create", "timer_settime", "timer_gettime",
                        "timer_getoverrun", "timer_delete", "clock_settime", "clock_gettime",
                        "clock_getres", "clock_nanosleep", "exit_group", "epoll_wait",
                        "epoll_ctl", "tgkill", "utimes", "mbind", "set_mempolicy",
                        "get_mempolicy", "mq_open", "mq_unlink", "mq_timedsend",
                        "mq_timedreceive", "mq_notify", "mq_getsetattr", "kexec_load",
                        "waitid", "add_key", "request_key", "keyctl", "ioprio_set",
                        "ioprio_get", "inotify_init", "inotify_add_watch", "inotify_rm_watch",
                        "migrate_pages", "openat", "mkdirat", "mknodat", "fchownat",
                        "futimesat", "newfstatat", "unlinkat", "renameat", "linkat",
                        "symlinkat", "readlinkat", "fchmodat", "faccessat", "pselect6",
                        "ppoll", "unshare", "set_robust_list", "get_robust_list",
                        "splice", "tee", "sync_file_range", "vmsplice", "move_pages",
                        "utimensat", "epoll_pwait", "signalfd", "timerfd_create",
                        "eventfd", "fallocate", "timerfd_settime", "timerfd_gettime",
                        "accept4", "signalfd4", "eventfd2", "epoll_create1", "dup3",
                        "pipe2", "inotify_init1", "preadv", "pwritev", "rt_tgsigqueueinfo",
                        "perf_event_open", "recvmmsg", "fanotify_init", "fanotify_mark",
                        "prlimit64", "name_to_handle_at", "open_by_handle_at",
                        "clock_adjtime", "syncfs", "sendmmsg", "setns", "getcpu",
                        "process_vm_readv", "process_vm_writev", "kcmp", "finit_module",
                        "sched_setattr", "sched_getattr", "renameat2", "seccomp",
                        "getrandom", "memfd_create", "kexec_file_load", "bpf",
                        "execveat", "userfaultfd", "membarrier", "mlock2", "copy_file_range",
                        "preadv2", "pwritev2", "pkey_mprotect", "pkey_alloc", "pkey_free",
                        "statx", "io_pgetevents", "rseq",
                    ],
                    "action": "SCMP_ACT_ALLOW",
                },
                # Block dangerous syscalls
                {
                    "names": [
                        "ptrace", "kexec_load", "kexec_file_load", "bpf",
                        "mount", "umount2", "pivot_root", "chroot",
                        "init_module", "finit_module", "delete_module",
                    ],
                    "action": "SCMP_ACT_ERRNO",
                    "errnoRet": 1,  # EPERM
                },
            ],
        }

        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"seccomp-cell-{cell_id[:8]}",
                "namespace": self.namespace,
                "labels": {
                    "colony.codingengine.io/cell-id": cell_id,
                    "colony.codingengine.io/resource-type": "seccomp-profile",
                },
            },
            "data": {
                "profile.json": json.dumps(profile, indent=2),
            },
        }

    def create_security_context(
        self,
        cell_id: str,
        cell_name: str,
        security_level: SecurityLevel = SecurityLevel.BASELINE,
        allowed_ports: Optional[List[int]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> SecurityContext:
        """
        Create a complete security context for a cell.

        Args:
            cell_id: Cell identifier
            cell_name: Cell name
            security_level: Desired security level
            allowed_ports: Ports to allow in network policy
            depends_on: Cell IDs this cell can communicate with

        Returns:
            Complete SecurityContext with all configurations
        """
        self.logger.info("Creating security context",
                        cell_id=cell_id,
                        security_level=security_level.value)

        # Configure network policy
        network_config = NetworkPolicyConfig(
            policy_type=NetworkPolicyType.DEFAULT_DENY,
            allowed_ports=allowed_ports or [],
            allow_dns=True,
            allow_internet=security_level == SecurityLevel.PRIVILEGED,
        )

        # Add egress rules for dependencies
        if depends_on:
            for dep_id in depends_on:
                network_config.allowed_egress_pods[f"colony.codingengine.io/cell-id"] = dep_id[:8]

        # Configure pod security based on level
        pod_security = PodSecurityConfig(
            security_level=security_level,
            run_as_non_root=True,
            read_only_root_filesystem=security_level != SecurityLevel.PRIVILEGED,
            allow_privilege_escalation=False,
            drop_capabilities=["ALL"],
            seccomp_profile="RuntimeDefault",
        )

        # Configure RBAC
        rbac_config = RBACConfig(
            service_account_name=f"cell-{cell_name}-sa",
            automount_token=False,
        )

        # Configure mTLS
        mtls_config = MTLSConfig(
            enabled=True,
            san_dns=[
                f"cell-{cell_name}.{self.namespace}.svc.cluster.local",
                f"*.{self.namespace}.svc.cluster.local",
            ],
        )

        context = SecurityContext(
            cell_id=cell_id,
            namespace=self.namespace,
            mtls=mtls_config,
            network_policy=network_config,
            rbac=rbac_config,
            pod_security=pod_security,
        )

        self._security_contexts[cell_id] = context
        return context

    def generate_all_manifests(
        self,
        cell_id: str,
        cell_name: str,
        security_context: Optional[SecurityContext] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate all security-related K8s manifests for a cell.

        Returns:
            Dictionary with categories of manifests
        """
        if security_context is None:
            security_context = self._security_contexts.get(cell_id)
            if security_context is None:
                security_context = self.create_security_context(cell_id, cell_name)

        manifests = {
            "network_policies": self.apply_network_policies(
                cell_id, cell_name, security_context.network_policy
            ),
            "rbac": [
                v for v in self.setup_rbac(
                    cell_id, cell_name, security_context.rbac
                ).values()
            ],
            "mtls": [
                v for v in self.configure_mtls(cell_id, security_context.mtls).values()
            ],
            "seccomp": [self.generate_seccomp_profile(cell_id)],
        }

        return manifests

    def get_security_context(self, cell_id: str) -> Optional[SecurityContext]:
        """Get cached security context for a cell."""
        return self._security_contexts.get(cell_id)
