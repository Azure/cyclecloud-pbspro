# -*- coding: utf-8 -*-
# Copyright (c) 2017, Bryan W. Berry <bryan.berry@gmail.com>
# License: BSD New, see LICENSE for details.

import sys
import os
import time
from abc import ABCMeta, abstractmethod
from functools import wraps, total_ordering

# Is this Python 3?
PY3 = sys.version_info > (3, 0)


class Null(object):
    """Null represents nothing."""
    # pylint: disable = too-few-public-methods
    def __repr__(self):
        return 'Null'

    def __call__(self):
        return self


# pylint: disable = invalid-name
#: The Null object.
Null = Null()


class Unit(object):
    """Descriptor that always return the owner monad, used for ``unit``."""
    # pylint: disable = too-few-public-methods
    def __get__(self, instance, cls):
        """Returns the owner monad."""
        return cls


@total_ordering
class Ord(object):
    """Mixin class that implements rich comparison ordering methods."""
    # pylint: disable = too-few-public-methods
    def __eq__(self, other):
        if self is other:
            return True
        elif not isinstance(other, type(self)):
            return NotImplemented
        else:
            return self._value == other._value

    def __lt__(self, other):
        if self is other:
            return False
        elif isinstance(other, type(self)):
            return self._value < other._value
        else:
            fmt = "unorderable types: {} and {}'".format
            raise TypeError(fmt(type(self), type(other)))


class Monad(object):
    """The Monad Class.

    This is just a base class
    """
    __metaclass__ = ABCMeta
    
    def __init__(self, value):
        self._value = value

    def __repr__(self):
        return '{cls}({value})'.format(
            cls=type(self).__name__, value=repr(self._value))

    @abstractmethod
    def map(self, function):
        """The map operation.

        ``function`` is a function that maps from the underlying value to a
        monadic type, something like signature ``f :: a -> M a`` in haskell's
        term.
        """
        return NotImplemented

    #: The ``unit`` of monad.
    unit = Unit()


class NoSuchElementError(Exception):
    pass


class FailureError(Exception):
    pass


class InvalidTryError(Exception):
    pass


