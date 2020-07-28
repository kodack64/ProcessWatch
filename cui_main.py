
import sys
import curses
import time
import shlex
import traceback
from process_attach import SafetyProcessCall


class Process(object):
    def __init__(self, name, commands, delay):
        self.name = name
        self.commands = commands
        self.delay = delay
        self.result = []
        self.status = "Stop"
        self.proc = None

    def start(self):
        if self.proc is not None:
            self.kill()
        self.proc = SafetyProcessCall(self.commands)
        self.proc.start()
        self.status = "Run"
        time.sleep(float(self.delay))

    def refresh_status(self):
        if self.proc is None:
            self.status = "Stop"
        else:
            self.status = "Run" if self.proc.is_alive() else "Stop"

        mes = self.proc.readlines()
        if mes is not None:
            self.result += mes.strip().split("\n")
        mes = self.proc.readlines_stderr()
        if mes is not None:
            self.result += mes.strip().split("\n")

    def kill(self):
        self.proc.kill()
        self.proc = None
        self.status = "Stop"


class ProcessTable():
    def __init__(self):
        self.process_list = []

    def add(self, name, commands, delay=0.):
        proc = Process(name, commands, delay)
        proc.start()
        self.process_list.append(proc)

    def refresh(self, index):
        self.process_list[index].refresh_status()

    def restart(self, index):
        self.process_list[index].start()

    def restart_all(self):
        for proc in self.process_list:
            proc.start()

    def kill(self, index):
        self.process_list[index].kill()

    def kill_all(self):
        for proc in self.process_list:
            proc.kill()

    def delete(self, index):
        self.process_list[index].kill()
        self.process_list.pop(index)

    def delete_all(self):
        self.kill_all()
        self.process_list = []

    def get_count(self):
        return len(self.process_list)

    def get_status(self, idx):
        proc = self.process_list[idx]
        return f"id: {idx:5} | status: {proc.status:6} | com: {str(proc.name)[:20]:20} | res: {'' if len(proc.result)==0 else proc.result[-1]}"

    def save_config(self, fname):
        s = ""
        for proc in self.process_list:
            s += f"{proc.name}:::{proc.commands}:::{str(proc.delay)}\n"
        fout = open(fname, "w")
        fout.write(s)
        fout.close()

    def load_config(self, fname):
        fin = open(fname, "r")
        config = fin.read()
        self.delete_all()
        for line in config.strip().split("\n"):
            name, commands, delay = line.split(":::")
            self.add(name, commands, delay)


