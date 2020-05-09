import os
import re
import subprocess
import sys
import threading
import time
from typing import List, IO, Callable, TypeVar, Union

from deckbuilder.promise import Promise, EventLoop

runner_index = 0

MaxLineLength = 256

T = TypeVar("T")
NormalizeNewlines = re.compile("\r\n|\r|\n")
MutexStdout = threading.Lock()
MutexStderr = threading.Lock()


class OutputBuffer:
	def __init__(self):
		self.chunks: List[str] = []
		self.total_len: int = 0

	def append(self, s: str):
		if len(self.chunks) == 0 or len(s) > 0:
			self.chunks.append(s)
			self.total_len += len(s)

	def has_any(self) -> bool:
		return len(self.chunks) > 0

	def compose(self) -> str:
		ret = ''.join(self.chunks)
		self.chunks.clear()
		self.total_len = 0
		return ret

	def process(self, data: Union[bytes, str]):
		if isinstance(data, bytes):
			data = data.decode(encoding="utf-8", errors='backslashreplace')
		data_len = len(data)
		i = 0
		while i != data_len:
			next_newline = NormalizeNewlines.search(data, i)
			if not next_newline:
				while i != data_len:
					remaining_length = min(MaxLineLength - self.total_len, data_len - i)
					self.append(data[i: i + remaining_length])
					i += remaining_length
					if self.total_len >= MaxLineLength:
						yield self.compose()
			else:
				next_newline_pos = next_newline.start()
				while True:
					remaining_length = min(MaxLineLength - self.total_len, data_len - i)
					if i + remaining_length >= next_newline_pos:
						self.append(data[i: next_newline_pos])
						yield self.compose()
						i = next_newline.end()
						break
					else:
						self.append(data[i: i + remaining_length])
						i += remaining_length
						if self.total_len >= MaxLineLength:
							yield self.compose()


class TaskProcess:
	def __init__(self, description: str, runner_idx: int):
		self.description = description
		self.runner_idx = runner_idx
		self.time_start = None
		self.time_end = None
		self.stdout = OutputBuffer()
		self.stderr = OutputBuffer()

	def start(self):
		self.time_start = time.time()
		with MutexStdout:
			print(f"[{self.runner_idx}]+ {self.description}")

	def end(self):
		self.flush()
		self.time_end = time.time()
		with MutexStderr:
			print(f"[{self.runner_idx}]- Completed in {self.time_end - self.time_start} s")

	def write_stdout(self, data: Union[bytes, str]) -> None:
		for line in self.stdout.process(data):
			self._out(sys.stdout, line)

	def write_stderr(self, data: Union[bytes, str]) -> None:
		for line in self.stderr.process(data):
			self._out(sys.stderr, line)

	def flush(self):
		if self.stdout.has_any():
			with MutexStdout:
				self._out(sys.stdout, self.stdout.compose())
		if self.stderr.has_any():
			with MutexStderr:
				self._out(sys.stderr, self.stderr.compose())

	def _out(self, stream: IO[str], line: str) -> None:
		print(f"[{self.runner_idx}] ", end="", file=stream)
		print(line, file=stream)


def run_async_command(description: str, command: List[str], suppress_stderr=False) -> Promise[int]:
	def worker(task_process: TaskProcess) -> int:
		stderr_target = subprocess.PIPE
		process = subprocess.Popen(executable=command[0], args=command, stdout=subprocess.PIPE, stderr=stderr_target)
		stdout = process.stdout
		stderr = process.stderr
		def start_line_reader(stream: IO[bytes], writer: Callable[[Union[bytes, str]], None]):
			def line_reader_worker():
				while not stream.closed:
					bytes = stream.read()
					if len(bytes) == 0:
						break
					writer(bytes)
			thread = threading.Thread(target=line_reader_worker)
			thread.start()
			return thread
		stdout_reader = start_line_reader(stdout, task_process.write_stdout)
		if not suppress_stderr:
			stderr_reader = start_line_reader(stderr, task_process.write_stderr)
		else:
			stderr.close()
		process.wait()
		stdout_reader.join()
		if not suppress_stderr:
			stderr_reader.join()
		if process.returncode != 0:
			raise RuntimeError(f"exit code {process.returncode}")
		return 0
	return run_threaded(description, worker)


def run_threaded(description: str, callee: Callable[[TaskProcess], T]) -> Promise[T]:
	global runner_index
	runner_index += 1
	task_process = TaskProcess(description, runner_index)
	def fn(resolve, reject):
		def worker():
			try:
				task_process.start()
				result = callee(task_process)
				task_process.end()
				EventLoop.schedule_thread(lambda: resolve(result))
			except:
				exc = sys.exc_info()[1]
				EventLoop.schedule_thread(lambda: reject(exc))
				return
		thread = threading.Thread(target=worker)
		thread.start()
	return Promise(fn)