class Try(Monad, Ord):
    """A wrapper for operations that may fail

    Represents values/computations with two possibilities.

    :param value: value to contain
    :param message: (optional) message to output to console if to_console is called.
                   If None, a string representation of the contained value is output.
                   Defaults to ``None``
    :param start: (optional) start time for the operation, in seconds since the UNIX epoch
                  `time.time()` is typically used for this value. Defaults to ``None``.
    :type start: int
    :param end: (optional) end time for the operation, in seconds since the UNIX epoch
                  ``time.time()`` is typically used for this value. Defaults to ``None``.
    :type end: int
    :param count: (optional) number of times the operation has been executed. Defaults to ``1``
    :type end: int

    Usage::

      >>> Success(42)
      Success(42)
      >>> Success([1, 2, 3])
      Success([1, 2, 3])
      >>> Failure('Error')
      Failure('Error')
      >>> Success(Failure('Error'))
      Success(Failure('Error'))
      >>> isinstance(Success(1), Try)
      True
      >>> isinstance(Failure(None), Try)
      True
      >>> saving = 100
      >>> insolvent = Failure('I am insolvent')
      >>> spend = lambda cost: insolvent if cost > saving else Success(saving - cost)
      >>> spend(90)
      Success(10)
      >>> spend(120)
      Failure('I am insolvent')

    Map operation with ``map``, applies function to value only if it is a Success and returns a Success

    >>> inc = lambda n: n + 1
    >>> Success(0)
    Success(0)
    >>> Success(0).map(inc)
    Success(1)
    >>> Success(0).map(inc).map(inc)
    Success(2)
    >>> Failure(0).map(inc)
    Failure(0)

    Comparison with ``==``, as long as they are the same type and what's
    wrapped inside are comparable.

    >>> Failure(42) == Failure(42)
    True
    >>> Success(42) == Success(42)
    True
    >>> Failure(42) == Success(42)
    False

    A :py:class:`Failure` is less than a :py:class:`Success`, or compare the two by
    the values inside if thay are of the same type.

    >>> Failure(42) < Success(42)
    True
    >>> Success(0) > Failure(100)
    True
    >>> Failure('Error message') > Success(42)
    False
    >>> Failure(100) > Failure(42)
    True
    >>> Success(-2) < Success(-1)
    True
    """
    def __init__(self, value, message=None, start=None, end=None, count=1):
        super(Try, self).__init__(value)
        self._message = message
        self._start = start
        self._end = end
        self._count = count
        if (start is None and end is not None) or (end is None and start is not None):
            raise InvalidTryError(
                "The start and end argument must either be both None or not None")
        
        if type(self) is Try:
            raise NotImplementedError('Please use Failure or Success instead')

    def map(self, function):
        """The map operation of :py:class:`Try` to Success instances

        Applies function to the value if and only if this is a
        :py:class:`Success`.
        """
        constructor = type(self)
        if self.succeeded():
            return constructor(function(self._value))
        else:
            return self

    def map_failure(self, function):
        """The map operation of :py:class:`Try` to Failure instances

        Applies function to the value if and only if this is a
        :py:class:`Success`.
        """
        constructor = type(self)
        if self.failed():
            return constructor(function(self._value))
        else:
            return self

    def get(self):
        '''Gets the Success value if this is a Success otherwise throws an exception'''
        if self.succeeded():
            return self._value
        else:
            raise NoSuchElementError('You cannot call `get` on a Failure, use `get_failure` instead')

    def get_failure(self):
        '''Gets the Failure value if this is a Failure otherwise throws an exception'''
        if self.failed():
            return self._value
        else:
            raise NoSuchElementError('You cannot call `get_failure` on a Success, use `get` instead')

    def get_or_else(self, default):
        '''Returns the value from this Success or the given default argument if this is a Failure.'''
        if self.succeeded():
            return self._value
        else:
            return default

    def succeeded(self):
        """Return a Boolean that indicates if the value is an instance of Success

        >>> Success(True).succeeded()
        True
        >>> Failure('fubar').succeeded()
        False
        """
        return bool(self)

    def failed(self):
        """Return a Boolean that indicates if the value is an instance of Failure

        >>> Failure('shit is fucked up').failed()
        True
        >>> Success('it worked!').failed()
        False
        """
        return not(bool(self))

    @property
    def message(self):
        '''
        Return the message for the Try. If the ``message`` argument was provided to the constructor
        that value is returned. Otherwise the string representation of the contained value is returened
        '''
        if self._message is not None:
            return self._message
        else:
            return str(self._value)

    @property
    def start(self):
        '''
        Start time of the operation in seconds since the UNIX epoch if specified in
        the constructor or with the ``update`` method, ``None`` otherwise
        '''
        return self._start

    @property
    def end(self):
        '''
        End time of the operation in seconds since the UNIX epoch if specified in
        the constructor or with the ``update`` method, ``None`` otherwise
        '''
        return self._end

    @property
    def elapsed(self):
        '''
        End time of the operation in seconds since the UNIX epoch if the start and end arguments
        were specified in the constructor or with the ``update`` method, ``None`` otherwise
        '''
        if self._end is None and self._start is None:
            return None
        
        return self.end - self.start

    @property
    def count(self):
        '''Number of times the operation has been tried'''
        return self._count

    def update(self, message=None, start=None, end=None, count=1):
        '''
        Update the Try with new properties but the same value. Returns a new :class:`Failure`
        or :py:class:`Success` and does not actually update in place.

        :param message: (optional) message to output to console if to_console is called.
                   If None, a string representation of the contained value is output.
                   Defaults to ``None``
        :param start: (optional) start time for the operation, in seconds since the UNIX epoch
                  `time.time()` is typically used for this value. Defaults to ``None``.
        :type start: int
        :param end: (optional) end time for the operation, in seconds since the UNIX epoch
                  ``time.time()`` is typically used for this value. Defaults to ``None``.
        :type end: int
        :param count: (optional) number of times the operation has been executed. Defaults to ``1``
        :type end: int
        '''
        if (start is None and end is not None) or (end is None and start is not None):
            raise InvalidTryError(
                "The start and end argument must either be both None or not None")
        
        message = message or self._message

        # start = start or self._start does not work because start may == 0 and is therefore falsey
        if start is None:
            start = self._start
        if end is None:
            end = self._end
        if count is None:
            count = self._count

        constructor = type(self)
        return constructor(self._value, message=message, start=start, end=end, count=count)

    def to_console(self, nl=True, exit_err=False, exit_status=1):
        '''
        Write a message to the console. By convention, Success messages are written to stdout
        and Failure messages are written to stderr. The Failure's `cause` is written to stderr
        while the string repesentation of the Success's _value is written.

        :param message: the message to print
        :param err: (optional) if set to true the file defaults to ``stderr`` instead of ``stdout``.
        :param nl: (optional) if set to `True` (the default) a newline is printed afterwards.
        :param exit_err: (optional) if set to True, exit the running program with a non-zero exit code
        :param exit_status: (optional) the numeric exist status to return if exit is True
        '''
        if self.succeeded():
            to_console(self.message, nl=nl)
        else:
            to_console(self.message, nl=nl, err=True, exit_err=exit_err, exit_status=exit_status)

    def fail_for_error(self, exit_status=1):
        '''
        If a Failure, write the message to stderr and exit with return code of `exit_status`
        Does nothing if a Success

        :param exit_status: (optional) the numeric exist status to return if exit is True
        :type exit_status: int
        '''
        if self.failed():
            to_console(self.message, nl=True, err=True, exit_err=True,
                       exit_status=exit_status)

    def raise_for_error(self, exception=FailureError):
        '''
        Raise an exception if self is an instance of Failure. If the wrapped value is an 
        instance of Exeception or one of its subclasses, it is raised directly. The the
        optional argument ``exception`` is specified, that type is raised with the wrapped
        value as its argument. Otherwise, FailureError is raised. This method has no effect 
        is self is an instance of Success.

        :param exception: (optional) type of Exception to raise
        '''
        
        if self.succeeded():
            return

        wrapped_value = self.get_failure()
        if isinstance(wrapped_value, Exception):
            raise wrapped_value
        else:
            raise exception(wrapped_value)

    def filter(self, predicate):
        '''
        If a Success, convert this to a Failure if the predicate is not satisfied.
        Applies predicate to the wrapped value

        :param predicate: a function that takes the wrapped value as its argument and returns a boolean value
        :rtype: :class:`Try <Try>` object
        :return: Try
        '''
        if self.failed():
            return self
        else:
            wrapped_value = self.get()
            if predicate(wrapped_value):
                return self
            else:
                return Failure(wrapped_value)
                
    def __lt__(self, monad):
        """Override to handle special case: Success."""
        if not isinstance(monad, (Failure, Success)):
            fmt = "unorderable types: {} and {}'".format
            raise TypeError(fmt(type(self), type(monad)))
        if type(self) is type(monad):
            # same type, either both lefts or rights, compare against value
            return self._value < monad._value
        if monad:
            # self is Failure and monad is Success, left is less than right
            return True
        else:
            return False

    def __repr__(self):
        """Customize Show."""
        fmt = 'Success({})' if self else 'Failure({})'
        return fmt.format(repr(self._value))


