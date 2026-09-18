# Smart Task Board

A Django-based task management application developed as part of the technical coding assignment for **Capace Software Pvt. Ltd.**

The application allows users to create and complete tasks while enforcing priority-based, time-based, locking, and hidden business rules.

---

## 1. Overview

Smart Task Board provides a simple task management interface where each task contains:

* Title
* Priority
* Estimated completion time
* Created timestamp
* Completion timestamp
* Temporary lock information

The application also implements special business rules that control whether a task can be completed.

---

## 2. Technology Stack

| Component            | Technology            |
| -------------------- | --------------------- |
| Programming Language | Python                |
| Backend Framework    | Django                |
| Database             | SQLite                |
| Frontend             | Django Templates      |
| Styling              | HTML5, CSS3           |
| ORM                  | Django ORM            |
| Testing              | Django Test Framework |

The project uses a simple Django monolith because the assignment does not require external APIs, asynchronous workers, or a separate frontend framework.

---

## 3. Features

### Task Management

Users can:

* Create tasks
* Select task priority
* Define estimated completion time
* View task creation time
* Complete eligible tasks
* View task status
* View temporary task locking

### Supported Priorities

* Low
* Medium
* High

### Task Status

A task can appear as:

* Pending
* Locked
* Completed

Status is calculated dynamically instead of being stored separately in the database.

---

## 4. Business Rules

### Rule 1: High Priority Dependency

A High priority task cannot be completed until at least one Low priority task has already been completed.

Example:

```text
Low Task     -> Pending
High Task    -> Cannot complete

Low Task     -> Completed
High Task    -> Completion may proceed
```

The user is not shown the exact rule when completion fails.

A cryptic hint is displayed instead.

Example:

```text
A smaller piece must move before this one.
```

---

### Rule 2: Rapid Task Creation Lock

If at least three tasks have been created during the previous two-minute window, a newly created task is locked for five minutes.

Example:

```text
Task 1 -> Normal
Task 2 -> Normal
Task 3 -> Normal
Task 4 -> Locked
```

The application stores the lock expiry timestamp in `locked_until`.

No scheduled background worker is required.

A task is considered locked when:

```text
current_time < locked_until
```

After the lock expiry time passes, the task automatically becomes available again.

### Implementation Interpretation

The two-minute rule is implemented using a rolling time window.

Therefore, additional tasks created while three or more tasks are still present inside that two-minute window can also become locked.

This interpretation is documented because the original requirement can be read in more than one way.

---

### Rule 3: Odd and Even Minute Behavior

Tasks created during odd-numbered minutes have a completion deadline.

The deadline is:

```text
created_at + estimated_time
```

Example:

```text
Created At:       10:31
Estimated Time:   15 minutes
Deadline:         10:46
```

Because minute `31` is odd, the task must be completed by `10:46`.

Tasks created during even-numbered minutes do not receive this additional deadline restriction.

Example:

```text
Created At: 10:32
```

Since `32` is even, the estimated time is informational and does not create an additional completion deadline.

This interpretation is explicitly documented because the assignment specification does not define the exact odd/even behavior.

---

### Rule 4: Hidden Completion Logic

A task may refuse to complete because of an additional hidden rule.

The application uses deterministic SHA-256 based logic instead of random behavior.

Inputs include:

* Task ID
* Task title
* Estimated time

This ensures:

* The behavior remains hidden from the user.
* The same task produces the same hidden-rule result.
* Automated tests remain deterministic.
* Completion behavior does not randomly change between requests.

The frontend never reveals the internal condition.

A cryptic hint is displayed:

```text
Something unseen blocked the final step.
```

---

## 5. Cryptic Failure Hints

The assignment requires the system to avoid showing the actual completion failure reason.

Examples include:

```text
This card has already crossed the finish line.

The board is not ready for this move yet.

A smaller piece must move before this one.

The clock moved before the task did.

Something unseen blocked the final step.
```

Business-rule implementation details remain server-side.

---

## 6. Application Architecture

The project follows a layered Django structure:

```text
Browser
   |
   v
Django Templates
   |
   v
Views
   |
   v
Forms
   |
   v
Service / Business Rule Layer
   |
   v
Django Models
   |
   v
SQLite Database
```

Business logic is kept outside views and models where practical.

The main rule implementation exists inside:

```text
tasks/services.py
```

This improves:

* Separation of concerns
* Testability
* Maintainability
* Readability

---

## 7. Project Structure

```text
smart-task-board/
|
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
|
├── tasks/
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   │
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── services.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
|
├── templates/
│   └── tasks/
│       └── board.html
|
├── static/
│   └── tasks/
│       └── board.css
|
├── .gitignore
├── Database.md
├── README.md
├── db.sqlite3
├── manage.py
└── requirements.txt
```

---

## 8. Core Model

The main application model is:

```text
Task
```

