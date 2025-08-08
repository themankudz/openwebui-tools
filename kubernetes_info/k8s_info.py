"""
title: Kubernetes Cluster Info
author: km01
version: 0.0.3
author_url: https://github.com/themankudz/
funding_url: https://buymeacoffee.com/km01
requirements: kubernetes
"""

from kubernetes import client, config
from collections import defaultdict
from datetime import datetime, timezone
import json

KNOWN_CRDS = {
    "argocd_applications": {
        "group": "argoproj.io",
        "version": "v1alpha1",
        "plural": "applications",
        "summarizer": lambda items: summarize_argocd_applications(items)
    },
    "certmanager_certificates": {
        "group": "cert-manager.io",
        "version": "v1",
        "plural": "certificates",
        "summarizer": lambda items: summarize_certmanager_certificates(items)
    }
}

# --- Summarizers ---
def summarize_argocd_applications(items) -> str:
    total = len(items)
    synced = sum(1 for app in items if app.get("status", {}).get("sync", {}).get("status") == "Synced")
    healthy = sum(1 for app in items if app.get("status", {}).get("health", {}).get("status") == "Healthy")

    details = [
        f"{app.get('metadata', {}).get('name', '<unknown>')} "
        f"({app.get('metadata', {}).get('namespace', '<unknown>')}) — "
        f"Sync: {app.get('status', {}).get('sync', {}).get('status', 'Unknown')}, "
        f"Health: {app.get('status', {}).get('health', {}).get('status', 'Unknown')}"
        for app in items
    ]

    return (
        f"📦 ArgoCD Applications: {total} total — {synced} synced, {total-synced} out-of-sync, "
        f"{healthy} healthy, {total-healthy} degraded.\nDetails:\n" + "\n".join(details)
    )

def summarize_certmanager_certificates(items) -> str:
    total = len(items)
    expiring_soon = []
    now = datetime.now(timezone.utc)

    for cert in items:
        expiry_str = cert.get("status", {}).get("notAfter")
        if expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                days_left = (expiry - now).days
                if days_left < 7:
                    expiring_soon.append(
                        f"{cert.get('metadata', {}).get('name', '<unknown>')} "
                        f"({cert.get('metadata', {}).get('namespace', '<unknown>')}) — "
                        f"expires in {days_left} days"
                    )
            except ValueError:
                pass

    details = "\n".join(expiring_soon) if expiring_soon else "No certificates expiring within 7 days."
    return (
        f"🔐 Cert-Manager Certificates: {total} total.\n"
        f"Expiring soon (<7 days): {len(expiring_soon)}\n{details}"
    )

