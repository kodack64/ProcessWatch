from threading import Thread, Event, Lock
from subprocess import Popen, PIPE
from multiprocessing import Process, Queue
from typing import List, Union
import shlex
import time


class ProcessListener(object):
    """
    Run executable and interactively listen stdout/stderr of it.
    """

    def __init__(self, process_args: List[str]) -> None:
        """Constructor

        Args:
            process_args (List[str]): process arguments
        """
        self.process_args = process_args
        self.stdoutString, self.stderrString = "", ""
        self.lock = Lock()
        self.process = None

    def start(self) -> None:
        """Start process with listeners"""
        self.process = Popen(self.process_args, stdout=PIPE, stderr=PIPE, shell=True, text=True)
        self.threads = [Thread(target=self._listen_stdout), Thread(target=self._listen_stderr)]
        for thread in self.threads:
            thread.setDaemon(True)
            thread.start()

    def kill(self) -> None:
        """Send kill signal and wait finishing

        NOTE: Even after this commands, threads are still alive.
        """
        self.process.kill()
        self.process.wait()
        self.process = None

    def is_alive(self) -> bool:
        """Check this process is alive

        Returns:
            bool: True if alive
        """
        if self.process is None:
            return False
        return (self.process.poll() is None)

    def _listen_stdout(self) -> None:
        """Infinite loop"""
        while True:
            line = self.process.stdout.readline()
            self.lock.acquire()
            self.stdoutString += line
            self.lock.release()

    def _listen_stderr(self) -> None:
        """Infinite loop"""
        while True:
            line = self.process.stderr.readline()
            self.lock.acquire()
            self.stderrString += line
            self.lock.release()

    @classmethod
    def process_entry(cls, qstdout: Queue, qstderr: Queue, qkill: Queue, process_args: List[str], wait):
        """Launch process

        Args:
            qstdout (Queue): queue for sending stdout
            qstderr (Queue): queue for sending stderr
            qkill (Queue): qeueue for receiving kill message
            process_args (List[str]): process arguments
            wait (float): time for checking each update.
        """
        proc = ProcessListener(process_args)
        proc.start()
        for _ in range(1000):
            # lock and check buffer
            proc.lock.acquire()
            if len(proc.stdoutString) > 0:
                qstdout.put(proc.stdoutString)
                proc.stdoutString = ""
            if len(proc.stderrString) > 0:
                qstderr.put(proc.stderrString)
                proc.stderrString = ""
            proc.lock.release()

            # leave if there is kill message
            if not qkill.empty():
                break

            # leave if process was finished
            if not proc.is_alive():
                break
            time.sleep(wait)
        proc.kill()


class SafetyProcessCall(object):
    def __init__(self, process_args: Union[str, List[str]]) -> None:
        """Constructor

        Args:
            process_args (Union[str, List[str]]): list of arguments or single string
        """
        if isinstance(process_args, str):
            process_args = shlex.split(process_args)
        self.process_args = process_args
        self.proc = None

    def start(self, wait=1.0) -> None:
        """Start process

        Kill process if process is already launched

        Args:
            wait (float): time for checking each update. Default to 1.0.
        """
        if self.proc is not None:
            self.kill()
        self.qstdout = Queue()
        self.qstderr = Queue()
        self.qkill = Queue()
        self.proc = Process(target=ProcessListener.process_entry, args=(self.qstdout, self.qstderr, self.qkill, self.process_args, wait))
        self.proc.start()

    def is_alive(self) -> bool:
        """Check process is alive

        Returns:
            bool: True if alive
        """
        if self.proc is None:
            return False
        return self.proc.is_alive()

    def readlines(self) -> str:
        """Read line from stdout, return None if empty

        Returns:
            str: returned message. Return None if no message.

        Raises:
            ValueError: process is not executed
        """
        if self.proc is None:
            raise ValueError("Not started")
        if not self.qstdout.empty():
            return self.qstdout.get()
        else:
            return None

    def readlines_stderr(self) -> str:
        """Read line from stderr, return None if empty

        Returns:
            str: returned message. Return None if no message.

        Raises:
            ValueError: process is not executed
        """
        if self.proc is None:
            raise ValueError("Not started")
        if not self.qstderr.empty():
            return self.qstderr.get()
        else:
            return None

    def kill(self):
        """ Kill process and join

        Raises:
            ValueError: process is not executed
        """
        if self.proc is None:
            raise ValueError("Not started")
        self.qkill.put("kill")
        self.proc.join()
        self.proc.close()
        time.sleep(0.1)
        self.qstdout.close()
        self.qstderr.close()
        self.qkill.close()
        self.proc = None


if __name__ == '__main__':
    proc = SafetyProcessCall("python -c 'import numpy as np; arr = np.array([0,1,2]); print(arr)'")
    proc.start()
    for _ in range(5):
        print("stdout:", proc.readlines())
        print("stderr:", proc.readlines_stderr())
        print("alive:", proc.is_alive())
        time.sleep(1.)
    print("kill")
    proc.kill()
    print("restart")
    proc.start()
    for _ in range(5):
        print("stdout:", proc.readlines())
        print("stderr:", proc.readlines_stderr())
        print("alive:", proc.is_alive())
        time.sleep(1.)
    print("kill")
    proc.kill()
    print("finish")
