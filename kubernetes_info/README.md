# Kubernetes Cluster Info Tool

## Overview

This Python tool provides a programmatic interface for querying and summarising information from a Kubernetes cluster.  
It is designed to be used as an **OpenWebUI tool** but can also run as a standalone Python script.  

It supports:
- Retrieving deployments, pods, and services.
- Detecting image version mismatches across pods in the same deployment.
- Querying and summarising **well-known CRDs** such as:
  - **ArgoCD Applications** (`argoproj.io`)
  - **Cert-Manager Certificates** (`cert-manager.io`)
- Fetching **any other custom resource** when group/version/plural are known.

For known CRDs, the tool automatically:
- Uses the correct **API group, version, and plural**.
- Generates human-readable summaries.

---

## Features

- **Namespace-specific or cluster-wide queries**  
  You can retrieve objects from a single namespace or across the entire cluster.

- **CRD-friendly names**  
  Query `argocd_applications` or `certmanager_certificates` without remembering API group or plural.

- **Smart Summarisation**  
  Displays ArgoCD sync/health status and Cert-Manager expiry warnings.

- **Flexible Connectivity**  
  Works both inside a Kubernetes cluster (using in-cluster config) and externally (using kubeconfig).

---

## Requirements

- Python 3.8+
- `kubernetes` Python client  
  Install with:
  ```bash
  pip install kubernetes

---

## Kubernetes Permissions

The tool requires read access to the following Kubernetes resources:

| API Group         | Resources                  | Access Needed          |
| ----------------- | -------------------------- | ---------------------- |
| `""` (core)       | pods, services, namespaces | `get`, `list`, `watch` |
| `apps`            | deployments                | `get`, `list`, `watch` |
| `argoproj.io`     | applications               | `get`, `list`, `watch` |
| `cert-manager.io` | certificates               | `get`, `list`, `watch` |


### Example ClusterRole
You can create a read-only ClusterRole and bind it to the ServiceAccount running the tool:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: k8s-cluster-info-reader
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "namespaces"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["argoproj.io"]
    resources: ["applications"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["cert-manager.io"]
    resources: ["certificates"]
    verbs: ["get", "list", "watch"]

```

### Example ClusterRoleBinding
``` yaml

apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: k8s-cluster-info-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: k8s-cluster-info-reader
subjects:
  - kind: ServiceAccount
    name: my-service-account
    namespace: my-namespace
```

---

## How this tool connects to kubernetes

The tool tries two connection methods in this order:

* External / Local Development

    Uses your local kubeconfig file:

    ```python
    config.load_kube_config()

    ```
  
    This is typically located at:

    ```
    ~/.kube/config
    ```

* In-Cluster (when running inside Kubernetes)

  If no local kubeconfig is found, it loads the in-cluster configuration:

  ```python
  config.load_incluster_config()
  ```

  This method uses the ServiceAccount token mounted into the Pod by Kubernetes.

### Accessing an External Kubernetes Cluster
If you want to run the tool outside Kubernetes but connect to a remote cluster:

* Obtain kubeconfig from the cluster

    From your cluster admin, or by running:

    ```
    kubectl config view --minify --flatten --context=<cluster-context> > kubeconfig
    ```

* Point the tool to your kubeconfig

    * Either set the KUBECONFIG environment variable:

        ```
        export KUBECONFIG=/path/to/kubeconfig
        ```

    * Or modify the tool to explicitly load it:
        
        ```
        config.load_kube_config(config_file="/path/to/kubeconfig")
        ```

* Ensure your kubeconfig user has the required permissions - you can use the same ClusterRole described earlier.

---

## Usage Examples

### Get cluster-wide deployment info

```
tools.get_k8s_cluster_info()
```

### Get ArgoCD applications without remembering API details

```
tools.get_custom_objects("argocd_applications")
```

### Get Cert-Manager certificates in default namespace

```
tools.get_custom_objects("certmanager_certificates", namespace="default")
```

### Get an unknown CRD (must provide details)

```
tools.get_custom_objects("mygroup.example.com", "v1", "widgets")
```

---
##Notes

When running inside a Kubernetes Pod, ensure the Pod’s ServiceAccount has the required RBAC permissions.

For external clusters, always secure your kubeconfig and do not commit it to Git.

This tool is read-only — it does not modify Kubernetes resources.