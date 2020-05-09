import inspect
import sys
import threading
from typing import Callable, Union, TypeVar, Any, Generic, Optional, List, Iterable


class PromiseResolver:
	__slots__ = ("_promise", )

	def __init__(self, promise):
		self._promise = promise

	def resolve(self, val):
		if self._promise is None:
			return
		self._promise._resolve(val)
		self._promise = None

	def reject(self, reason):
		if self._promise is None:
			return
		self._promise._reject(reason)
		self._promise = None


T = TypeVar('T')
X = TypeVar('X')
PromiseOrT = Union['Promise[T]', T]
PromiseOrX = Union['Promise[X]', X]


class PromiseEventLoop:
	def __init__(self):
		self._scheduled = []
		self._scheduled_next = []
		self._scheduled_offthread = []
		self._cv = threading.Condition()

	def schedule_thread(self, fn: Callable[[], None]):
		"""
		Executes fn the next time event loop is processed.
		It is safe to call from different thread.
		"""
		with self._cv:
			self._scheduled_offthread.append(fn)
			self._cv.notify()

	def schedule(self, fn: Callable[[], None]):
		"""
		Executes fn the next time event loop is processed.
		"""
		self._scheduled_next.append(fn)

	def unhandled_rejection(self, promise: PromiseOrX, reason: Any) -> None:
		raise RuntimeError(f"Unhandled rejection: {reason}")

	def pull_from_offthread(self):
		with self._cv:
			self._scheduled_next.extend(self._scheduled_offthread)
			self._scheduled_offthread.clear()

	def process(self):
		self.pull_from_offthread()
		while self._scheduled_next:
			while self._scheduled_next:
				self._scheduled, self._scheduled_next = self._scheduled_next, self._scheduled
				for fn in self._scheduled:
					fn()
				self._scheduled.clear()
			self.pull_from_offthread()

	def wait(self):
		with self._cv:
			self.pull_from_offthread()
			if len(self._scheduled_next) == 0:
				def has_new_elements():
					return len(self._scheduled_offthread) > 0
				self._cv.wait_for(has_new_elements)
		self.process()


EventLoop = PromiseEventLoop()


STATE_PENDING = 0
STATE_RESOLVED = 1
STATE_REJECTED = 2


class Promise(Generic[T]):
	__slots__ = ("_listeners", "_state", "_value")

	def __init__(self, func: Callable[[Callable[[PromiseOrT], None], Callable[[Any], None]], None]):
		self._listeners = None
		self._state = STATE_PENDING
		self._value = None
		if func:
			resolver = PromiseResolver(self)

			def callable():
				try:
					func(resolver.resolve, resolver.reject)
				except:
					resolver.reject(sys.exc_info()[1])

			EventLoop.schedule(callable)

	@staticmethod
	def resolve(value: PromiseOrT) -> 'Promise[T]':
		if isinstance(value, Promise):
			return value
		return Promise(lambda res, _: res(value))

	@staticmethod
	def reject(reason: Any) -> 'Promise[Any]':
		return Promise(lambda _, rej: rej(reason))

	@staticmethod
	def all(seq: Iterable['Promise[Any]']) -> 'Promise[List[Any]]':
		promise_list = list(seq)
		if len(promise_list) == 0:
			return Promise.resolve([])

		def worker(resolve, reject):
			result = [None] * len(promise_list)
			pending = len(promise_list)
			for idx, promise in enumerate(promise_list):
				def fn(succ, val, idx=idx):
					if not succ:
						return reject(val)
					nonlocal pending
					result[idx] = val
					pending -= 1
					if pending <= 0:
						resolve(result)
				Promise.resolve(promise)._listen(fn)

		return Promise(worker)

	def then(
		self,
		on_succ: Callable[[T], PromiseOrX],
		on_fail: Optional[Callable[[Any], PromiseOrX]] = None
	) -> 'Promise[X]':
		def cont(succ, val):
			if succ:
				if on_succ is not None:
					return on_succ(val)
				else:
					return val
			else:
				if on_fail is not None:
					return on_fail(val)
				else:
					return self
		return self._chain(cont)

	def catch(self, on_fail: Callable[[Any], PromiseOrX]) -> 'Promise[X]':
		def cont(succ, val):
			if succ:
				return val
			else:
				return on_fail(val)
		return self._chain(cont)

	def _chain(self, func: Callable[[bool, Union[T, Any]], PromiseOrX]) -> 'Promise[X]':
		promise = Promise(lambda res, rej: None)

		def cont(succ, val):
			try:
				promise._resolve(func(succ, val))
			except:
				promise._reject(sys.exc_info()[1])

		self._listen(cont)
		return promise

	def _listen(self, func: Callable[[bool, Union[T, Any]], None]) -> None:
		if self._listeners is None:
			self._listeners = func
			self._fire_if_settled()
		else:
			if not isinstance(self._listeners, list):
				self._listeners = [self._listeners]
			self._listeners.append(func)
			if len(self._listeners) == 1:
				self._fire_if_settled()

	def _fire_if_settled(self):
		if self._state != STATE_PENDING:
			EventLoop.schedule(self._dispatch)

	def _dispatch(self):
		if self._listeners is None:
			if self._state == STATE_REJECTED:
				EventLoop.unhandled_rejection(self, self._value)
		else:
			to_dispatch = []
			if isinstance(self._listeners, list):
				to_dispatch.extend(self._listeners)
				self._listeners.clear()
			else:
				to_dispatch.append(self._listeners)
				self._listeners = None
			for listener in to_dispatch:
				listener(self._state == STATE_RESOLVED, self._value)

	def always(self, func: Callable[[], None]) -> 'Promise[T]':
		def cont(_, __):
			func()
			return self
		return self._chain(cont)

	def run_until_completion(self) -> T:
		while self._state == STATE_PENDING:
			EventLoop.wait()
		if self._state == STATE_RESOLVED:
			return self._value
		else:
			raise self._value

	def _resolve(self, val: PromiseOrT) -> None:
		self._fulfill(True, val)

	def _reject(self, reason: Any) -> None:
		self._fulfill(False, reason)

	def _fulfill(self, succ: bool, val: Union[T, Any]) -> None:
		if succ:
			if isinstance(val, Promise):
				val._listen(self._fulfill)
			else:
				self._settle(succ, val)
		else:
			self._settle(succ, val)

	def _settle(self, succ: bool, val: Union[T, Any]) -> None:
		if succ:
			self._state = STATE_RESOLVED
		else:
			self._state = STATE_REJECTED
		self._value = val
		if self._listeners or self._state == STATE_REJECTED:
			EventLoop.schedule(self._dispatch)


def asyncify(fn):
	def wrapper(*args, **kwargs):
		def worker(resolve, reject):
			if not inspect.isgeneratorfunction(fn):
				resolve(fn(*args, **kwargs))
			else:
				iter = fn(*args, **kwargs)

				def spin_val(success, value):
					try:
						if success:
							result = iter.send(value)
						else:
							result = iter.throw(value)
					except StopIteration as stop:
						return resolve(stop.value)
					except:
						return reject(sys.exc_info()[1])

					if isinstance(result, Promise):
						result.then(
							lambda val: spin_val(True, val),
							lambda reason: spin_val(False, reason)
						)
					else:
						Promise.resolve(result).then(lambda val: spin_val(True, val))

				spin_val(True, None)
		return Promise(worker)
	return wrapper


