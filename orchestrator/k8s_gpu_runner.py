"""
Runs a test/validation command on the GKE cluster's L4 node pool as a
Kubernetes Job, and returns its logs + exit status to the loop. Anything in
the roadmap tagged requires_gpu (bench, differential-oracle runs, driver
verifier soaks, density tests) goes through here rather than running
wherever the orchestrator process happens to live.

Requires: pip install kubernetes
Auth: `gcloud container clusters get-credentials <cluster> --zone <zone>`
      before running the loop, so ~/.kube/config points at the GKE cluster.
"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass

from kubernetes import client, config as kube_config


@dataclass
class GpuJobResult:
    succeeded: bool
    logs: str
    exit_code: int | None


class GpuJobRunner:
    def __init__(self, namespace: str = "kayfabe-loop", node_pool_label: str = "l4-pool"):
        kube_config.load_kube_config()  # assumes get-credentials was already run
        self.batch = client.BatchV1Api()
        self.core = client.CoreV1Api()
        self.namespace = namespace
        self.node_pool_label = node_pool_label
        self._ensure_namespace()

    def _ensure_namespace(self):
        try:
            self.core.read_namespace(self.namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                self.core.create_namespace(
                    client.V1Namespace(metadata=client.V1ObjectMeta(name=self.namespace))
                )
            else:
                raise

    def run(self, image: str, command: list[str], phase: str, task_id: str,
            timeout_s: int = 3600, gpu_count: int = 1) -> GpuJobResult:
        job_name = f"kf-{phase.lower()}-{task_id.lower()}-{uuid.uuid4().hex[:6]}"

        job = client.V1Job(
            metadata=client.V1ObjectMeta(name=job_name, namespace=self.namespace),
            spec=client.V1JobSpec(
                backoff_limit=0,
                active_deadline_seconds=timeout_s,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "kayfabe-loop-gpu-job"}),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        # Pin to the L4 node pool; requires the pool to be
                        # labeled cloud.google.com/gke-nodepool=<node_pool_label>
                        # (GKE sets this automatically from the pool name).
                        node_selector={"cloud.google.com/gke-nodepool": self.node_pool_label},
                        tolerations=[client.V1Toleration(
                            key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")],
                        containers=[client.V1Container(
                            name="gpu-test",
                            image=image,
                            command=command,
                            resources=client.V1ResourceRequirements(
                                limits={"nvidia.com/gpu": str(gpu_count)}
                            ),
                            security_context=client.V1SecurityContext(
                                privileged=True  # kayfabe needs /dev/kvm + real device access;
                                                 # narrow this to specific device mounts once
                                                 # the exact requirement set is known (P1/P2)
                            ),
                        )],
                    ),
                ),
            ),
        )

        self.batch.create_namespaced_job(namespace=self.namespace, body=job)
        exit_code = self._wait(job_name, timeout_s)
        logs = self._logs(job_name)
        self.batch.delete_namespaced_job(
            name=job_name, namespace=self.namespace,
            body=client.V1DeleteOptions(propagation_policy="Foreground"),
        )
        return GpuJobResult(succeeded=(exit_code == 0), logs=logs, exit_code=exit_code)

    def _wait(self, job_name: str, timeout_s: int) -> int | None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            job = self.batch.read_namespaced_job_status(job_name, self.namespace)
            if job.status.succeeded:
                return 0
            if job.status.failed:
                return 1
            time.sleep(5)
        return None  # timed out

    def _logs(self, job_name: str) -> str:
        pods = self.core.list_namespaced_pod(
            self.namespace, label_selector=f"job-name={job_name}"
        ).items
        if not pods:
            return "(no pod found for job -- check node pool capacity/taints)"
        return self.core.read_namespaced_pod_log(pods[0].metadata.name, self.namespace)