class Failure(Try):
    """Failure of :py:class:`Try`."""
    def __bool__(self):
        # pylint: disable = no-self-use
        return False
    __nonzero__ = __bool__


class Success(Try):
    """Success of :py:class:`Try`."""
    def __bool__(self):
        # pylint: disable = no-self-use
        return True


class Maybe(Monad, Ord):
    """A wrapper for values that be None

    >>> Some(42)
    Some(42)
    >>> Some([1, 2, 3])
    Some([1, 2, 3])
    >>> Some(Nothing)
    Some(Nothing)
    >>> Some(Some(2))
    Some(Some(2))
    >>> isinstance(Some(1), Maybe)
    True
    >>> isinstance(Nothing, Maybe)
    True
    >>> saving = 100
    >>> spend = lambda cost: Nothing if cost > saving else Some(saving - cost)
    >>> spend(90)
    Some(10)
    >>> spend(120)
    Nothing
    >>> safe_div = lambda a, b: Nothing if b == 0 else Some(a / b)
    >>> safe_div(12.0, 6)
    Some(2.0)
    >>> safe_div(12.0, 0)
    Nothing

    Map operation with ``map``. Not that map only applies a function if the object is an
    instance of Some. In the case of a Some, ``map`` returns the transformed value inside a Some. 
    No action is taken for a Nothing.

    >>> inc = lambda n: n + 1
    >>> Some(0)
    Some(0)
    >>> Some(0).map(inc)
    Some(1)
    >>> Some(0).map(inc).map(inc)
    Some(2)
    >>> Nothing.map(inc)
    Nothing

    Comparison with ``==``, as long as what's wrapped inside are comparable.

    >>> Some(42) == Some(42)
    True
    >>> Some(42) == Nothing
    False
    >>> Nothing == Nothing
    True
    """
    @classmethod
    def from_value(cls, value):
        """Wraps ``value`` in a :class:`Maybe` monad.

        Returns a :class:`Some` if the value is evaluated as true.
        :data:`Nothing` otherwise.
        """
        return cls.unit(value) if value else Nothing

    def get(self):
        '''Return the wrapped value if this is Some otherwise throws an exception'''
        if self.is_empty():
            raise NoSuchElementError('You cannot call `get` on Nothing')
        else:
            return self._value

    def get_or_else(self, default):
        '''Returns the value from this Some or the given default argument otherwise.'''
        if self.is_empty():
            return default
        else:
            return self._value

    def filter(self, predicate):
        '''
        Returns Some(value) if this is a Some and the value satisfies the given predicate.

        :param predicate: a function that takes the wrapped value as its argument and returns a boolean value
        :rtype: :class:`Maybe <Maybe>` object
        :return: Maybe
        '''
        if self.is_empty():
            return self
        else:
            wrapped_value = self.get()
            if predicate(wrapped_value):
                return self
            else:
                return Nothing

    def map(self, function):
        """The map operation of :class:`Maybe`.

        Applies function to the value if and only if this is a :class:`Some`.
        """
        constructor = type(self)
        return self and constructor(function(self._value))

    def is_empty(self):
        '''Returns true, if this is None, otherwise false, if this is Some.'''
        return self is Nothing

    def is_defined(self):
        '''Returns true, if this is Some, otherwise false, if this is Nothing.'''
        return self is not Nothing
    
    def __bool__(self):
        return self is not Nothing

    __nonzero__ = __bool__

    def __repr__(self):
        """Customized Show."""
        if self is Nothing:
            return 'Nothing'
        else:
            return 'Some({})'.format(repr(self._value))

    def __iter__(self):
        if self is not Nothing:
            yield self._value


