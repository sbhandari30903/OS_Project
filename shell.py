#!/usr/bin/env python3
import os
import sys
import shlex
import signal
import subprocess
import readline
import time
import heapq
import threading
import random
from collections import deque, OrderedDict
from threading import Lock, Semaphore, Condition

# Global variables
jobs = []
scheduling_queue = deque()
priority_queue = []  # heap
current_running_priority_job = None

# Memory Management
TOTAL_MEMORY_PAGES = 20  # Total physical memory pages
PAGE_SIZE = 4096  # 4KB pages
memory_frames = [None] * TOTAL_MEMORY_PAGES  # Physical memory frames
process_page_tables = {}  # Page tables for each process
page_fault_count = 0
memory_lock = Lock()

# Process Synchronization
shared_buffer = deque(maxlen=10)  # Producer-Consumer buffer
buffer_mutex = Lock()
buffer_not_empty = Condition(buffer_mutex)
buffer_not_full = Condition(buffer_mutex)
producer_count = 0
consumer_count = 0

# Dining Philosophers
NUM_PHILOSOPHERS = 5
forks = [Lock() for _ in range(NUM_PHILOSOPHERS)]
philosophers_active = False

class Page:
    def __init__(self, process_id, page_number, data=None):
        self.process_id = process_id
        self.page_number = page_number
        self.data = data or f"Page {page_number} of Process {process_id}"
        self.last_accessed = time.time()
        self.loaded_time = time.time()

class PageTable:
    def __init__(self, process_id, num_pages):
        self.process_id = process_id
        self.num_pages = num_pages
        self.page_to_frame = {}  # Virtual page -> Physical frame mapping
        self.pages_in_memory = set()
        
