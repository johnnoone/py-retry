import pytest
from itertools import cycle
from retrying import retry, Backoff, ExponentialBackoff, RandBackoff
from retrying import RetryError, MaxRetriesError, TimeoutError, TryAgain
from unittest.mock import Mock
from datetime import timedelta


class Dumb(Exception):
    pass


async def coro(stub):
    action = stub()
    if action == 'again':
        raise TryAgain
    if action == 'dumb':
        raise Dumb()
    if action == 'exception':
        raise Exception()
    return action


@pytest.fixture
def mock():
    return Mock()


@pytest.mark.asyncio
async def test_inherits_docs():
    @retry
    def example():
        """Docstring"""
    assert example.__name__ == 'example'
    assert example.__doc__ == 'Docstring'


@pytest.mark.asyncio
async def test_retry_until_success(mock):
    sentinel = 'ok'
    mock.side_effect = [
        'dumb',
        'exception',
        sentinel,
        'exception',
        sentinel
    ]
    assert (await retry(coro)(mock)) == sentinel
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_on_exception(mock):
    sentinel = 'dumb'

    def callback(error, ctx):
        return not isinstance(error, Dumb)

    mock.side_effect = ['exception', sentinel, sentinel]
    with pytest.raises(Dumb):
        await retry(coro, on_exception=callback)(mock)
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_wrap_expection(mock):
    sentinel = 'dumb'

    def callback(error, ctx):
        return not isinstance(error, Dumb)

    mock.side_effect = ['exception', sentinel, sentinel]
    with pytest.raises(RetryError):
        await retry(coro, on_exception=callback, wrap_exception=True)(mock)
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_on_result(mock):
    sentinel = 'bar'

    def callback(result, ctx):
        return result == 'foo'

    mock.side_effect = ['foo', 'foo', sentinel, sentinel]
    assert (await retry(coro, on_result=callback)(mock)) == sentinel
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_on_global(mock):
    sentinel = 'bar'

    def callback(result, exception, ctx):
        return result == 'foo'

    mock.side_effect = ['foo', 'foo', sentinel, sentinel]
    assert (await retry(coro, on_global=callback)(mock)) == sentinel
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_on_global_caused_runtime_error(mock):
    def callback(result, exception, ctx):
        raise Exception('No reason')

    mock.side_effect = ['foo']
    with pytest.raises(RuntimeError):
        await retry(coro, on_global=callback)(mock)


@pytest.mark.asyncio
async def test_max_tries(mock):
    mock.side_effect = cycle(['dumb', 'exception'])
    with pytest.raises(MaxRetriesError):
        await retry(coro, max_tries=4)(mock)
    assert mock.call_count == 4


@pytest.mark.asyncio
async def test_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    await retry(coro, backoff=Backoff(.001))(mock)
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_exponential_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    await retry(coro, backoff=ExponentialBackoff(.001))(mock)
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_rand_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    await retry(coro, backoff=RandBackoff(timedelta(seconds=.1),
                                          timedelta(seconds=.2)))(mock)
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_custom_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    await retry(coro, backoff=cycle([timedelta(seconds=.001)]))(mock)
    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_backoff_on_context(mock):
    def callback(result, ctx):
        assert isinstance(ctx.backoff, Backoff)
        return result != 'bar'

    mock.side_effect = cycle(['foo', 'bar'])
    assert (await retry(coro, on_result=callback, max_tries=4)(mock)) == 'bar'
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_change_backoff_on_context(mock):
    def callback(result, ctx):
        ctx.backoff = Backoff(seconds=.1)
        return result != 'bar'

    mock.side_effect = cycle(['foo', 'bar'])
    assert (await retry(coro, on_result=callback, max_tries=4)(mock)) == 'bar'
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_timeout(mock):
    def callback(result, ctx):
        return True

    mock.side_effect = cycle(['foo', 'bar'])
    with pytest.raises(TimeoutError):
        await retry(coro,
                    giveup_after=timedelta(seconds=1),
                    on_result=callback, backoff=Backoff(seconds=1))(mock)
    assert mock.call_count >= 1


@pytest.mark.asyncio
async def test_reraise_on_maxtries_throws_value_error(mock):
    def callback(result, ctx):
        return True

    mock.side_effect = cycle(['foo', 'bar'])
    with pytest.raises(ValueError):
        await retry(coro, on_result=callback, max_tries=4, reraise=True)(mock)


@pytest.mark.asyncio
async def test_reraise_on_maxtries_has_effect(mock):
    mock.side_effect = cycle(['dumb'])
    with pytest.raises(Dumb):
        await retry(coro, max_tries=4, reraise=True)(mock)
    assert mock.call_count >= 4


@pytest.mark.asyncio
async def test_reraise_on_timeout_throws_value_error(mock):
    def callback(result, ctx):
        return True

    mock.side_effect = cycle(['foo', 'bar'])
    with pytest.raises(ValueError):
        await retry(coro,
                    giveup_after=timedelta(seconds=1),
                    on_result=callback,
                    backoff=Backoff(seconds=1),
                    reraise=True)(mock)


@pytest.mark.asyncio
async def test_reraise_on_timeout_has_effect(mock):
    mock.side_effect = cycle(['dumb'])
    with pytest.raises(Dumb):
        await retry(coro,
                    giveup_after=timedelta(seconds=1),
                    backoff=Backoff(seconds=1),
                    reraise=True)(mock)


@pytest.mark.asyncio
async def test_try_again_timeout(mock):
    mock.side_effect = cycle(['again'])
    with pytest.raises(TimeoutError):
        await retry(coro,
                    giveup_after=timedelta(seconds=1),
                    backoff=Backoff(seconds=1))(mock)


@pytest.mark.asyncio
async def test_try_again_max_retries(mock):
    mock.side_effect = cycle(['again'])
    with pytest.raises(MaxRetriesError):
        await retry(coro, max_tries=4)(mock)
