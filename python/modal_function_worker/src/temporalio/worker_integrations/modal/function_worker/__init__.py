"""Run Temporal workers inside Modal Functions.

Installed from the ``temporalio-worker-integrations-modal-function-worker`` distribution as
``temporalio.worker_integrations.modal.function_worker``. See the package README for a complete
Workflow and Activity example.
"""

from temporalio.worker_integrations.modal.function_worker._configure import (
    ModalWorkerConfig,
)
from temporalio.worker_integrations.modal.function_worker._run_worker import run_worker

__all__ = [
    "ModalWorkerConfig",
    "run_worker",
]
