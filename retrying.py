# pylama:ignore=E701

from collections.abc import Sequence
from dataclasses import dataclass, field, InitVar
from datetime import datetime, timedelta
from functools import wraps
from itertools import count
from inspect import iscoroutinefunction
from random import Random
from typing import Any, Callable, Coroutine, List, Optional, Union
import time
import asyncio

RetryCallback = Callable[[Any, 'Context'], bool]
DecisionHandler = Callable[[Any, Exception, 'Context'], bool]
T = Union[Callable, Coroutine]


def retry(func: T = None, **opts) -> T:
    if func is None:
        return lambda f: retry(f, **opts)

    if iscoroutinefunction(func):
        async def wrapped(*args, **kwargs) -> Any:
            z = AsyncRetry(func, **opts)
            return (await z(*args, **kwargs))
    else:
        def wrapped(*args, **kwargs) -> Any:
            return Retry(func, **opts)(*args, **kwargs)

    return wraps(func)(wrapped)


@dataclass
class Context(Sequence):
    _attempts: List['Attempt'] = field(default_factory=list)
    backoff: 'Backoff' = None
    timeout: Optional[datetime] = None

    def __iter__(self):
        return iter(self.attempts)

    def __getitem__(self, index):
        return self._attempts[index]

    def __len__(self):
        return len(self._attempts)

    @property
    def tries(self) -> int:
        return self.__len__()

    def add_attempts(self, *args, **kwargs) -> 'Attempt':
        a = Attempt(*args, **kwargs)
        self._attempts.append(a)
        return a


def continue_callback(obj, ctx) -> True:
    return True


def stop_callback(obj, ctx) -> False:
    return False


@dataclass(frozen=True)
class Decision:
    on_result: RetryCallback = field(default=stop_callback)
    on_exception: RetryCallback = field(default=continue_callback)

    def __call__(self, result, exception, ctx) -> bool:
        if exception is not None:
            return self.on_exception(exception, ctx)
        return self.on_result(result, ctx)


@dataclass
class Retry:
    func: Callable
    on_result: InitVar[RetryCallback] = None
    on_exception: InitVar[RetryCallback] = None
    on_global: InitVar[DecisionHandler] = None
    max_tries: Optional[int] = None
    backoff: Optional['Backoff'] = None
    giveup_after: Optional[timedelta] = None
    wrap_exception: bool = False
    reraise: bool = False

    def __post_init__(self, on_result, on_exception, on_global):
        self.backoff = self.backoff or Backoff(0)
        assert not (on_global and on_result), 'global and result are unique together'
        assert not (on_global and on_exception), 'global and exception are unique together'
        self.decision = on_global or Decision(
            on_result or stop_callback,
            on_exception or continue_callback
        )

    def check_limits(self, i, ctx):
        current_timeout = start = datetime.now()
        current_timespan = None
        if i and ctx.backoff:
            current_timespan = next(ctx.backoff)
            current_timeout += current_timespan
        if i and ctx.timeout and ctx.timeout <= current_timeout:
            self.throw(TimeoutError, 'timeout limit reached', ctx)
        if i and current_timespan:
            wait = current_timespan.total_seconds()
            time.sleep(wait)
            start = datetime.now()
        return start

    def throw(self, cls, message, ctx):
        if self.reraise:
            if ctx[-1].exception:
                raise ctx[-1].exception
            else:
                raise ValueError(ctx[-1].result)
        raise cls('timeout limit reached', ctx)

    def transmit(self, *args, **kwargs):
        result, error, try_again = None, None, False
        try:
            result = self.func(*args, **kwargs)
        except TryAgain:
            try_again = True
        except Exception as exc:
            error = exc
        return result, error, try_again

    def __call__(self, *args, **kwargs):
        def run():
            start = datetime.now()
            timeout = None
            if self.giveup_after:
                timeout = start + self.giveup_after
            ctx = Context(backoff=self.backoff, timeout=timeout)
            for i in count():
                if i == self.max_tries:
                    self.throw(MaxRetriesError, 'max tries limit reached', ctx)

                start = self.check_limits(i, ctx)

                try:
                    result, error, try_again = self.transmit(*args, **kwargs)
                    try:
                        if try_again or self.decision(result, error, ctx):
                            continue
                    except Exception as exc:
                        msg = 'Decision raised: %s' % exc
                        raise RuntimeError(msg, result, error) from exc
                    else:
                        if error:
                            if self.wrap_exception:
                                raise RetryError(str(error), ctx) from error
                            raise error
                        else:
                            return result

                finally:
                    ctx.add_attempts(exception=error, result=result, time=start)
        return run()


