#!/usr/bin/env python3
from cortexutils.responder import Responder
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import tempfile
import os

SUPPORTED_KINDS = {"pod", "cronjob", "job", "deployment", "daemonset"}


class K8sContainResourceResponder(Responder):
    def __init__(self):
        Responder.__init__(self)
        self.kubeconfig = self.get_param("config.kubeconfig", None, "Missing kubeconfig")
        self.default_namespace = self.get_param("config.default_namespace", "default")
        self.cordon_node = self.get_param("config.cordon_node", True)
        self.drain_node = self.get_param("config.drain_node", False)

    def resolve_target(self, raw_value):
        """Accepts 'namespace/kind/name' or 'namespace/name' (kind defaults to pod)."""
        if isinstance(raw_value, dict):
            raw_value = raw_value.get("data")
        value = str(raw_value).strip()
        parts = value.split("/")
        if len(parts) == 3:
            namespace, kind, name = parts
        elif len(parts) == 2:
            namespace, name = parts
            kind = "pod"
        elif len(parts) == 1:
            namespace, kind, name = self.default_namespace, "pod", parts[0]
        else:
            self.error(f"Could not parse target '{value}'. Use 'namespace/kind/name'.")
            return None
        kind = kind.lower()
        if kind not in SUPPORTED_KINDS:
            self.error(f"Unsupported kind '{kind}'. Supported: {sorted(SUPPORTED_KINDS)}")
            return None
            return None
        return namespace, kind, name

    def load_client(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ya
            f.write(self.kubeconfig)
            path = f.name
        try:
            config.load_kube_config(config_file=path)
        finally:
            os.unlink(path)
        return client.CoreV1Api(), client.BatchV1Api(), client.AppsV1Api()

    def cordon(self, core_v1, node_name):
        body = {"spec": {"unschedulable": True}}
        core_v1.patch_node(node_name, body)

    def evict_node_pods(self, core_v1, node_name):
        pods = core_v1.list_pod_for_all_namespaces(field_selece}")
        evicted = []
        for pod in pods.items:
            if pod.metadata.namespace == "kube-system":
                continue
            try:
                core_v1.delete_namespaced_pod(pod.metadata.namace_period_seconds=0)
                evicted.append(f"{pod.metadata.namespace}/{pod.metadata.name}")
            except ApiException:
                pass
        return evicted

    def run(self):
        Responder.run(self)
        target = self.resolve_target(self.get_data())
        if target is None:
            return
        namespace, kind, name = target

        core_v1, batch_v1, apps_v1 = self.load_client()

        node_name = None
        deleted = False

        try:
            if kind == "pod":
                pod = core_v1.read_namespaced_pod(name, namesp
                node_name = pod.spec.node_name
                core_v1.delete_namespaced_pod(name, namespace,
                deleted = True
            elif kind == "cronjob":
                batch_v1.delete_namespaced_cron_job(name, namespace)
                jobs = batch_v1.list_namespaced_job(namespace,ame}")
                for job in batch_v1.list_namespaced_job(namespace).items:
                    owners = job.metadata.owner_references or
                    if any(o.name == name for o in owners):
                        batch_v1.delete_namespaced_job(job.metation_policy="Foreground")
                deleted = True
            elif kind == "job":
                batch_v1.delete_namespaced_job(name, namespace, propagation_policy="Foreground")
                deleted = True
            elif kind == "deployment":
                apps_v1.delete_namespaced_deployment(name, nam
                deleted = True
            elif kind == "daemonset":
                apps_v1.delete_namespaced_daemon_set(name, namespace)
                deleted = True
        except ApiException as e:
            self.error(f"Kubernetes API error deleting {kind} } (status {e.status})")
            return

        cordoned = False
        evicted_pods = []
        if node_name and self.cordon_node:
            try:
                self.cordon(core_v1, node_name)
                cordoned = True
            except ApiException as e:
                self.error(f"Deleted {kind} but failed to cordn}")
                return
            if self.drain_node:
                evicted_pods = self.evict_node_pods(core_v1, node_name)

        self.report({
            "action": "contain-k8s-resource",
            "namespace": namespace,
            "kind": kind,
            "name": name,
            "deleted": deleted,
            "node": node_name,
            "nodeCordoned": cordoned,
            "nodeDrained": self.drain_node and cordoned,
            "additionalPodsEvicted": evicted_pods,
        })

    def operations(self, raw):
        return [self.build_operation("AddTagToCase", tag="k8s:


if __name__ == "__main__":