class MemoryManager:
    def __init__(self):
        self.fifo_queue = deque()  # For FIFO replacement
        self.lru_access_order = OrderedDict()  # For LRU replacement
        self.replacement_algorithm = 'FIFO'  # Default algorithm
        
    def allocate_pages(self, process_id, num_pages):
        """Allocate pages for a process"""
        with memory_lock:
            if process_id not in process_page_tables:
                process_page_tables[process_id] = PageTable(process_id, num_pages)
            
            allocated_pages = []
            for page_num in range(num_pages):
                page = Page(process_id, page_num)
                frame_index = self._find_free_frame()
                
                if frame_index is not None:
                    # Page can be loaded directly
                    memory_frames[frame_index] = page
                    process_page_tables[process_id].page_to_frame[page_num] = frame_index
                    process_page_tables[process_id].pages_in_memory.add(page_num)
                    
                    self.fifo_queue.append((process_id, page_num, frame_index))
                    self.lru_access_order[(process_id, page_num)] = frame_index
                    allocated_pages.append(page_num)
                else:
                    # Memory is full, but we'll handle page faults when accessed
                    print(f"Memory full. Page {page_num} of process {process_id} will be loaded on demand.")
            
            return allocated_pages
    
    def access_page(self, process_id, page_number):
        """Access a page, handling page faults if necessary"""
        global page_fault_count
        
        with memory_lock:
            if process_id not in process_page_tables:
                print(f"Error: Process {process_id} not found in page tables")
                return None
                
            page_table = process_page_tables[process_id]
            
            if page_number in page_table.pages_in_memory:
                # Page hit
                frame_index = page_table.page_to_frame[page_number]
                page = memory_frames[frame_index]
                page.last_accessed = time.time()
                
                # Update LRU order
                if (process_id, page_number) in self.lru_access_order:
                    del self.lru_access_order[(process_id, page_number)]
                self.lru_access_order[(process_id, page_number)] = frame_index
                
                print(f"Page hit: Process {process_id}, Page {page_number} -> Frame {frame_index}")
                return frame_index
            else:
                # Page fault
                page_fault_count += 1
                print(f"Page fault #{page_fault_count}: Process {process_id}, Page {page_number}")
                
                # Load page into memory
                page = Page(process_id, page_number)
                frame_index = self._find_free_frame()
                
                if frame_index is None:
                    # Need page replacement
                    frame_index = self._replace_page()
                
                # Load the page
                memory_frames[frame_index] = page
                page_table.page_to_frame[page_number] = frame_index
                page_table.pages_in_memory.add(page_number)
                
                # Update replacement algorithm data structures
                self.fifo_queue.append((process_id, page_number, frame_index))
                self.lru_access_order[(process_id, page_number)] = frame_index
                
                print(f"Page loaded: Process {process_id}, Page {page_number} -> Frame {frame_index}")
                return frame_index
    
    def _find_free_frame(self):
        """Find a free memory frame"""
        for i, frame in enumerate(memory_frames):
            if frame is None:
                return i
        return None
    
    def _replace_page(self):
        """Replace a page using the selected algorithm"""
        if self.replacement_algorithm == 'FIFO':
            return self._fifo_replace()
        elif self.replacement_algorithm == 'LRU':
            return self._lru_replace()
        else:
            return self._fifo_replace()  # Default to FIFO
    
    def _fifo_replace(self):
        """FIFO page replacement"""
        if not self.fifo_queue:
            return 0  # Fallback to first frame
            
        old_process_id, old_page_num, frame_index = self.fifo_queue.popleft()
        
        # Remove from old process's page table
        if old_process_id in process_page_tables:
            old_page_table = process_page_tables[old_process_id]
            if old_page_num in old_page_table.page_to_frame:
                del old_page_table.page_to_frame[old_page_num]
            old_page_table.pages_in_memory.discard(old_page_num)
        
        # Remove from LRU tracking
        if (old_process_id, old_page_num) in self.lru_access_order:
            del self.lru_access_order[(old_process_id, old_page_num)]
            
        print(f"FIFO replacement: Evicted Process {old_process_id}, Page {old_page_num} from Frame {frame_index}")
        return frame_index
    
    def _lru_replace(self):
        """LRU page replacement"""
        if not self.lru_access_order:
            return 0  # Fallback to first frame
            
        # Get least recently used page
        (old_process_id, old_page_num), frame_index = self.lru_access_order.popitem(last=False)
        
        # Remove from old process's page table
        if old_process_id in process_page_tables:
            old_page_table = process_page_tables[old_process_id]
            if old_page_num in old_page_table.page_to_frame:
                del old_page_table.page_to_frame[old_page_num]
            old_page_table.pages_in_memory.discard(old_page_num)
        
        # Remove from FIFO queue
        self.fifo_queue = deque([(pid, pnum, findex) for pid, pnum, findex in self.fifo_queue 
                                if not (pid == old_process_id and pnum == old_page_num)])
            
        print(f"LRU replacement: Evicted Process {old_process_id}, Page {old_page_num} from Frame {frame_index}")
        return frame_index
    
    def deallocate_process(self, process_id):
        """Deallocate all pages for a process"""
        with memory_lock:
            if process_id not in process_page_tables:
                return
                
            page_table = process_page_tables[process_id]
            
            # Free all frames used by this process
            for page_num, frame_index in page_table.page_to_frame.items():
                memory_frames[frame_index] = None
                
            # Remove from tracking structures
            self.fifo_queue = deque([(pid, pnum, findex) for pid, pnum, findex in self.fifo_queue 
                                    if pid != process_id])
            
            keys_to_remove = [(pid, pnum) for pid, pnum in self.lru_access_order.keys() 
                             if pid == process_id]
            for key in keys_to_remove:
                del self.lru_access_order[key]
            
            # Remove page table
            del process_page_tables[process_id]
            print(f"Deallocated all pages for process {process_id}")
    
    def print_memory_status(self):
        """Print current memory status"""
        print("\n=== Memory Status ===")
        print(f"Total Frames: {TOTAL_MEMORY_PAGES}")
        used_frames = sum(1 for frame in memory_frames if frame is not None)
        print(f"Used Frames: {used_frames}")
        print(f"Free Frames: {TOTAL_MEMORY_PAGES - used_frames}")
        print(f"Page Faults: {page_fault_count}")
        print(f"Replacement Algorithm: {self.replacement_algorithm}")
        
        print("\nFrame Contents:")
        for i, frame in enumerate(memory_frames):
            if frame:
                print(f"Frame {i}: Process {frame.process_id}, Page {frame.page_number}")
            else:
                print(f"Frame {i}: Empty")
        print("=====================\n")