@dataclass
class AsyncRetry:
    coro: Callable
    on_result: InitVar[RetryCallback] = None
    on_exception: InitVar[RetryCallback] = None
    on_global: InitVar[DecisionHandler] = None
    max_tries: Optional[int] = None
    backoff: Optional['Backoff'] = None
    giveup_after: Optional[timedelta] = None
    wrap_exception: bool = False
    reraise: bool = False

    def __post_init__(self, on_result, on_exception, on_global):
        self.backoff = self.backoff or Backoff(0)
        assert not (on_global and on_result), 'global and result are unique together'
        assert not (on_global and on_exception), 'global and exception are unique together'
        self.decision = on_global or Decision(
            on_result or stop_callback,
            on_exception or continue_callback
        )

    async def check_limits(self, i, ctx):
        current_timeout = start = datetime.now()
        current_timespan = None
        if i and ctx.backoff:
            current_timespan = next(ctx.backoff)
            current_timeout += current_timespan
        if i and ctx.timeout and ctx.timeout <= current_timeout:
            self.throw(TimeoutError, 'timeout limit reached', ctx)
        if i and current_timespan:
            wait = current_timespan.total_seconds()
            await asyncio.sleep(wait)
            start = datetime.now()
        return start

    def throw(self, cls, message, ctx):
        if self.reraise:
            if ctx[-1].exception:
                raise ctx[-1].exception
            else:
                raise ValueError(ctx[-1].result)
        raise cls('timeout limit reached', ctx)

    async def transmit(self, *args, **kwargs):
        result, error, try_again = None, None, False
        try:
            result = await self.coro(*args, **kwargs)
        except TryAgain:
            try_again = True
        except Exception as exc:
            error = exc
        return result, error, try_again

    def __call__(self, *args, **kwargs):
        async def run():
            start = datetime.now()
            timeout = None
            if self.giveup_after:
                timeout = start + self.giveup_after
            ctx = Context(backoff=self.backoff, timeout=timeout)
            for i in count():
                if i == self.max_tries:
                    self.throw(MaxRetriesError, 'max tries limit reached', ctx)

                start = await self.check_limits(i, ctx)

                try:
                    result, error, try_again = await self.transmit(*args, **kwargs)
                    try:
                        if try_again or self.decision(result, error, ctx):
                            continue
                    except Exception as exc:
                        msg = 'Decision raised: %s' % exc
                        raise RuntimeError(msg, result, error) from exc
                    else:
                        if error:
                            if self.wrap_exception:
                                raise RetryError(str(error), ctx) from error
                            raise error
                        else:
                            return result

                finally:
                    ctx.add_attempts(exception=error, result=result, time=start)
        return run()


@dataclass(frozen=True)
class Attempt:
    result: Any
    exception: Optional[Exception]
    time: datetime


@dataclass(frozen=True)
class RetryError(Exception):
    message: str
    context: Context


@dataclass(frozen=True)
class TimeoutError(RetryError):
    pass


@dataclass(frozen=True)
class MaxRetriesError(RetryError):
    pass


@dataclass
class RandBackoff:
    min: timedelta
    max: timedelta

    def __post_init__(self):
        self.interval = None
        self.random = Random(time.monotonic() * 1000_000_000)

    def __next__(self):
        self.interval = self.get_interval()
        return self.interval

    def get_interval(self) -> timedelta:
        salt = self.random.random()
        return self.min + (salt * (self.max - self.min))


@dataclass
class Backoff:
    seconds: InitVar[int] = 0
    milliseconds: InitVar[int] = 0
    microseconds: InitVar[int] = 0

    def __post_init__(self, seconds, milliseconds, microseconds):
        self.interval = timedelta(seconds=seconds,
                                  milliseconds=milliseconds,
                                  microseconds=microseconds)

    def __next__(self):
        return self.interval


@dataclass
class ExponentialBackoff(Backoff):
    max: timedelta = field(default=timedelta(seconds=60))
    randomization_factor: float = 0.5
    multiplier: float = 1.5

    def __post_init__(self, seconds, milliseconds, microseconds):
        self.interval = None
        self.initial = timedelta(seconds=seconds,
                                 milliseconds=milliseconds,
                                 microseconds=microseconds)
        self.random = Random(time.monotonic() * 1000_000_000)
        self.reset()

    def reset(self):
        self.current = self.initial

    def __next__(self):
        self.interval = self.get_interval()
        self.increment()
        return self.interval

    def increment(self):
        self.current = min(self.max, self.current * self.multiplier)
        # ensure at least 100 milliseconds
        self.current = max(self.current, timedelta(seconds=.1))

    def get_interval(self) -> timedelta:
        salt = self.random.random()
        delta = self.randomization_factor * self.current
        min_interval = self.current - delta
        max = self.current + delta
        return min_interval + (salt * (max - min_interval))


class TryAgain(Exception):
    pass
