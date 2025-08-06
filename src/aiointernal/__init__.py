from __future__ import annotations
from culsans import Queue, QueueShutDown
from threading import Thread
import sys
import asyncio
from typing import TypeVar, Generic, Callable, Generator, Any, overload, Optional
from types import GenericAlias, coroutine
from inspect import isgeneratorfunction
from abc import ABC, abstractmethod
from aiologic import REvent


if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec, Concatenate
else:
    from typing import ParamSpec, Concatenate


P = ParamSpec("P")
R = TypeVar("R")

_OwnerT = TypeVar("_OwnerT", bound="HeapThread")

__author__ = "Vizonex"
__license__ = "MIT"
__version__ = "0.1.0"
__all__ = ("HeapThread", "sync", "__author__", "__version__", "__license__")



class HeapThread(ABC):
    def __init__(
        self,
        heap_size: int = 0,
        queue_factory: Callable[..., Queue]
        | type[
            Queue[tuple[asyncio.Future, Callable[[int], R], tuple[Any], dict[str, Any]]]
        ] = Queue,
        exception_handler: Callable[[Exception], None] | None = None,
    ):
        self._queue = queue_factory(heap_size)
        self._thread = Thread(target=self.__run)
        self._closed = REvent()
        self._is_running = False
        self._exception_handler = exception_handler

    @property
    def is_running(self) -> bool:
        """determines if the thread is active"""
        return self._is_running

    @property
    def is_closed(self) -> bool:
        """Determines if the `HeapThread` is closed"""
        return self._closed.is_set()

    @abstractmethod
    def on_setup(self) -> None:
        """method for setting up a crticial structure for the `HeapThread` you wish to create carry"""

    @abstractmethod
    def on_shutdown(self) -> None:
        """method for shutting down a critical structure ran in your `HeapThread`"""

    def _run_setup(self) -> None:
        if not getattr(self.on_setup, "__isabstractmethod__", False):
            return self.on_setup()

    def _run_shutdown(self) -> None:
        if not getattr(self.on_shutdown, "__isabstractmethod__", False):
            return self.on_shutdown()

    @property
    def is_shutdown(self) -> bool:
        """Determines if the main thread requires shutdown"""
        return self._queue.is_shutdown

    def shutdown(self, immediate: bool = False):
        """Shutdown later or on the next avalible frame the thread gets and close

        Parameters
        ----------

        :param immediate: shutdown abruptly if a generator is running or is still in session.
        otherwise wait for the next avalible time to exit. by default it will do so gracefully.
        """
        if not self._queue.is_shutdown:
            self._queue.shutdown(immediate=immediate)

    def run(self):
        """Starts the thread so asynchronous communication can begin raises `RuntimeError` is
        this thread was already started"""
        if not self._is_running:
            self._thread.start()
            self._is_running = True
        else:
            raise RuntimeError(f"{self!r} is already running")

    async def __aenter__(self):
        self.run()
        return self

    async def close(self, immediate: bool = False) -> bool:
        """Shuts down heap thread and waits for confirmation of closure"""
        # abrupt shutdown unless user did so gracefully.
        self.shutdown(immediate)
        # wait for signal of closure
        return await self._closed

    async def __aexit__(self, *args):
        await self.close(immediate=True)

    def _process(
        self,
        fut: asyncio.Future[R | list[R]],
        func: Callable[P, R | Generator[Any, Any, R]],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        # NOTE all yeilds are treated as signals or checkpoints
        # which can help with something such as a if a future was being
        # cancelled or the main Owner was shut down remember
        # not to starve the critical thread if you can.
        # the less time you take the safer the thread becomes.
        
        # Last chance to abort or not.
        if fut.cancelled():
            return fut
        
        try:
            if isgeneratorfunction(func):
                result: list[R] = list()
                for s in func(*args, **kwargs):
                    if self.is_shutdown:
                        fut.cancel()
                        return fut
                    elif fut.cancelled():
                        # User on the other end cut the future
                        return fut
                    else:
                        result.append(s)
            else:
                result = func(*args, **kwargs)
                if fut.cancelled():
                    return fut
            fut.get_loop().call_soon_threadsafe(fut.set_result, result)
        except Exception as e:
            fut.get_loop().call_soon_threadsafe(fut.set_exception, e)
        return fut

    
    def __run(self):
        self._run_setup()
        try:
            while item := self._queue.sync_get():
                try:
                    fut, func, args, kw = item
                    # We pass self so that Internal structures can be interacted with
                    self._process(fut, func, self, *args, **kw)
                except Exception as e:
                    if self._exception_handler:
                        self._exception_handler(e)
                    else:
                        self.shutdown()
                        self._run_shutdown()
                        self._closed.set()
                    raise e
        except QueueShutDown:
            self._run_shutdown()
            self._closed.set()

class _async_partial(Generic[_OwnerT, P, R]):
    def __init__(self, owner: _OwnerT, func: Callable[P, R]) -> None:
        self._func = func
        self._owner = owner

    async def __call__(self, *args: P.args, **kwds: P.kwargs) -> R:
        _fut: asyncio.Future[R] = asyncio.get_event_loop().create_future()
        try:
            await self._owner._queue.async_put((_fut, self._func, args, kwds))
        except QueueShutDown:
            _fut.cancel()
        return await _fut

    def queue(self, *args: P.args, **kwds: P.kwargs) -> asyncio.Future[R]:
        """queues the function to run as a task that can be cancelled However
        this only works if the function is a `Generator`"""
        if not isgeneratorfunction(self._func):
            raise RuntimeError(
                "Implementation will not communicate as intended"
                " if the function is not a Generator"
            )

        _fut: asyncio.Future[R] = asyncio.get_event_loop().create_future()
        try:
            self._owner._queue.sync_put((_fut, self._func, args, kwds))
        except QueueShutDown:
            _fut.cancel()
        return _fut


class sync(Generic[_OwnerT, P, R]):
    """
    A Special member descriptor marker to tell the main thread executing critical logic
    to queue this function up for later and will tell the owning thread how to
    handle queing items
    """

    __class_getitem__ = classmethod(GenericAlias)

    @overload
    def __init__(
        self: "sync[_OwnerT, P, list[R]]",
        func: Callable[Concatenate[_OwnerT, P], Generator[Any, Any, R]],
    ) -> None: ...

    @overload
    def __init__(self, func: Callable[Concatenate[_OwnerT, P], R]) -> None: ...

    def __init__(
        self, func: Callable[Concatenate[_OwnerT, P], R | Generator[Any, Any, R]]
    ) -> None:
        self._func = func
        self._name = self._func.__name__

    @property
    def __doc__(self):
        return self._func.__doc__

    def __get__(self, instance: _OwnerT, owner: Any) -> _async_partial[_OwnerT, P, R]:
        if not hasattr(self, "_partial"):
            self._partial = _async_partial(instance, self._func)
        return self._partial