# Global memory manager instance
memory_manager = MemoryManager()

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
        self.allocated_pages = []

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
            
            # Allocate memory pages for the process
            num_pages = random.randint(2, 5)  # Random number of pages needed
            self.allocated_pages = memory_manager.allocate_pages(self.pid, num_pages)
            
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
        print(f"Response Time: {response:.2f}s")
        print(f"Allocated Pages: {len(self.allocated_pages)}")
        
        # Deallocate memory pages
        if self.pid:
            memory_manager.deallocate_process(self.pid)

# Producer-Consumer Implementation
def producer_task(producer_id, items_to_produce):
    """Producer thread function"""
    global producer_count
    
    for i in range(items_to_produce):
        item = f"Item-{producer_id}-{i}"
        
        with buffer_not_full:
            while len(shared_buffer) >= shared_buffer.maxlen:
                print(f"Producer {producer_id}: Buffer full, waiting...")
                buffer_not_full.wait()
            
            shared_buffer.append(item)
            producer_count += 1
            print(f"Producer {producer_id}: Produced {item} (Buffer size: {len(shared_buffer)})")
            buffer_not_empty.notify()
        
        time.sleep(random.uniform(0.1, 0.5))  # Simulate work
    
    print(f"Producer {producer_id}: Finished producing {items_to_produce} items")

def consumer_task(consumer_id, items_to_consume):
    """Consumer thread function"""
    global consumer_count
    
    for i in range(items_to_consume):
        with buffer_not_empty:
            while len(shared_buffer) == 0:
                print(f"Consumer {consumer_id}: Buffer empty, waiting...")
                buffer_not_empty.wait()
            
            item = shared_buffer.popleft()
            consumer_count += 1
            print(f"Consumer {consumer_id}: Consumed {item} (Buffer size: {len(shared_buffer)})")
            buffer_not_full.notify()
        
        time.sleep(random.uniform(0.1, 0.5))  # Simulate work
    
    print(f"Consumer {consumer_id}: Finished consuming {items_to_consume} items")

# Dining Philosophers Implementation
def philosopher_task(philosopher_id):
    """Philosopher thread function"""
    left_fork = forks[philosopher_id]
    right_fork = forks[(philosopher_id + 1) % NUM_PHILOSOPHERS]
    
    for meal in range(3):  # Each philosopher eats 3 times
        # Think
        print(f"Philosopher {philosopher_id}: Thinking...")
        time.sleep(random.uniform(1, 3))
        
        # Try to pick up forks (avoid deadlock by ordering)
        first_fork = left_fork if philosopher_id % 2 == 0 else right_fork
        second_fork = right_fork if philosopher_id % 2 == 0 else left_fork
        
        print(f"Philosopher {philosopher_id}: Hungry, trying to pick up forks...")
        
        with first_fork:
            print(f"Philosopher {philosopher_id}: Picked up first fork")
            with second_fork:
                print(f"Philosopher {philosopher_id}: Picked up second fork, eating meal {meal + 1}...")
                time.sleep(random.uniform(1, 2))  # Eat
                print(f"Philosopher {philosopher_id}: Finished eating meal {meal + 1}")
        
        print(f"Philosopher {philosopher_id}: Put down both forks")
    
    print(f"Philosopher {philosopher_id}: Finished all meals")

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
        
        # Simulate memory access during execution
        if job.pid and job.allocated_pages:
            page_to_access = random.choice(range(len(job.allocated_pages) + 2))  # May cause page fault
            memory_manager.access_page(job.pid, page_to_access)
        
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
        
        # Simulate memory access during execution
        if job.pid and job.allocated_pages:
            page_to_access = random.choice(range(len(job.allocated_pages) + 2))  # May cause page fault
            memory_manager.access_page(job.pid, page_to_access)
        
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
        job.pid = process.pid
        
        # Allocate memory pages for the process
        num_pages = random.randint(2, 5)
        job.allocated_pages = memory_manager.allocate_pages(job.pid, num_pages)
        
        jobs.append(job)

        if background:
            print(f"[{len(jobs)}] {process.pid}")
        else:
            process.wait()
            job.status = 'Done'
            job.finalize_metrics()
    except FileNotFoundError:
        print(f"{cmd_tokens[0]}: command not found")
    except Exception as e:
        print(f"Error executing command: {e}")

