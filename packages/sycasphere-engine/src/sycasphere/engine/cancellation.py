# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : cancellation.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  定义后端中立、线程安全的 Engine 协作取消探针和令牌。

■ 主要函数功能:
  - CancellationProbe: 声明只读取消状态的协议。
  - CancellationToken: 提供只能从未取消变为已取消的线程安全令牌。

■ 功能特性:
  ✓ 使用 threading.Event 保证并发读取和取消的安全性。
  ✓ 允许科学后端只依赖只读取消探针。

■ 待办事项:
  - [ ] 后续任务在运行器和后端端口中消费取消探针。

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from threading import Event
from typing import Protocol, runtime_checkable

# =============================👐Seperate👐=============================
# Cooperative cancellation contracts
# =============================👐Seperate👐=============================


@runtime_checkable
class CancellationProbe(Protocol):
    """A read-only probe that reports whether cooperative cancellation was requested."""

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""


class CancellationToken:
    """A thread-safe, monotonic cancellation signal for one Engine operation."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        """Return whether this token has been cancelled."""
        return self._event.is_set()

    def cancel(self) -> None:
        """Request cancellation; repeated requests leave the token cancelled."""
        self._event.set()


__all__ = ["CancellationProbe", "CancellationToken"]
