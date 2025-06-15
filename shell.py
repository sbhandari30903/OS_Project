#!/usr/bin/env python3
import os
import sys
import shlex
import signal
import subprocess
import readline
import time
import heapq
from collections import deque

jobs = []
scheduling_queue = deque()
priority_queue = []  # heap
current_running_priority_job = None

class Job:
    def __init__(self, command, priority=0):
        self.command = command
        self.priority = priority
        self.status = 'Ready'
        self.process = None
        self.pid = None
        self.start_time = None
        self.response_time = None
        self.completion_time = None
        self.start_order = time.time()

    def start(self):
        try:
            self.start_time = time.time()
            self.process = subprocess.Popen(
                shlex.split(self.command),
                start_new_session=True
            )
            self.status = 'Running'
            self.pid = self.process.pid
            if self.response_time is None:
                self.response_time = self.start_time - self.start_order
        except Exception as e:
            print(f"Failed to start job '{self.command}': {e}")
            self.status = 'Failed'

    def is_finished(self):
        return self.process.poll() is not None if self.process else True

    def finalize_metrics(self):
        self.completion_time = time.time()
        turnaround = self.completion_time - self.start_order
        waiting = turnaround - (self.completion_time - self.start_time)
        response = self.response_time if self.response_time is not None else 0
        print(f"\nPerformance Metrics for {self.command} [PID: {self.pid}]:")
        print(f"Turnaround Time: {turnaround:.2f}s")
        print(f"Waiting Time: {waiting:.2f}s")
        print(f"Response Time: {response:.2f}s\n")

def simulate_round_robin(time_slice):
    global scheduling_queue
    print(f"Starting Round-Robin scheduling with time slice = {time_slice}s")
    active_jobs = list(scheduling_queue)
    scheduling_queue.clear()

    while active_jobs:
        job = active_jobs.pop(0)
        if job.process is None:
            job.start()

        if job.is_finished():
            print(f"Job '{job.command}' already finished.")
            job.status = 'Done'
            job.finalize_metrics()
            continue

        print(f"Running: {job.command} [PID: {job.process.pid}] for {time_slice}s")
        try:
            os.kill(job.process.pid, signal.SIGCONT)
        except Exception:
            pass

        start = time.time()
        while time.time() - start < time_slice:
            if job.is_finished():
                break
            time.sleep(0.1)

        if job.is_finished():
            job.status = 'Done'
            print(f"Completed: {job.command} [PID: {job.process.pid}]")
            job.finalize_metrics()
        else:
            try:
                os.kill(job.process.pid, signal.SIGSTOP)
                job.status = 'Stopped'
                print(f"Time slice expired. Stopping: {job.command} [PID: {job.process.pid}]")
                active_jobs.append(job)
            except Exception as e:
                print(f"Error stopping process {job.process.pid}: {e}")



def simulate_priority_scheduling():
    global current_running_priority_job
    print("Starting Priority-Based Scheduling")
    while priority_queue:
        priority, start_order, job = heapq.heappop(priority_queue)

        if job.process is None:
            job.start()
        if job.process is None or job.pid is None:
            print(f"Skipping job '{job.command}' due to failed start.")
            continue
        elif job.is_finished():
            job.status = 'Done'
            print(f"Job '{job.command}' already finished.")
            job.finalize_metrics()
            continue

        if current_running_priority_job and not current_running_priority_job.is_finished():
            if priority < current_running_priority_job.priority:
                print(f"Preempting job {current_running_priority_job.command} for higher priority job {job.command}")
                try:
                    os.kill(current_running_priority_job.process.pid, signal.SIGSTOP)
                    current_running_priority_job.status = 'Stopped'
                    heapq.heappush(priority_queue, (current_running_priority_job.priority, current_running_priority_job.start_order, current_running_priority_job))
                except Exception as e:
                    print(f"Failed to stop lower priority job: {e}")

        print(f"Running: {job.command} [PID: {job.process.pid}] with priority {priority}")
        current_running_priority_job = job
        try:
            os.kill(job.process.pid, signal.SIGCONT)
        except Exception as e:
            print(f"Error resuming job {job.command}: {e}")

        while not job.is_finished():
            time.sleep(0.5)

        job.status = 'Done'
        print(f"Completed: {job.command} [PID: {job.process.pid}]")
        job.finalize_metrics()
        current_running_priority_job = None

def execute_command(cmd_tokens, background, priority=0):
    try:
        process = subprocess.Popen(cmd_tokens)
        job = Job(' '.join(cmd_tokens), priority)
        job.process = process
        job.status = 'Running'
        jobs.append(job)

        if background:
            print(f"[{len(jobs)}] {process.pid}")
        else:
            process.wait()
            job.status = 'Done'
    except FileNotFoundError:
        print(f"{cmd_tokens[0]}: command not found")
    except Exception as e:
        print(f"Error executing command: {e}")