def builtin_command(cmd_tokens):
    global philosophers_active
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
            pid = int(cmd_tokens[1])
            os.kill(pid, signal.SIGTERM)
            # Deallocate memory for killed process
            memory_manager.deallocate_process(pid)
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
            job.finalize_metrics()
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

    # Memory Management Commands
    elif command == 'mem-status':
        memory_manager.print_memory_status()

    elif command == 'mem-access':
        try:
            process_id = int(cmd_tokens[1])
            page_number = int(cmd_tokens[2])
            memory_manager.access_page(process_id, page_number)
        except (IndexError, ValueError):
            print("Usage: mem-access [process_id] [page_number]")

    elif command == 'mem-algorithm':
        try:
            algorithm = cmd_tokens[1].upper()
            if algorithm in ['FIFO', 'LRU']:
                memory_manager.replacement_algorithm = algorithm
                print(f"Page replacement algorithm set to {algorithm}")
            else:
                print("Available algorithms: FIFO, LRU")
        except IndexError:
            print(f"Current algorithm: {memory_manager.replacement_algorithm}")
            print("Usage: mem-algorithm [FIFO|LRU]")

    # Process Synchronization Commands
    elif command == 'producer-consumer':
        try:
            num_producers = int(cmd_tokens[1]) if len(cmd_tokens) > 1 else 2
            num_consumers = int(cmd_tokens[2]) if len(cmd_tokens) > 2 else 2
            items_per_producer = int(cmd_tokens[3]) if len(cmd_tokens) > 3 else 5
            
            print(f"Starting Producer-Consumer simulation:")
            print(f"Producers: {num_producers}, Consumers: {num_consumers}, Items per producer: {items_per_producer}")
            
            # Clear buffer and counters
            shared_buffer.clear()
            global producer_count, consumer_count
            producer_count = 0
            consumer_count = 0
            
            threads = []
            
            # Start producer threads
            for i in range(num_producers):
                thread = threading.Thread(target=producer_task, args=(i, items_per_producer))
                threads.append(thread)
                thread.start()
            
            # Start consumer threads
            items_per_consumer = (num_producers * items_per_producer) // num_consumers
            for i in range(num_consumers):
                thread = threading.Thread(target=consumer_task, args=(i, items_per_consumer))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            print(f"\nProducer-Consumer simulation completed!")
            print(f"Total items produced: {producer_count}")
            print(f"Total items consumed: {consumer_count}")
            print(f"Items remaining in buffer: {len(shared_buffer)}")
            
        except ValueError:
            print("Usage: producer-consumer [num_producers] [num_consumers] [items_per_producer]")

    elif command == 'dining-philosophers':
        if philosophers_active:
            print("Dining philosophers simulation is already running!")
        else:
            print("Starting Dining Philosophers simulation...")
            philosophers_active = True
            
            threads = []
            for i in range(NUM_PHILOSOPHERS):
                thread = threading.Thread(target=philosopher_task, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all philosophers to finish
            for thread in threads:
                thread.join()
            
            philosophers_active = False
            print("Dining Philosophers simulation completed!")

    elif command == 'help-memory':
        print("Memory Management Commands:")
        print("  mem-status                    - Show current memory status")
        print("  mem-access [pid] [page]       - Access a specific page")
        print("  mem-algorithm [FIFO|LRU]      - Set/show page replacement algorithm")

    elif command == 'help-sync':
        print("Process Synchronization Commands:")
        print("  producer-consumer [producers] [consumers] [items] - Run producer-consumer simulation")
        print("  dining-philosophers           - Run dining philosophers simulation")

    else:
        return False

    return True

def shell_loop():
    print("Enhanced Operating System Shell")
    print("Features: Job Scheduling, Memory Management, Process Synchronization")
    print("Type 'help-memory' or 'help-sync' for additional commands")
    print()
    
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