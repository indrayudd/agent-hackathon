"""Kernel pool manager for parallel subagent execution."""
from __future__ import annotations

import logging
import threading

from backend.services.kernel_manager import (
    get_or_create_kernel,
    execute_code,
    shutdown_kernel,
)

_LOG = logging.getLogger(__name__)


class KernelPoolManager:
    """Manages a main kernel + N subagent kernels per session."""

    def __init__(self):
        self._main_kernels: dict[str, object] = {}  # session_id -> client
        self._sub_kernels: dict[str, list[str]] = {}  # session_id -> [kernel_ids]
        self._lock = threading.Lock()

    def get_main_kernel(self, session_id: str) -> object:
        with self._lock:
            if session_id not in self._main_kernels:
                self._main_kernels[session_id] = get_or_create_kernel(session_id)
            return self._main_kernels[session_id]

    def allocate_subagent_kernels(self, session_id: str, n: int) -> list[str]:
        kernel_ids = []
        with self._lock:
            self._sub_kernels.setdefault(session_id, [])
        for i in range(n):
            kid = f"{session_id}_sub_{i}"
            get_or_create_kernel(kid)
            with self._lock:
                self._sub_kernels[session_id].append(kid)
            kernel_ids.append(kid)
            _LOG.info("Allocated subagent kernel: %s", kid)
        return kernel_ids

    def execute_on_subkernel(
        self, kernel_id: str, code: str, timeout: int = 60, cell_id: str | None = None,
    ) -> tuple[list, str | None]:
        return execute_code(kernel_id, code, timeout=timeout, cell_id=cell_id)

    def inject_dataset_preamble(self, kernel_id: str, session_dir: str) -> None:
        """Load the cached parquet into a subagent kernel."""
        code = (
            "import pandas as pd\nimport numpy as np\n"
            "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
            "import warnings\nwarnings.filterwarnings('ignore')\n"
            f"df = pd.read_parquet('{session_dir}/.cache/df_clean.parquet')\n"
            f"print(f'Loaded {{len(df)}} rows x {{len(df.columns)}} cols')"
        )
        execute_code(kernel_id, code, timeout=15)

    def shutdown_subagent_kernels(self, session_id: str) -> None:
        with self._lock:
            kernel_ids = self._sub_kernels.pop(session_id, [])
        for kid in kernel_ids:
            try:
                shutdown_kernel(kid)
                _LOG.info("Shutdown subagent kernel: %s", kid)
            except Exception as exc:
                _LOG.warning("Failed to shutdown %s: %s", kid, exc)

    def shutdown_all(self, session_id: str) -> None:
        self.shutdown_subagent_kernels(session_id)
        with self._lock:
            self._main_kernels.pop(session_id, None)
        try:
            shutdown_kernel(session_id)
        except Exception:
            pass