class Application():
    def __init__(self, stdscr):
        self.scr = stdscr
        self.command = ""
        self.last_command = ""
        self.last_message = ""
        self.position = 0
        self.finish = False
        self.offset = 2
        self.scr.timeout(1000)
        self.debug_str = ""
        self.process_table = ProcessTable()
        self.refresh_all()
        if len(sys.argv) == 2:
            fname = sys.argv[1]
            self.process_table.load_config(fname)
        else:
            self.process_table.add("sample sleep", "python sleep.py")
            self.process_table.add("sample numpy", "python -c 'import numpy as np; np.array([0,1,2,]); print(arr)'")
            self.process_table.add("sample loop", 'python -c "import time; [(print(ind, flush=True),time.sleep(1)) for ind in range(1000)]"')
        self.refresh_all()

    def getch(self):
        try:
            ch = self.scr.getkey()
        except curses.error:  # timeout
            return -1

        self.debug_str = (str(ch).replace("\n", "\\n") + " " + str(list(map(ord, ch)))).replace("\0", "\\0")
        self.refresh_debug_line()

        if len(ch) != 1:
            if ch == "KEY_LEFT":
                self.command_cursor_left_move()
            elif ch == "KEY_RIGHT":
                self.command_cursor_right_move()
            elif ch == "KEY_UP":
                self.command_load_last()
            elif ch == "KEY_RESIZE":
                self.refresh_window()
            elif ch == "KEY_HOME":
                self.command_move_cursor(0)
            elif ch == "KEY_END":
                self.command_move_cursor(len(self.command))
            elif ch == "KEY_DC":
                self.command_delete()
            ch = 0
        else:
            ch = ord(ch)
            if ch == 3:  # Ctrl+C
                raise KeyboardInterrupt
            elif ch == 26:  # EOF
                raise EOFError
            elif ch == 27:  # Escape
                self.finish = True
            elif ch == 10:  # Enter
                self.process_command()
            elif ch == 8:  # Backspace
                self.command_backspace()

        if ch < 32 or ch >= 127:  # Not character
            ch = 0

        return ch

    def mainloop(self):
        try:
            while not self.finish:
                ch = self.getch()
                if ch == 0:
                    continue
                elif ch == -1:
                    self.refresh_process_list()
                else:
                    self.update_command(ch)
        except Exception as e:
            self.process_table.kill_all()
            raise e
        self.process_table.kill_all()

    def process_command(self):
        command_list = self.command.strip().split()
        self.last_command = self.command.strip()
        try:
            if len(command_list) == 0:
                pass
            elif command_list[0] in ["exit", "quit", "bye"]:
                self.finish = True
                self.last_message = f"Exit"
            elif command_list[0] in ["restart", "start"]:
                if command_list[1] == "all":
                    self.process_table.restart_all()
                    self.last_message = f"Restart all processes"
                else:
                    val = int(command_list[1])
                    self.process_table.restart(val)
                    self.last_message = f"Restart {val}-th process"
            elif command_list[0] in ["stop", "kill"]:
                if command_list[1] == "all":
                    self.process_table.kill_all()
                    self.last_message = f"Kill all processes"
                else:
                    val = int(command_list[1])
                    self.process_table.kill(val)
                    self.last_message = f"Kill {val}-th process"
            elif command_list[0] in ["delete", "remove"]:
                self.clear_process_list()
                if command_list[1] == "all":
                    self.process_table.delete_all()
                    self.last_message = f"Delete all processes"
                else:
                    val = int(command_list[1])
                    self.process_table.delete(val)
                    self.last_message = f"Delete {val}-th process"
            elif command_list[0] in ["add", "append"]:
                if len(command_list) < 2:
                    raise ValueError("The format of add is 'add <name> <args>'")
                name = command_list[1]
                args = command_list[2:]
                self.process_table.add(name, args)
                self.last_message = f"add {str(args)} as name '{name}'"
            elif command_list[0] in ["save"]:
                fname = command_list[1]
                self.process_table.save_config(fname)
                self.last_message = f"save config to {fname}"
            elif command_list[0] in ["load"]:
                fname = command_list[1]
                self.process_table.load_config(fname)
                self.clear_process_list()
                self.last_message = f"load config from {fname}"
            elif command_list[0] in ["h", "help"]:
                self.show_description()
            else:
                self.last_message = "No command matched"
        except Exception as e:
            self.last_message = str(e)

        self.refresh_last_command()
        self.refresh_last_message()
        self.command = ""
        self.position = 0
        self.refresh_command_line()

    def update_command(self, ch):
        s = str(chr(ch))
        self.command = self.command[:self.position] + s + self.command[self.position:]
        self.position += len(s)
        self.refresh_command_line()

    def command_cursor_left_move(self):
        self.position = max(self.position - 1, 0)
        self.refresh_command_cursor()

    def command_cursor_right_move(self):
        self.position = min(self.position + 1, len(self.command))
        self.refresh_command_cursor()

    def command_backspace(self):
        if self.position == 0:
            return
        self.command = self.command[:self.position - 1] + self.command[self.position:]
        self.command_cursor_left_move()
        self.refresh_command_line()

    def command_delete(self):
        if self.position == len(self.command):
            return
        self.command = self.command[:self.position] + self.command[self.position + 1:]
        self.refresh_command_line()

    def command_move_cursor(self, index):
        self.position = index
        self.refresh_command_line()

    def command_load_last(self):
        self.command = self.last_command
        self.position = len(self.command)
        self.refresh_command_line()

    def refresh_all(self):
        self.scr.clear()
        self.refresh_command_line()
        self.refresh_last_command()
        self.refresh_last_message()
        self.refresh_debug_line()
        self.refresh_process_list()
        self.show_description()

    def refresh_window(self):
        y, x = self.scr.getmaxyx()
        self.scr.clear()
        curses.resize_term(y, x)
        self.scr.refresh()
        self.refresh_all()

    def refresh_command_line(self):
        self.scr.move(0, 0)
        self.scr.clrtoeol()
        self.scr.addstr(0, 0, f"> {self.command}")
        self.refresh_command_cursor()

    def refresh_command_cursor(self):
        self.scr.move(0, self.position + self.offset)

    def refresh_last_command(self):
        y, x = self.scr.getyx()
        self.scr.move(2, 0)
        self.scr.clrtoeol()
        self.scr.addstr(2, 0, f"LAST: {self.last_command}")
        self.scr.move(y, x)

    def refresh_last_message(self):
        y, x = self.scr.getyx()
        self.scr.move(3, 0)
        self.scr.clrtoeol()
        self.scr.addstr(3, 0, f"MESSAGE: {self.last_message}")
        self.scr.move(y, x)

    def refresh_debug_line(self):
        y, x = self.scr.getyx()
        self.scr.move(4, 0)
        self.scr.clrtoeol()
        self.scr.addstr(4, 0, f"INPUT: {self.debug_str}")
        self.scr.move(y, x)

    def refresh_process_list(self):
        y, x = self.scr.getyx()
        offset = 5
        self.scr.addstr(offset, 0, "-" * 40)
        offset += 1
        for idx in range(self.process_table.get_count()):
            self.process_table.refresh(idx)
            message = self.process_table.get_status(idx)
            self.scr.move(idx + offset, 0)
            self.scr.clrtoeol()
            self.scr.addstr(idx + offset, 0, message)
        self.scr.move(y, x)

    def clear_process_list(self):
        y, x = self.scr.getyx()
        offset = 5
        self.scr.addstr(offset, 0, "-" * 40)
        offset += 1
        for idx in range(self.process_table.get_count()):
            self.scr.move(idx + offset, 0)
            self.scr.clrtoeol()
        self.scr.move(y, x)

    def show_description(self):
        desc = {
            "exit": "Exit this program",
            "start <num/all>": "(Re)start <num>-th process or all process",
            "kill <num/all>": "Kill <num>-th process or all process",
            "delete <num/all>": "Delete <num>-th row or all rows",
            "add <name> <args>": "Add new process to list",
            "save <name>": "Save current setting as config",
            "load <name>": "Load saved config",
        }
        y, x = self.scr.getyx()
        offset = 5 + self.process_table.get_count() + 2
        for idx, key in enumerate(desc.keys()):
            val = desc[key]
            message = f"{key:20} : {val}"
            self.scr.move(idx + offset, 0)
            self.scr.clrtoeol()
            self.scr.addstr(idx + offset, 0, message)
            self.scr.move(y, x)


def main(stdscr):
    curses.noraw()
    appli = Application(stdscr)
    appli.mainloop()


if __name__ == "__main__":
    curses.wrapper(main)
