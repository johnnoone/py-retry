Retrying
========

Retrying is an Apache 2.0 licensed general-purpose retrying library, written in Python, to simplify the task of adding retry behavior to just about anything.

The simplest use case is retrying a flaky function whenever an Exception occurs until a value is returned.

::

    import random
    from retrying import retry

    @retry
    def do_something_unreliable():
        if random.randint(0, 10) > 1:
            raise IOError("Broken sauce, everything is hosed!!!111one")
        else:
            return "Awesome sauce!"

    print do_something_unreliable()


Features
--------

*   Generic Decorator API
*   Specify stop condition (i.e. limit by number of attempts)
*   Specify wait condition (i.e. exponential backoff sleeping between attempts)
*   Customize retrying on Exceptions
*   Customize retrying on expected returned result


Installation
------------

To install retrying, simply::

    $ pip install retrying


Examples
--------

As you saw above, the default behavior is to retry forever without waiting.

::

    @retry
    def never_give_up_never_surrender():
        print "Retry forever ignoring Exceptions, don't wait between retries"

Let’s be a little less persistent and set some boundaries, such as the number of attempts before giving up.

::

    @retry(max_tries=7)
    def stop_after_7_attempts():
        print "Stopping after 7 attempts"

We don’t have all day, so let’s set a boundary for how long we should be retrying stuff.

::

    @retry(giveup_after=timedelta(seconds=10))
    def stop_after_10_s():
        print "Stopping after 10 seconds"

Most things don’t like to be polled as fast as possible, so let’s just wait 2 seconds between retries.

::

    @retry(backoff=Backoff(seconds=2))
    def wait_2_s():
        print "Wait 2 second between retries"

Some things perform best with a bit of randomness injected.

::

    @retry(backoff=RandBackoff(timedelta(seconds=1), timedelta(seconds=2))
    def wait_random_1_to_2_s():
        print "Randomly wait 1 to 2 seconds between retries"

Then again, it’s hard to beat exponential backoff when retrying distributed services and other remote endpoints.

::

    @retry(backoff=ExponentialBackoff(max=timedelta(seconds=10)))
    def wait_exponential_1000():
        print "Wait 2^x * 1000 milliseconds between each retry, up to 10 seconds, then 10 seconds afterwards"

We have a few options for dealing with retries that raise specific or general exceptions, as in the cases here.

::

    def retry_if_io_error(exception, ctx):
        """Return True if we should retry (in this case when it's an IOError), False otherwise"""
        return isinstance(exception, IOError)

    @retry(on_exception=retry_if_io_error)
    def might_io_error():
        print "Retry forever with no wait if an IOError occurs, raise any other errors"

::

    @retry(on_exception=retry_if_io_error, wrap_exception=True)
    def only_raise_retry_error_when_not_io_error():
        print "Retry forever with no wait if an IOError occurs, raise any other errors wrapped in RetryError"

We can also use the result of the function to alter the behavior of retrying.

::

    def retry_if_result_none(result):
        """Return True if we should retry (in this case when result is None), False otherwise"""
        return result is None

    @retry(on_result=retry_if_result_none)
    def might_return_none():
        print "Retry forever ignoring Exceptions with no wait if return value is None"

Any combination of stop, wait, etc. is also supported to give you the freedom to mix and match.


By default, max_tries and timeout raises MaxTriesError and TimeoutError. this behavior can be altered with a reraise option:

::

    @retry(reraise=True, max_tries=3)
    def is_it_good():
        raise NotYetError()

    is_it_good() # -> throws NotYetError

::

    @retry(on_result=lambda *x: True, reraise=True)
    def is_it_good():
        return 'not yet'

    is_it_good() # -> throws ValueError('not yet')


API
---

*   A Backoff can be any iterable that yields timedelta objects.
    It can be altered into context.
*   Explain context, and on_global
*   Works with asyncio too::

        @retry
        async def clumsy():
            if random.randint(0, 10) > 1:
                raise IOError("Broken sauce, everything is hosed!!!111one")
            else:
                return "Awesome sauce!"


todo
----

*   asyncio support
*   warning when passing iterators to func args