# pylint: disable = invalid-name
Some = Maybe
#: The :class:`Maybe` that represents nothing, a singleton, like ``None``.
Nothing = Maybe(Null)
Maybe.zero = Nothing
# pylint: enable = invalid-name


def _get_stacktrace():
    import traceback
    if PY3:
        from io import StringIO
    else:
        from StringIO import StringIO

    t, _, tb = sys.exc_info()
    f = StringIO()
    traceback.print_tb(tb, None, f)
    stacktrace = f.getvalue()
    return stacktrace


def try_out(callable, exception=None):
    '''
    Executes a callable and wraps a raised exception in a Failure class. If an exception was
    not raised, a Success is returned. If the keyword argument ``exception`` is not None,
    only wrap the specified exception. Raise all other exceptions.
    The stacktrace related to the exception is added to the wrapped exception
    as the `stracktrace` property


    :param callable: A callable reference, should return a value other than None
    :rtype Try: a Success or Failure
    '''

    if exception is None:
        catch_exception = Exception
    else:
        catch_exception = exception

    try:
        return Success(callable())
    except catch_exception as e:
        stacktrace = _get_stacktrace()
        e.stacktrace = stacktrace
        return Failure(e)
    

def to_console(message=None, nl=True, err=False, exit_err=False, exit_status=1):
    '''
    Write a message to the console

    :param message: the message to print
    :param err: (optional) if set to true the file defaults to ``stderr`` instead of ``stdout``.
    :param nl: (optional) if set to `True` (the default) a newline is printed afterwards.
    :param exit_err: (optional) if set to True, exit the running program with a non-zero exit code
    :param exit_status: (optional) the numeric exist status to return if exit is True
    '''
    if err:
        stream = sys.stderr
    else:
        stream = sys.stdout
        
    stream.write(message)

    if nl:
        stream.write(os.linesep)

    stream.flush()
    if exit_err:
        sys.exit(exit_status)


