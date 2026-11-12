"""Run Temporal workers inside Modal Functions.

.. warning::
    This package is experimental and may change in future versions.
    Use with caution in production environments.

Installed from the ``temporalio-modal-function-worker`` distribution as
``temporalio.worker_integrations.modal.function``. See the package README for a complete
Workflow and Activity example.
"""

from temporalio.worker_integrations.modal.function._configure import (
    ModalWorkerConfig,
)
from temporalio.worker_integrations.modal.function._run_worker import run_worker

__all__ = [
    "ModalWorkerConfig",
    "run_worker",
]