def builtin_command(cmd_tokens):
    command = cmd_tokens[0]

    if command == 'cd':
        try:
            os.chdir(cmd_tokens[1])
        except IndexError:
            print("cd: missing argument")
        except FileNotFoundError:
            print(f"cd: {cmd_tokens[1]}: No such directory")

    elif command == 'pwd':
        print(os.getcwd())

    elif command == 'exit':
        sys.exit(0)

    elif command == 'echo':
        print(' '.join(cmd_tokens[1:]))

    elif command == 'clear':
        os.system('clear')

    elif command == 'ls':
        print('\n'.join(os.listdir('.')))

    elif command == 'cat':
        try:
            with open(cmd_tokens[1], 'r') as f:
                print(f.read())
        except IndexError:
            print("cat: missing file operand")
        except FileNotFoundError:
            print(f"cat: {cmd_tokens[1]}: No such file")

    elif command == 'mkdir':
        try:
            os.mkdir(cmd_tokens[1])
        except IndexError:
            print("mkdir: missing directory name")
        except FileExistsError:
            print(f"mkdir: {cmd_tokens[1]}: Directory already exists")

    elif command == 'rmdir':
        try:
            os.rmdir(cmd_tokens[1])
        except IndexError:
            print("rmdir: missing directory name")
        except FileNotFoundError:
            print(f"rmdir: {cmd_tokens[1]}: No such directory")

    elif command == 'rm':
        try:
            os.remove(cmd_tokens[1])
        except IndexError:
            print("rm: missing file name")
        except FileNotFoundError:
            print(f"rm: {cmd_tokens[1]}: No such file")

    elif command == 'touch':
        try:
            open(cmd_tokens[1], 'a').close()
        except IndexError:
            print("touch: missing file name")

    elif command == 'kill':
        try:
            os.kill(int(cmd_tokens[1]), signal.SIGTERM)
        except IndexError:
            print("kill: missing pid")
        except ProcessLookupError:
            print(f"kill: {cmd_tokens[1]}: No such process")

    elif command == 'jobs':
        for i, job in enumerate(jobs):
            print(f"[{i+1}] {job.process.pid if job.process else 'N/A'} {job.status} {job.command}")

    elif command == 'fg':
        try:
            job_id = int(cmd_tokens[1]) - 1
            job = jobs[job_id]
            os.kill(job.process.pid, signal.SIGCONT)
            os.waitpid(job.process.pid, 0)
            job.status = 'Done'
        except IndexError:
            print("fg: missing job ID")
        except Exception:
            print("fg: invalid job ID")

    elif command == 'bg':
        try:
            job_id = int(cmd_tokens[1]) - 1
            job = jobs[job_id]
            os.kill(job.process.pid, signal.SIGCONT)
            job.status = 'Running'
        except IndexError:
            print("bg: missing job ID")
        except Exception:
            print("bg: invalid job ID")

    elif command == 'schedule-rr':
        try:
            time_slice = int(cmd_tokens[1])
            simulate_round_robin(time_slice)
        except (IndexError, ValueError):
            print("Usage: schedule-rr [time_slice_in_seconds]")

    elif command == 'schedule-priority':
        simulate_priority_scheduling()

    else:
        return False

    return True

def shell_loop():
    while True:
        try:
            raw_input_cmd = input("osh> ").strip()
            if not raw_input_cmd:
                continue
            background = raw_input_cmd.endswith('&')
            if background:
                raw_input_cmd = raw_input_cmd[:-1].strip()

            cmd_tokens = shlex.split(raw_input_cmd)
            command_string = ' '.join(cmd_tokens)

            # Check for priority flag
            priority = 0
            if '--priority' in cmd_tokens:
                try:
                    idx = cmd_tokens.index('--priority')
                    priority = int(cmd_tokens[idx + 1])
                    del cmd_tokens[idx:idx+2]
                except (IndexError, ValueError):
                    print("Invalid priority value.")
                    continue

            if not builtin_command(cmd_tokens):
                if '--rr' in cmd_tokens:
                    cmd_tokens.remove('--rr')
                    job = Job(' '.join(cmd_tokens))
                    scheduling_queue.append(job)
                elif priority > 0:
                    job = Job(' '.join(cmd_tokens), priority)
                    heapq.heappush(priority_queue, (priority, time.time(), job))
                else:
                    execute_command(cmd_tokens, background, priority)
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit the shell.")
        except EOFError:
            print("\nExiting shell.")
            break

if __name__ == '__main__':
    shell_loop()