class SystemClock:
    '''
    This is just a wrapper around the built-in time.time that makes it much easier to test 
    this module by mocking out time itself.
    '''
    def __init__(self):
        pass

    def time(self):
        '''Returns value of current UNIX epoch in seconds'''
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)


class StoppedClock:
    '''
    This class only exists to make it easier to test retries
    '''
    def __init__(self):
        self.times = []

    def set_times(self, times):
        '''list of times for the self.time call to return
        the times can be a single value or be a value + side effect to trigger

        example:
           clock.set_times([100, 200, (300, lambda: Failure("Uh oh!"), 400])

        the 3rd invocation of clock.time() will return the Failure

        example:
           clock.set_times([100, 200, (300, function_with_side_effect), 400])
           
        function_with_side_effect will be triggered the 3rd time clock.time() is invoked
        '''
        self.times = times
        self.current = iter(times)

    def sleep(self, seconds):
        '''This sleep doesn't actually sleep, so your tests run quickly!'''
        pass

    def time(self):
        current_time = next(self.current)
        if not isinstance(current_time, tuple):
            return current_time

        current_time_val, side_effect = current_time
        if isinstance(side_effect, Exception):
            raise side_effect

        side_effect()

        return current_time_val


class Counter:
    '''A simple counter'''

    def __init__(self, initial=0):
        self._count = initial

    def increment(self):
        self._count = self._count + 1

    def reset(self):
        self._count = 0
        
    @property
    def count(self):
        return self._count


def tick_counter(column_limit=80):

    counter = Counter()
    
    def write_tick(log):
        sys.stdout.write('.')
        counter.increment()
        # if we have reached the max # of columns, write a newline and reset the counter
        if counter.count == column_limit:
            sys.stdout.write(os.linesep)
            counter.reset()
        sys.stdout.flush()
        
    return write_tick
    

_clock = SystemClock()


class Again(Failure):
    """
    Again of :py:class:`Failure`.
    A handy alias of :py:class:`Failure` to indicate that an operation should be retried
    """
    pass


class Stop(Success):
    """
    Stop of :py:class:`Success`.
    A handy alias of :py:class:`Success` to indicate that an operation should **not** be retried
    """
    pass


class InvalidCallableError(Exception):
    pass


def raise_if_invalid_result(result):
    '''Raise InvalidCallableError if the result is not of type Try'''
    if not isinstance(result, Try):
        raise InvalidCallableError(
            "Functions passed as arguments to the retry function must "
            "return either tryme.Success, tryme.Failure, or raise an exception")