Fields:

| Field          | Type                 | Description                                |
| -------------- | -------------------- | ------------------------------------------ |
| id             | BigAutoField         | Primary key                                |
| title          | CharField            | Task title                                 |
| priority       | CharField            | LOW, MEDIUM or HIGH                        |
| estimated_time | PositiveIntegerField | Estimated time in minutes                  |
| created_at     | DateTimeField        | Automatically generated creation timestamp |
| completed_at   | DateTimeField        | Completion timestamp                       |
| locked_until   | DateTimeField        | Lock expiration timestamp                  |

For complete database documentation, see:

```text
Database.md
```

---

## 9. Important Model Properties

### `is_completed`

Returns whether the task has already been completed.

```python
@property
def is_completed(self):
    return self.completed_at is not None
```

### `is_locked`

Determines whether the current time is before the lock expiry.

```python
@property
def is_locked(self):
    if self.locked_until is None:
        return False

    return timezone.now() < self.locked_until
```

### `status`

Returns one of:

```text
Pending
Locked
Completed
```

Status is calculated dynamically instead of being duplicated inside the database.

---

## 10. Business Service Layer

The application's business rules are implemented in:

```text
tasks/services.py
```

Important functions include:

### `create_task()`

Responsible for:

* Creating tasks
* Checking recently created tasks
* Applying the five-minute lock when required

### `high_priority_requirement_met()`

Checks whether a High priority task is allowed to proceed.

### `is_odd_minute_task()`

Determines whether a task was created during an odd-numbered minute.

### `completion_window_valid()`

Validates the completion deadline for odd-minute tasks.

### `hidden_rule_allows_completion()`

Runs deterministic hidden completion logic.

### `complete_task()`

Coordinates all completion rules and updates the task when every required condition passes.

---

## 11. Completion Flow

```text
User clicks "Complete Task"
        |
        v
Is task already completed?
        |
        +-- Yes -> Reject
        |
        v
Is task currently locked?
        |
        +-- Yes -> Reject
        |
        v
Is High-priority dependency satisfied?
        |
        +-- No -> Reject
        |
        v
Is odd-minute completion window valid?
        |
        +-- No -> Reject
        |
        v
Does hidden rule allow completion?
        |
        +-- No -> Reject
        |
        v
Set completed_at
        |
        v
Task Completed
```

---

## 12. Database Transactions

Task creation and completion operations use:

```python
@transaction.atomic
```

Task completion additionally retrieves the task using:

```python
select_for_update()
```

This keeps task completion inside a controlled transaction.

---

## 13. Installation

### Prerequisites

```text
Python
pip
venv
```

---

## 14. Local Setup

Enter the project directory:

```bash
cd smart-task-board
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it on macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Apply migrations:

```bash
python manage.py migrate
```

Run Django system checks:

```bash
python manage.py check
```

Start the development server:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

## 15. Django Admin

Create a superuser:

```bash
python manage.py createsuperuser
```

Start the application:

```bash
python manage.py runserver
```

Admin interface:

```text
http://127.0.0.1:8000/admin/
```

---

## 16. Running Tests

Run the complete test suite:

```bash
python manage.py test
```

Tests cover the application's business rules and task behavior.

---

## 17. Security Considerations

The application uses Django's built-in protections, including:

* CSRF protection
* ORM parameterization
* Form validation
* Server-side business-rule enforcement
* POST requests for state-changing operations

Task completion cannot be performed using a normal GET request.

All important validation occurs on the backend rather than relying on frontend JavaScript.

---

## 18. Design Decisions

### Why SQLite?

SQLite was selected because:

* The project is a small coding assignment.
* No external database server is required.
* The reviewer can run the application immediately.

### Why Django Templates?

A separate frontend framework would unnecessarily increase setup complexity.

Django templates provide everything required for:

* Task creation
* Task display
* Completion forms
* Messages
* Responsive UI

### Why no Celery?

The five-minute lock does not require a background process.

The application compares the current time with:

```text
locked_until
```

### Why no separate status field?

`Pending`, `Locked`, and `Completed` are derived values.

Storing status separately could create inconsistent data.

---

## 19. Assumptions

The following interpretations were made where the assignment specification was ambiguous:

1. The High priority requirement applies globally across tasks.
2. At least one previously completed Low task satisfies the High priority dependency.
3. Rapid task locking uses a rolling two-minute window.
4. Odd-minute tasks must complete within their estimated time.
5. Even-minute tasks do not receive that deadline.
6. Hidden completion behavior is deterministic rather than random.
7. Locking expires automatically based on timestamp comparison.

---

## 20. Submission

This project is intended to be submitted through Google Drive as requested in the assignment instructions.

The source code is not intended to be published on external public code-hosting platforms as part of this submission.

---

## Author

**Ashwani Kumar**

Python / Django Backend Developer
