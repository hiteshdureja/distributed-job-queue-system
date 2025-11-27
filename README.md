# 🚀 Django Distributed Task Queue Prototype

This project is a simplified, fault-tolerant job queue system built on Django and SQLite. It demonstrates core concepts of distributed processing: job leasing via atomic database locking (`select_for_update`), rate limiting, concurrent job quotas, and a retry mechanism with a Dead Letter Queue (DLQ).

## ✨ Features

* **Atomic Job Leasing:** Prevents multiple workers from processing the same job concurrently.
* **API Endpoints:** Submit new jobs, check job status, and interact with the DLQ.
* **Rate Limiting & Quotas:** Limits jobs per minute and concurrent active jobs per user ID.
* **Fault Tolerance:** Automatic retries (max 3) before moving the job to the DLQ (`FAILED` status).
* **Web Dashboard:** Real-time monitoring of queue statistics, recent jobs, and manual DLQ management (re-queue/force-success).

## 🛠️ Setup and Installation

### Prerequisites

* Python 3.8+
* pip

### Step 1: Clone the Repository and Setup Environment

```bash
git clone https://github.com/hiteshdureja/distributed-job-queue-system.git
cd distributed-job-queue-system

python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install Django
```

### Step 3: Database Migration

Initialize the SQLite database and create the necessary tables (`core_job`):

```bash
python manage.py makemigrations core
python manage.py migrate
```

## Running the System

The system requires two components running concurrently: the **Django Web Server (API/Dashboard)** and at least one **Worker Process**.

### 1. Run the Django Server (Terminal 1)

This runs the submission API, status API, and the dashboard.

```bash
python manage.py runserver
```

### 2. Run the Worker Process (Terminal 2)

Open a **separate terminal**, activate the `venv`, and run the custom worker command. This process polls the database, leases jobs, executes tasks (simulated by a `time.sleep`), and handles retries.

```bash
source venv/bin/activate
python manage.py runworker
```
> **To test concurrency, open several terminals and run `python manage.py runworker` in each.**

## Testing and Interaction

### A. Web Dashboard

Access the real-time queue monitor and job submission form here:

👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

### B. API Submission (cURL)

You can submit jobs via the API. The `duration` key simulates the work time (in seconds).

#### 1. Successful Job

```bash
curl -X POST http://127.0.0.1:8000/api/submit/ \
     -H "Content-Type: application/json" \
     -d '{"user_id": "alice", "payload": {"duration": 5}}'
```

#### 2. Failing Job (Testing Retry and DLQ)

Include `"fail_simulation": true` to force the worker to raise an exception. It will retry the task **3 times** before setting the status to `FAILED` and moving it to the DLQ.

```bash
curl -X POST http://127.0.0.1:8000/api/submit/ \
     -H "Content-Type: application/json" \
     -d '{"user_id": "bob", "payload": {"fail_simulation": true, "duration": 1}}'
```

### C. Check Job Status

Use the `job_id` returned from the submission command to check the status.

```bash
# Replace the UUID with your actual Job ID
curl http://127.0.0.1:8000/api/status/YOUR-JOB-ID-UUID/
```

### D. DLQ Management (Re-queue via API)

You can manually trigger actions on jobs in the `FAILED` or `COMPLETED` state (the dashboard uses these endpoints).

```bash
curl -X POST http://127.0.0.1:8000/api/requeue/YOUR-JOB-ID/ \
     -H "Content-Type: application/json" \
     -d '{"action": "REQUEUE"}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/requeue/YOUR-JOB-ID/ \
     -H "Content-Type: application/json" \
     -d '{"action": "FORCE_SUCCESS"}'
```


### A. Design Trade-offs

This prototype prioritizes simplicity and using the **database as the single source of truth** for all queue state. This involved key architectural trade-offs compared to production systems:

| Feature | Choice Made | Rationale & Production Alternative |
| :--- | :--- | :--- |
| **Queue Backend** | **SQLite Database** | **Rationale:** Met the requirement for durability and forced manual implementation of the critical **Lease/Ack/Retry** logic using Django's `select_for_update`. **Alternative:** In production, this would be **Redis (for high throughput)** or **AWS SQS (for distributed reliability)**. |
| **Job Polling** | **Busy-Wait Worker Loop** (`while True: sleep(2)`) | **Rationale:** Simple to implement using a custom Django Management Command. **Alternative:** Production workers should be **event-driven** (e.g., consuming SQS/Kafka messages) or use **Long Polling** to avoid continuously hitting the database. |
| **Rate Limiting** | **Database Lookups** (Querying recent jobs) | **Rationale:** Simplified implementation by centralizing state in the existing DB. **Alternative:** For performance, rate limits should be enforced using a dedicated, low-latency store like **Redis** for fast lookups (e.g., using the Sliding Window Log technique). |
| **DLQ Implementation** | **DB Status Field** (`status='FAILED'`) | **Rationale:** Highly simplified monitoring and re-queueing (just an `UPDATE` command). **Alternative:** A true DLQ would be a separate, isolated queue that requires explicit movement of messages, ensuring failed data is logically separated from active jobs. |

### B. Auto-Scaling Workers (Conceptual Plan)

To achieve true distributed scalability, an external mechanism would dynamically adjust the number of worker instances based on queue load.

| Component | Policy/Metric | Action |
| :--- | :--- | :--- |
| **Scaling Metric** | The number of jobs with `status='PENDING'`. | This is the primary indicator of queue backlog/demand. |
| **Scaler Service** | A dedicated service polls the DB for the PENDING job count and interacts with the orchestrator. | Executes the scale-up/scale-down commands. |
| **Scale Up Threshold** | `PENDING Jobs > 10` **and** `Workers < Max (e.g., 50)`. | **Deploy 1-2 new worker instances** via the orchestrator (e.g., Kubernetes HPA).  |
| **Scale Down Threshold**| `PENDING Jobs = 0` **for** `5 consecutive minutes`. | **Terminate 1 worker instance** to reduce operational costs. |