def retry_wrapper(acallable, timeout=300, delay=5, status_callback=None):

    @wraps(acallable)
    def _retry(*args, **kwargs):
        start = _clock.time()
        assert timeout > 0, 'the timeout keyword argument must be greater than 0'
        deadline = start + timeout
        counter = Counter(0)
        current_time = start

        while current_time < deadline:
            counter.increment()
            result = acallable(*args, **kwargs)
            current_time = _clock.time()
            end = current_time
            raise_if_invalid_result(result)

            # update with time accounting
            result = result.update(start=start, end=end, count=counter.count)
            if result.succeeded():
                if status_callback:
                    status_callback(result)
                return result
            else:
                if status_callback:
                    status_callback(result)
                _clock.sleep(delay)

        return result.update(start=start, end=end, count=counter.count)
    
    return _retry


def retry(*args, **kwargs):
    '''
    Function that wraps a callable with a retry loop. The callable should only return
    :class:Failure, :class:Success, or raise an exception. This function can
    be used as a decorator or directly wrap a function. This method returns a 
    a result object which is an instance of py:class:`Success` or py:class:`Failure`.
    This function updates the result with the time of the first attempt, the time
    of the last attempt, and the total count of attempts

    :param acallable: object that can be called
    :type acallable: function
    :param timeout: (optional) maximum period, in seconds, to wait until an individual try succeeds.
                    Defaults to ``300`` seconds
    :type timeout: int
    :param delay: (optional) delay between retries in seconds. Defaults to ``5`` seconds.
    :type delay: int
    :param status_callback: (optional) callback to invoke after each retry, is passed the result
                            as an argument. Defaults to ``None``.
    :type status_callback: function

    Usage::
      >>> deadline = time.time() + 300
      >>> dinner_iterator = iter([False, False, True])
      >>> def dinner_is_ready():
      ...     return next(dinner_iterator)
      >>> breakfast_iterator = iter([False, False, True])
      >>> def breakfast_is_ready():
      ...     return next(breakfast_iterator)
      >>> @retry
      ... def wait_for_dinner():
      ...     if dinner_is_ready():
      ...         return Success("Ready!")
      ...     else:
      ...         return Failure("not ready yet")
      >>> result = wait_for_dinner()  # doctest: +SKIP
      >>> result  # doctest: +SKIP
      Success("Ready!")
      >>> result.elapsed  # doctest: +SKIP
      8
      >>> result.count  # doctest: +SKIP
      3
      >>> @retry
      ... def wait_for_breakfast():
      ...     if breakfast_is_ready():
      ...         return Success("Ready!")
      ...     else:
      ...         return Failure("not ready yet")
      >>> result = wait_for_breakfast() # doctest: +SKIP
      Success("Ready!")
      >>> result.elapsed   # doctest: +SKIP
      8
      >>> result.count # doctest: +SKIP
      3

    The names py:class:`Success` and py:class:`Failure` do not always
    map well to operations that need to be retried. The subclasses
    py:class:`Stop` and py:class:`Again` can be more intuitive.::
      >>> breakfast_iterator = iter([False, False, True])
      >>> def breakfast_is_ready():
      ...     return next(breakfast_iterator)
      >>> @retry
      ... def wait_for_breakfast():
      ...     if breakfast_is_ready():
      ...         return Stop("Ready!")
      ...     else:
      ...         return Again("not ready yet")

    '''

    # if used as a decorator without arguments `@retry`, the first argument is
    # is the decorated function
    # If used as a decorator with keyword arguments, say `@retry(timeout=900)`
    # the args are empty and the decorated function is supplied sometime later
    # as the argument to the decorator. Confusing!
    acallable = None
    if len(args) > 0:
        acallable = args[0]

    if acallable is not None:
        return retry_wrapper(acallable, **kwargs)
    else:
        def decorator(func):
            return retry_wrapper(func, **kwargs)

        return decorator