class Tools:
    def __init__(self):
        # Load kube config once for all methods
        try:
            config.load_kube_config()
        except:
            config.load_incluster_config()

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_api = client.CustomObjectsApi()

    def get_k8s_cluster_info(self, namespace: str = None) -> dict:
        """
        Retrieve Kubernetes cluster state including deployments, pods, services, 
        image versions and detect version mismatches across pods in the same deployment.
        Also returns a plain-English summary.
        Use when you want a complete cluster-wide or namespace-specific overview.
        """
        namespaces = (
            [namespace]
            if namespace
            else [ns.metadata.name for ns in self.v1.list_namespace().items]
        )
        cluster_info = {}
        summaries = []

        for ns in namespaces:
            ns_info = {
                "deployments": [],
                "pods": [],
                "services": [],
                "version_issues": [],
            }

            # Deployments
            deployments = self.apps_v1.list_namespaced_deployment(namespace=ns)
            for dep in deployments.items:
                containers = dep.spec.template.spec.containers or []
                dep_images = [c.image for c in containers]
                ns_info["deployments"].append(
                    {
                        "name": dep.metadata.name,
                        "replicas": dep.spec.replicas,
                        "available_replicas": dep.status.available_replicas or 0,
                        "images": dep_images,
                    }
                )

            # Pods
            pods = self.v1.list_namespaced_pod(namespace=ns)
            deployment_image_map = defaultdict(set)

            for pod in pods.items:
                containers = pod.spec.containers or []
                pod_images = [c.image for c in containers]
                owner_refs = pod.metadata.owner_references or []
                deployment_name = None
                for owner in owner_refs:
                    if owner.kind == "ReplicaSet" and "-" in owner.name:
                        deployment_name = "-".join(owner.name.split("-")[:-1])
                        break

                if deployment_name:
                    deployment_image_map[deployment_name].update(pod_images)

                container_statuses = pod.status.container_statuses or []
                ns_info["pods"].append(
                    {
                        "name": pod.metadata.name,
                        "phase": pod.status.phase,
                        "host_ip": pod.status.host_ip,
                        "pod_ip": pod.status.pod_ip,
                        "restart_count": sum(
                            cs.restart_count for cs in container_statuses
                        ),
                        "images": pod_images,
                    }
                )

            # Version mismatch detection
            for dep_name, images in deployment_image_map.items():
                if len(images) > 1:
                    mismatch_msg = (
                        f"Namespace '{ns}': Deployment '{dep_name}' has version mismatch — "
                        f"running images: {', '.join(images)}"
                    )
                    ns_info["version_issues"].append(
                        {
                            "deployment": dep_name,
                            "detected_images": list(images),
                            "issue": "Mismatched versions detected in pods — rollout may be incomplete or stuck.",
                        }
                    )
                    summaries.append(mismatch_msg)

            # Services
            services = self.v1.list_namespaced_service(namespace=ns)
            for svc in services.items:
                ports = svc.spec.ports or []
                ns_info["services"].append(
                    {
                        "name": svc.metadata.name,
                        "type": svc.spec.type,
                        "cluster_ip": svc.spec.cluster_ip,
                        "ports": [
                            {"port": p.port, "targetPort": p.target_port} for p in ports
                        ],
                    }
                )

            cluster_info[ns] = ns_info

        if not summaries:
            summary_text = "✅ No version mismatches detected across deployments."
        else:
            summary_text = "\n".join(summaries)

        return {"summary": summary_text, "data": cluster_info}

    def get_deployments(self, namespace: str = None) -> dict:
        """
        Retrieve a list of deployments with replica counts and container images.
        Use this when you only need deployment info without pods or services.
        """
        namespaces = (
            [namespace]
            if namespace
            else [ns.metadata.name for ns in self.v1.list_namespace().items]
        )
        results = {}
        for ns in namespaces:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=ns)
            results[ns] = [
                {
                    "name": dep.metadata.name,
                    "replicas": dep.spec.replicas,
                    "available_replicas": dep.status.available_replicas or 0,
                    "images": [
                        c.image for c in (dep.spec.template.spec.containers or [])
                    ],
                }
                for dep in deployments.items
            ]
        return results

    def get_pods(self, namespace: str = None) -> dict:
        """
        Retrieve pod names, status, restart counts, and container images.
        Use this for pod-level debugging without fetching deployments/services.
        """
        namespaces = (
            [namespace]
            if namespace
            else [ns.metadata.name for ns in self.v1.list_namespace().items]
        )
        results = {}
        for ns in namespaces:
            pods = self.v1.list_namespaced_pod(namespace=ns)
            results[ns] = [
                {
                    "name": pod.metadata.name,
                    "phase": pod.status.phase,
                    "host_ip": pod.status.host_ip,
                    "pod_ip": pod.status.pod_ip,
                    "restart_count": sum(
                        cs.restart_count for cs in (pod.status.container_statuses or [])
                    ),
                    "images": [c.image for c in (pod.spec.containers or [])],
                }
                for pod in pods.items
            ]
        return results

    def get_services(self, namespace: str = None) -> dict:
        """
        Retrieve services with type, cluster IP, and ports.
        Use this for networking/service discovery checks without deployments/pods.
        """
        namespaces = (
            [namespace]
            if namespace
            else [ns.metadata.name for ns in self.v1.list_namespace().items]
        )
        results = {}
        for ns in namespaces:
            services = self.v1.list_namespaced_service(namespace=ns)
            results[ns] = [
                {
                    "name": svc.metadata.name,
                    "type": svc.spec.type,
                    "cluster_ip": svc.spec.cluster_ip,
                    "ports": [
                        {"port": p.port, "targetPort": p.target_port}
                        for p in (svc.spec.ports or [])
                    ],
                }
                for svc in services.items
            ]
        return results

    def get_custom_objects(self, group: str, version: str = None, plural: str = None, namespace: str = None) -> dict:
        """
        Retrieve Kubernetes custom resources (CRDs) and return both raw data
        and a human-friendly summary for known types like ArgoCD Applications
        and Cert-Manager Certificates.

        This method now:
        - Accepts either full (group, version, plural) OR a friendly name (e.g., "argocd_applications" or "certmanager_certificates").
        - Automatically uses the correct API info for known CRDs.
        - Falls back to generic behavior for unknown CRDs.
        """
        crd_info = None

        # If user passed a known CRD name instead of group
        if group in KNOWN_CRDS:
            crd_info = KNOWN_CRDS[group]
        else:
            # Try to match by group+plural ignoring case
            for info in KNOWN_CRDS.values():
                if info["group"].lower() == str(group).lower() and info["plural"].lower() == str(plural).lower():
                    crd_info = info
                    break

        try:
            if crd_info:  # Known CRD → override args and use summarizer
                if namespace:
                    resources = self.custom_api.list_namespaced_custom_object(
                        group=crd_info["group"], version=crd_info["version"],
                        namespace=namespace, plural=crd_info["plural"]
                    )
                else:
                    resources = self.custom_api.list_cluster_custom_object(
                        group=crd_info["group"], version=crd_info["version"], plural=crd_info["plural"]
                    )
                items = resources.get("items", [])
                summary = crd_info["summarizer"](items)
                return {"summary": summary, "data": resources}

            # Unknown CRD → use whatever was passed
            if not all([group, version, plural]):
                return {"error": "Unknown CRD and missing API details (group/version/plural required)"}

            if namespace:
                resources = self.custom_api.list_namespaced_custom_object(
                    group=group, version=version, namespace=namespace, plural=plural
                )
            else:
                resources = self.custom_api.list_cluster_custom_object(
                    group=group, version=version, plural=plural
                )

            return {"summary": f"Retrieved {len(resources.get('items', []))} {plural} objects.", "data": resources}

        except Exception as e:
            return {"error": str(e)}