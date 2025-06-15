# Operating System Shell

A Python-based shell implementation with process scheduling capabilities.

## Prerequisites
- Python 3.x installed on a Unix-like system (Linux/macOS or WSL on Windows)

## Running the Shell
```bash
python3 shell.py
```

## Features

### Basic Shell Commands
- `cd`: Change directory
- `pwd`: Print working directory
- `ls`: List directory contents
- `cat`: Display file contents
- `mkdir`: Create directory
- `rmdir`: Remove directory
- `rm`: Remove file
- `touch`: Create empty file
- `echo`: Print text
- `clear`: Clear terminal
- `exit`: Exit shell

### Process Management
- `jobs`: List all background jobs
- `fg`: Bring a background job to foreground
- `bg`: Continue a stopped job in background
- `kill`: Terminate a process by PID

### Process Scheduling

#### Round-Robin Scheduling
Use the `--rr` flag with any command to schedule it using round-robin algorithm:
```bash
osh> sleep 10 --rr
```

To start round-robin scheduling with a specific time slice:
```bash
osh> schedule-rr <time_slice_in_seconds>
```

#### Priority-Based Scheduling
Schedule processes with priorities using the `--priority` flag:
```bash
osh> sleep 10 --priority 1  # Higher priority (lower number = higher priority)
osh> sleep 10 --priority 5  # Lower priority
```

To start priority-based scheduling:
```bash
osh> schedule-priority
```

### Background Processing
Add `&` at the end of any command to run it in the background:
```bash
osh> sleep 10 &
```

## Performance Metrics
The shell tracks and displays the following metrics for scheduled jobs:
- Turnaround Time
- Waiting Time
- Response Time

## Notes
- Higher priority jobs (lower priority numbers) will preempt lower priority jobs
- Round-robin scheduling ensures fair CPU time distribution among processes
- Background jobs can be managed using `jobs`, `fg`, and `bg` commands
