import pytest
from itertools import cycle
from retrying import retry, Backoff, ExponentialBackoff, RandBackoff
from retrying import RetryError, MaxRetriesError, TimeoutError, TryAgain
from unittest.mock import Mock
from datetime import timedelta


class Dumb(Exception):
    pass


def func(stub):
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


def test_inherits_docs():
    @retry
    def example():
        """Docstring"""
    assert example.__name__ == 'example'
    assert example.__doc__ == 'Docstring'


def test_retry_until_success(mock):
    sentinel = 'ok'
    mock.side_effect = [
        'dumb',
        'exception',
        sentinel,
        'exception',
        sentinel
    ]
    assert retry(func)(mock) == sentinel
    assert mock.call_count == 3


def test_on_exception(mock):
    sentinel = 'dumb'

    def callback(error, ctx):
        return not isinstance(error, Dumb)

    mock.side_effect = ['exception', sentinel, sentinel]
    with pytest.raises(Dumb):
        retry(func, on_exception=callback)(mock)
    assert mock.call_count == 2


def test_wrap_expection(mock):
    sentinel = 'dumb'

    def callback(error, ctx):
        return not isinstance(error, Dumb)

    mock.side_effect = ['exception', sentinel, sentinel]
    with pytest.raises(RetryError):
        retry(func, on_exception=callback, wrap_exception=True)(mock)
    assert mock.call_count == 2


def test_on_result(mock):
    sentinel = 'bar'

    def callback(result, ctx):
        return result == 'foo'

    mock.side_effect = ['foo', 'foo', sentinel, sentinel]
    assert retry(func, on_result=callback)(mock) == sentinel
    assert mock.call_count == 3


def test_on_global(mock):
    sentinel = 'bar'

    def callback(result, exception, ctx):
        return result == 'foo'

    mock.side_effect = ['foo', 'foo', sentinel, sentinel]
    assert retry(func, on_global=callback)(mock) == sentinel
    assert mock.call_count == 3


def test_on_global_caused_runtime_error(mock):
    def callback(result, exception, ctx):
        raise Exception('No reason')

    mock.side_effect = ['foo']
    with pytest.raises(RuntimeError):
        retry(func, on_global=callback)(mock)


def test_max_tries(mock):
    mock.side_effect = cycle(['dumb', 'exception'])
    with pytest.raises(MaxRetriesError):
        retry(func, max_tries=4)(mock)
    assert mock.call_count == 4


def test_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    retry(func, backoff=Backoff(.001))(mock)
    assert mock.call_count == 3


def test_exponential_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    retry(func, backoff=ExponentialBackoff(.001))(mock)
    assert mock.call_count == 3


def test_rand_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    retry(func, backoff=RandBackoff(timedelta(seconds=.1),
                                    timedelta(seconds=.2)))(mock)
    assert mock.call_count == 3


def test_custom_backoff(mock):
    mock.side_effect = cycle(['dumb', 'exception', 'foo'])
    retry(func, backoff=cycle([timedelta(seconds=.001)]))(mock)
    assert mock.call_count == 3


def test_backoff_on_context(mock):
    def callback(result, ctx):
        assert isinstance(ctx.backoff, Backoff)
        return result != 'bar'

    mock.side_effect = cycle(['foo', 'bar'])
    assert retry(func, on_result=callback, max_tries=4)(mock) == 'bar'
    assert mock.call_count == 2


def test_change_backoff_on_context(mock):
    def callback(result, ctx):
        ctx.backoff = Backoff(seconds=.1)
        return result != 'bar'

    mock.side_effect = cycle(['foo', 'bar'])
    assert retry(func, on_result=callback, max_tries=4)(mock) == 'bar'
    assert mock.call_count == 2


def test_timeout(mock):
    def callback(result, ctx):
        return True

    mock.side_effect = cycle(['foo', 'bar'])
    with pytest.raises(TimeoutError):
        retry(func,
              giveup_after=timedelta(seconds=1),
              on_result=callback, backoff=Backoff(seconds=1))(mock)
    assert mock.call_count >= 1


def test_reraise_on_maxtries_throws_value_error(mock):
    def callback(result, ctx):
        return True

    mock.side_effect = cycle(['foo', 'bar'])
    with pytest.raises(ValueError):
        retry(func, on_result=callback, max_tries=4, reraise=True)(mock)


def test_reraise_on_maxtries_has_effect(mock):
    mock.side_effect = cycle(['dumb'])
    with pytest.raises(Dumb):
        retry(func, max_tries=4, reraise=True)(mock)
    assert mock.call_count >= 4


def test_reraise_on_timeout_throws_value_error(mock):
    def callback(result, ctx):
        return True

    mock.side_effect = cycle(['foo', 'bar'])
    with pytest.raises(ValueError):
        retry(func,
              giveup_after=timedelta(seconds=1),
              on_result=callback,
              backoff=Backoff(seconds=1),
              reraise=True)(mock)


def test_reraise_on_timeout_has_effect(mock):
    mock.side_effect = cycle(['dumb'])
    with pytest.raises(Dumb):
        retry(func,
              giveup_after=timedelta(seconds=1),
              backoff=Backoff(seconds=1),
              reraise=True)(mock)


def test_try_again_timeout(mock):
    mock.side_effect = cycle(['again'])
    with pytest.raises(TimeoutError):
        retry(func,
              giveup_after=timedelta(seconds=1),
              backoff=Backoff(seconds=1))(mock)


def test_try_again_max_retries(mock):
    mock.side_effect = cycle(['again'])
    with pytest.raises(MaxRetriesError):
        retry(func, max_tries=4)(mock)
