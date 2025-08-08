# Open Web UI tools

# [Kubernetes cluster info ](kubernetes_info)

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