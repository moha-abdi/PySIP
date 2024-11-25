import asyncio
import logging
import random
from enum import Enum
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass

from .logger import logger
from ..exceptions import SIPError, OperationTimeout


class RetryStrategy(Enum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_delay: float = 0.5
    max_delay: float = 4.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    jitter: bool = True


class RetryHandler:
    """
    Generic retry handler for SIP operations.
    Can be used by SipClient, SipCore, or any other component
    that needs retry logic.
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.pending_operations: Dict[str, asyncio.Event] = {}

    def _calculate_delay(self, attempt: int) -> float:
        if self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.initial_delay * attempt
        else:  # EXPONENTIAL
            delay = self.config.initial_delay * (2 ** (attempt - 1))

        if self.config.jitter:
            jitter = random.uniform(-0.1, 0.1) * delay
            delay += jitter

        return min(delay, self.config.max_delay)

    async def execute_with_retry(
        self,
        operation: Callable,
        operation_id: str,
        *args,
        timeout: float = 2.0,
        **kwargs,
    ) -> bool:
        """
        Execute a SIP operation with retry logic

        Args:
            operation: The async function to execute
            operation_id: Unique identifier for this operation
            timeout: Maximum time to wait for operation completion
            *args, **kwargs: Arguments for the operation

        Returns:
            bool: True if operation succeeded, False otherwise

        Raises:
            SIPError: If operation fails with an error
        """
        completion_event = asyncio.Event()
        self.pending_operations[operation_id] = completion_event

        try:
            for attempt in range(1, self.config.max_attempts + 1):
                try:
                    await operation(*args, **kwargs)

                    try:
                        await asyncio.wait_for(completion_event.wait(), timeout=timeout)
                        return True

                    except asyncio.TimeoutError:
                        if attempt == self.config.max_attempts:
                            raise OperationTimeout(
                                f"Operation {operation_id} timed out after {attempt} attempts"
                            )

                        delay = self._calculate_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt} for {operation_id} timed out. "
                            f"Retrying in {delay:.2f} seconds..."
                        )
                        await asyncio.sleep(delay)

                except Exception as e:
                    if attempt == self.config.max_attempts:
                        raise SIPError(
                            f"Operation {operation_id} failed: {str(e)}"
                        ) from e

                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt} failed: {str(e)}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    await asyncio.sleep(delay)

        finally:
            self.pending_operations.pop(operation_id, None)

        return False

    def complete_operation(self, operation_id: str) -> None:
        """Called by message handler when operation succeeds"""
        if operation_id in self.pending_operations:
            self.pending_operations[operation_id].set()
