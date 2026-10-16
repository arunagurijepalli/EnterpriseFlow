from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import sqlite3
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parents[1]
from company.store import DB_PATH as CONFIGURED_DB_PATH
DB_PATH = CONFIGURED_DB_PATH


# ============================================================
# HELPERS
# ============================================================

@contextmanager
def connect():
    """Yield a configured portfolio connection and always close it."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now():
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# TABLES
# ============================================================

def ensure_employee_portfolio_tables():
    with connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_projects (
                project_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                role_in_project TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                status TEXT DEFAULT 'in_progress',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_milestones (
                milestone_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                project_id INTEGER NOT NULL,
                milestone_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                due_date TEXT DEFAULT '',
                completion_percent REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                completed_date TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_achievements (
                achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                achievement_date TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_participations (
                participation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                participation_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                participation_date TEXT DEFAULT '',
                result TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_performance (
                performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                review_period TEXT NOT NULL,
                rating REAL DEFAULT 0,
                goals TEXT DEFAULT '',
                achievements_summary TEXT DEFAULT '',
                manager_feedback TEXT DEFAULT '',
                status TEXT DEFAULT 'completed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Additive migration for structured feedback metadata; preserve legacy reviews.
        performance_columns = {row[1] for row in conn.execute("PRAGMA table_info(employee_performance)").fetchall()}
        for column, definition in {
            "strengths": "TEXT NOT NULL DEFAULT ''",
            "areas_for_improvement": "TEXT NOT NULL DEFAULT ''",
            "reviewer_user_id": "TEXT NOT NULL DEFAULT ''",
            "feedback_comments": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in performance_columns:
                conn.execute(f"ALTER TABLE employee_performance ADD COLUMN {column} {definition}")

        # Project files are stored as company- and employee-scoped uploads.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_files (
                file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                project_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                uploaded_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_submissions (
                submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                submitted_by_user_id TEXT NOT NULL,
                project_id INTEGER NOT NULL,
                submission_note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'submitted',
                admin_feedback TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_by TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_files_company_project ON project_files(company_id, project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_submissions_company_status ON project_submissions(company_id, status, created_at)")

        conn.commit()


# ============================================================
# PROJECTS
# ============================================================

def create_project(
    company_id,
    employee_id,
    project_name,
    description="",
    role_in_project="",
    start_date="",
    end_date="",
    status="in_progress",
):
    ensure_employee_portfolio_tables()

    if not project_name.strip():
        return {
            "status": "error",
            "message": "Project name is required.",
        }

    timestamp = now()

    with connect() as conn:
        cursor = conn.execute("""
            INSERT INTO employee_projects (
                company_id,
                employee_id,
                project_name,
                description,
                role_in_project,
                start_date,
                end_date,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            employee_id,
            project_name.strip(),
            description.strip(),
            role_in_project.strip(),
            start_date.strip(),
            end_date.strip(),
            status.strip().lower(),
            timestamp,
            timestamp,
        ))

        conn.commit()

        return {
            "status": "success",
            "project_id": cursor.lastrowid,
            "message": "Project saved successfully.",
        }


def get_project(company_id, employee_id, project_id):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        row = conn.execute("""
            SELECT *
            FROM employee_projects
            WHERE project_id = ?
              AND company_id = ?
              AND employee_id = ?
        """, (
            project_id,
            company_id,
            employee_id,
        )).fetchone()

    return dict(row) if row else None


def update_project(
    company_id,
    employee_id,
    project_id,
    project_name,
    description="",
    role_in_project="",
    start_date="",
    end_date="",
    status="in_progress",
):
    ensure_employee_portfolio_tables()

    if not project_name.strip():
        return {
            "status": "error",
            "message": "Project name is required.",
        }

    timestamp = now()

    with connect() as conn:
        cursor = conn.execute("""
            UPDATE employee_projects
            SET
                project_name = ?,
                description = ?,
                role_in_project = ?,
                start_date = ?,
                end_date = ?,
                status = ?,
                updated_at = ?
            WHERE project_id = ?
              AND company_id = ?
              AND employee_id = ?
        """, (
            project_name.strip(),
            description.strip(),
            role_in_project.strip(),
            start_date.strip(),
            end_date.strip(),
            status.strip().lower(),
            timestamp,
            project_id,
            company_id,
            employee_id,
        ))

        conn.commit()

        if cursor.rowcount == 0:
            return {
                "status": "error",
                "message": "Project not found for this employee.",
            }

    return {
        "status": "success",
        "message": "Project updated successfully.",
        "project_id": project_id,
    }


def list_projects(company_id, employee_id):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        rows = conn.execute("""
            SELECT *
            FROM employee_projects
            WHERE company_id = ?
              AND employee_id = ?
            ORDER BY created_at DESC
        """, (
            company_id,
            employee_id,
        )).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# MILESTONES
# ============================================================

def create_milestone(
    company_id,
    employee_id,
    project_id,
    milestone_name,
    description="",
    due_date="",
    completion_percent=0,
    status="pending",
    completed_date="",
):
    ensure_employee_portfolio_tables()

    if not milestone_name.strip():
        return {
            "status": "error",
            "message": "Milestone name is required.",
        }

    with connect() as conn:

        project = conn.execute("""
            SELECT project_id
            FROM employee_projects
            WHERE project_id = ?
              AND company_id = ?
              AND employee_id = ?
        """, (
            project_id,
            company_id,
            employee_id,
        )).fetchone()

        if not project:
            return {
                "status": "error",
                "message": "Project not found for this employee.",
            }

        timestamp = now()

        cursor = conn.execute("""
            INSERT INTO project_milestones (
                company_id,
                employee_id,
                project_id,
                milestone_name,
                description,
                due_date,
                completion_percent,
                status,
                completed_date,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            employee_id,
            project_id,
            milestone_name.strip(),
            description.strip(),
            due_date.strip(),
            max(0, min(100, float(completion_percent))),
            status.strip().lower(),
            completed_date.strip(),
            timestamp,
            timestamp,
        ))

        conn.commit()

        return {
            "status": "success",
            "milestone_id": cursor.lastrowid,
            "message": "Milestone saved successfully.",
        }


def list_milestones(
    company_id,
    employee_id,
    project_id=None,
):
    ensure_employee_portfolio_tables()

    query = """
        SELECT *
        FROM project_milestones
        WHERE company_id = ?
          AND employee_id = ?
    """

    params = [
        company_id,
        employee_id,
    ]

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    query += " ORDER BY created_at DESC"

    with connect() as conn:
        rows = conn.execute(
            query,
            params,
        ).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# ACHIEVEMENTS
# ============================================================

def create_achievement(
    company_id,
    employee_id,
    title,
    description="",
    category="",
    achievement_date="",
):
    ensure_employee_portfolio_tables()

    if not title.strip():
        return {
            "status": "error",
            "message": "Achievement title is required.",
        }

    timestamp = now()

    with connect() as conn:
        cursor = conn.execute("""
            INSERT INTO employee_achievements (
                company_id,
                employee_id,
                title,
                description,
                category,
                achievement_date,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            employee_id,
            title.strip(),
            description.strip(),
            category.strip(),
            achievement_date.strip(),
            timestamp,
            timestamp,
        ))

        conn.commit()

        return {
            "status": "success",
            "achievement_id": cursor.lastrowid,
            "message": "Achievement saved successfully.",
        }


def list_achievements(company_id, employee_id):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        rows = conn.execute("""
            SELECT *
            FROM employee_achievements
            WHERE company_id = ?
              AND employee_id = ?
            ORDER BY achievement_date DESC, created_at DESC
        """, (
            company_id,
            employee_id,
        )).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# PARTICIPATIONS
# ============================================================

def create_participation(
    company_id,
    employee_id,
    participation_type,
    title,
    description="",
    participation_date="",
    result="",
):
    ensure_employee_portfolio_tables()

    if not participation_type.strip():
        return {
            "status": "error",
            "message": "Participation type is required.",
        }

    if not title.strip():
        return {
            "status": "error",
            "message": "Participation title is required.",
        }

    timestamp = now()

    with connect() as conn:
        cursor = conn.execute("""
            INSERT INTO employee_participations (
                company_id,
                employee_id,
                participation_type,
                title,
                description,
                participation_date,
                result,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            employee_id,
            participation_type.strip(),
            title.strip(),
            description.strip(),
            participation_date.strip(),
            result.strip(),
            timestamp,
            timestamp,
        ))

        conn.commit()

        return {
            "status": "success",
            "participation_id": cursor.lastrowid,
            "message": "Participation saved successfully.",
        }


def list_participations(company_id, employee_id):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        rows = conn.execute("""
            SELECT *
            FROM employee_participations
            WHERE company_id = ?
              AND employee_id = ?
            ORDER BY participation_date DESC, created_at DESC
        """, (
            company_id,
            employee_id,
        )).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# PERFORMANCE
# ============================================================

def create_performance(
    company_id,
    employee_id,
    review_period,
    rating,
    goals="",
    achievements_summary="",
    manager_feedback="",
    status="completed",
    strengths="",
    areas_for_improvement="",
    reviewer_user_id="",
    feedback_comments="",
):
    ensure_employee_portfolio_tables()

    # Normalize the period to prevent accidental leading punctuation.
    cleaned_period = str(review_period or "").strip()
    cleaned_period = cleaned_period.lstrip(" \\t\\r\\n:;,-??").strip()
    if not cleaned_period:
        raise ValueError("A valid review period is required.")

    def normalize_period(value):
        return str(value or "").strip().lstrip(
            " \\t\\r\\n:;,-??"
        ).strip().casefold()

    timestamp = now()

    with connect() as conn:
        # Compare existing periods after normalization, including legacy
        # records such as ": October 2026".
        existing = conn.execute(
            """
            SELECT review_period
            FROM employee_performance
            WHERE company_id = ? AND employee_id = ?
            """,
            (company_id, employee_id),
        ).fetchall()

        if any(
            normalize_period(row["review_period"]) ==
            normalize_period(cleaned_period)
            for row in existing
        ):
            raise ValueError(
                "A review already exists for this employee and period. "
                "Edit the existing review instead of creating a duplicate."
            )

        cursor = conn.execute("""
            INSERT INTO employee_performance (
                company_id,
                employee_id,
                review_period,
                rating,
                goals,
                achievements_summary,
                manager_feedback,
                status,
                created_at,
                updated_at,
                strengths,
                areas_for_improvement,
                reviewer_user_id,
                feedback_comments
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            employee_id,
            cleaned_period,
            float(rating),
            goals.strip(),
            achievements_summary.strip(),
            manager_feedback.strip(),
            status.strip().lower(),
            timestamp,
            timestamp,
            str(strengths or "").strip(),
            str(areas_for_improvement or "").strip(),
            str(reviewer_user_id or "").strip(),
            str(feedback_comments or "").strip(),
        ))

        conn.commit()

        return {
            "status": "success",
            "performance_id": cursor.lastrowid,
            "message": "Performance record saved successfully.",
        }


def get_performance(company_id, employee_id):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        rows = conn.execute("""
            SELECT *
            FROM employee_performance
            WHERE company_id = ?
              AND employee_id = ?
            ORDER BY review_period DESC, created_at DESC
        """, (
            company_id,
            employee_id,
        )).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# COMPLETE PORTFOLIO
# ============================================================

def get_employee_portfolio(company_id, employee_id):
    return {
        "employee_id": employee_id,
        "projects": list_projects(
            company_id,
            employee_id,
        ),
        "milestones": list_milestones(
            company_id,
            employee_id,
        ),
        "achievements": list_achievements(
            company_id,
            employee_id,
        ),
        "participations": list_participations(
            company_id,
            employee_id,
        ),
        "performance": get_performance(
            company_id,
            employee_id,
        ),
    }


if __name__ == "__main__":
    ensure_employee_portfolio_tables()
    print("Employee portfolio tables created successfully.")
    print("Projects: READY")
    print("Milestones: READY")
    print("Achievements: READY")
    print("Participations: READY")
    print("Performance: READY")
def create_project_module(
    company_id,
    employee_id,
    project_id,
    module_name,
    description="",
    completion_percent=0,
    status="pending",
):
    ensure_employee_portfolio_tables()

    if not module_name.strip():
        return {
            "status": "error",
            "message": "Module name is required.",
        }

    with connect() as conn:

        project = conn.execute(
            """
            SELECT project_id
            FROM employee_projects
            WHERE project_id = ?
              AND company_id = ?
              AND employee_id = ?
            """,
            (
                project_id,
                company_id,
                employee_id,
            ),
        ).fetchone()

        if not project:
            return {
                "status": "error",
                "message": "Project not found.",
            }

        timestamp = now()

        cursor = conn.execute(
            """
            INSERT INTO project_modules (
                company_id,
                employee_id,
                project_id,
                module_name,
                description,
                completion_percent,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                employee_id,
                project_id,
                module_name.strip(),
                description.strip(),
                max(0, min(100, float(completion_percent))),
                status.strip().lower(),
                timestamp,
                timestamp,
            ),
        )

        conn.commit()

        return {
            "status": "success",
            "module_id": cursor.lastrowid,
            "message": "Project module saved successfully.",
        }


def list_project_modules(
    company_id,
    employee_id,
    project_id,
):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM project_modules
            WHERE company_id = ?
              AND employee_id = ?
              AND project_id = ?
            ORDER BY created_at ASC
            """,
            (
                company_id,
                employee_id,
                project_id,
            ),
        ).fetchall()

    return [dict(row) for row in rows]


def save_project_file(
    company_id,
    employee_id,
    project_id,
    file_name,
    file_data,
):
    ensure_employee_portfolio_tables()

    if not file_name:
        return {
            "status": "error",
            "message": "File name is required.",
        }

    with connect() as conn:

        project = conn.execute(
            """
            SELECT project_id
            FROM employee_projects
            WHERE project_id = ?
              AND company_id = ?
              AND employee_id = ?
            """,
            (
                project_id,
                company_id,
                employee_id,
            ),
        ).fetchone()

        if not project:
            return {
                "status": "error",
                "message": "Project not found.",
            }

    folder = (
        BASE_DIR
        / "data"
        / "project_files"
        / str(company_id)
        / str(employee_id)
        / str(project_id)
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Streamlit's directory uploader returns relative paths. Preserve them
    # safely so the submitted project retains its folder structure.
    raw_name = str(file_name or "").replace("\\", "/")
    relative = PurePosixPath(raw_name)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts) or ":" in raw_name:
        return {"status": "invalid", "message": "Unsafe project file path was rejected."}
    parts = [part for part in relative.parts if part]
    if not parts or len(raw_name) > 240:
        return {"status": "invalid", "message": "Project file name is invalid or too long."}

    folder.mkdir(parents=True, exist_ok=True)
    safe_rel_name = PurePosixPath(*parts).as_posix()
    file_path = folder.joinpath(*parts).resolve()
    try:
        file_path.relative_to(folder.resolve())
    except ValueError:
        return {"status": "invalid", "message": "Unsafe project file path was rejected."}
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if len(file_data or b"") > 50 * 1024 * 1024:
        return {"status": "invalid", "message": "Each project file must be 50 MB or smaller."}
    if file_path.exists():
        stem, suffix = file_path.stem, file_path.suffix
        counter = 2
        while file_path.exists():
            file_path = file_path.with_name(f"{stem}_{counter}{suffix}")
            safe_rel_name = str(PurePosixPath(*parts[:-1]) / file_path.name) if len(parts) > 1 else file_path.name
            counter += 1
    file_path.write_bytes(file_data)

    timestamp = now()

    with connect() as conn:

        cursor = conn.execute(
            """
            INSERT INTO project_files (
                company_id,
                employee_id,
                project_id,
                file_name,
                file_path,
                file_type,
                file_size,
                uploaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                employee_id,
                project_id,
                safe_rel_name,
                str(file_path),
                Path(safe_rel_name).suffix.lower().lstrip("."),
                len(file_data),
                timestamp,
            ),
        )

        conn.commit()

        return {
            "status": "success",
            "file_id": cursor.lastrowid,
            "message": "Project file uploaded successfully.",
        }


def list_project_files(
    company_id,
    employee_id,
    project_id,
):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM project_files
            WHERE company_id = ?
              AND employee_id = ?
              AND project_id = ?
            ORDER BY uploaded_at DESC
            """,
            (
                company_id,
                employee_id,
                project_id,
            ),
        ).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# PROJECT SUBMISSIONS / ADMIN REVIEW
# ============================================================

def create_project_submission(company_id, employee_id, submitted_by_user_id, project_id, submission_note=""):
    ensure_employee_portfolio_tables()
    from company.store import authorize_user
    actor = authorize_user(company_id, submitted_by_user_id)
    if str(actor.get("role") or "").casefold() != "employee":
        return {"status": "forbidden", "message": "Only an employee may submit their project for review."}
    if str(actor.get("employee_id") or "") != str(employee_id):
        return {"status": "forbidden", "message": "You can submit only your own project."}
    with connect() as conn:
        project = conn.execute(
            "SELECT project_id FROM employee_projects WHERE company_id=? AND employee_id=? AND project_id=?",
            (company_id, employee_id, int(project_id)),
        ).fetchone()
        if not project:
            return {"status": "not_found", "message": "Project was not found for this employee."}
        file_count = conn.execute(
            "SELECT COUNT(*) FROM project_files WHERE company_id=? AND employee_id=? AND project_id=?",
            (company_id, employee_id, int(project_id)),
        ).fetchone()[0]
        if not file_count:
            return {"status": "invalid", "message": "Upload at least one project file or folder before submitting it to the administrator."}
        existing = conn.execute(
            "SELECT submission_id FROM project_submissions WHERE company_id=? AND employee_id=? AND project_id=? AND status IN ('submitted','under_review') ORDER BY created_at DESC LIMIT 1",
            (company_id, employee_id, int(project_id)),
        ).fetchone()
        if existing:
            return {"status": "already_submitted", "submission_id": existing["submission_id"], "message": f"This project is already submitted for admin review (submission #{existing['submission_id']})."}
        timestamp = now()
        cursor = conn.execute(
            """INSERT INTO project_submissions
                (company_id,employee_id,submitted_by_user_id,project_id,submission_note,status,created_at,updated_at)
                VALUES (?,?,?,?,?,'submitted',?,?)""",
            (company_id, employee_id, submitted_by_user_id, int(project_id), str(submission_note or "").strip(), timestamp, timestamp),
        )
        conn.commit()
        submission_id = int(cursor.lastrowid)
    return {"status": "success", "submission_id": submission_id, "message": f"Project submitted to the administrator for review (submission #{submission_id})."}


def list_my_project_submissions(company_id, employee_id):
    ensure_employee_portfolio_tables()
    with connect() as conn:
        rows = conn.execute(
            """SELECT s.*, p.project_name, p.description AS project_description,
                      p.start_date, p.end_date, p.status AS project_status,
                      (SELECT COUNT(*) FROM project_files f WHERE f.company_id=s.company_id AND f.employee_id=s.employee_id AND f.project_id=s.project_id) AS file_count
               FROM project_submissions s JOIN employee_projects p
                 ON p.company_id=s.company_id AND p.employee_id=s.employee_id AND p.project_id=s.project_id
               WHERE s.company_id=? AND s.employee_id=? ORDER BY s.created_at DESC""",
            (company_id, employee_id),
        ).fetchall()
    return [dict(row) for row in rows]


def list_project_submissions_for_admin(company_id, admin_user_id, status=None):
    ensure_employee_portfolio_tables()
    from company.store import authorize_user
    authorize_user(company_id, admin_user_id, allowed_roles=["company_admin", "hr_admin"])
    query = """SELECT s.*, p.project_name, p.description AS project_description,
                      p.role_in_project, p.start_date, p.end_date, p.status AS project_status,
                      u.name AS employee_name, u.email AS employee_email,
                      (SELECT COUNT(*) FROM project_files f WHERE f.company_id=s.company_id AND f.employee_id=s.employee_id AND f.project_id=s.project_id) AS file_count
               FROM project_submissions s
               JOIN employee_projects p ON p.company_id=s.company_id AND p.employee_id=s.employee_id AND p.project_id=s.project_id
               LEFT JOIN company_users u ON u.company_id=s.company_id AND u.employee_id=s.employee_id
               WHERE s.company_id=?"""
    params = [company_id]
    if status and str(status).casefold() != "all":
        query += " AND s.status=?"
        params.append(str(status).casefold())
    query += " ORDER BY s.created_at DESC"
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_project_files_for_admin(company_id, admin_user_id, project_id):
    ensure_employee_portfolio_tables()
    from company.store import authorize_user
    authorize_user(company_id, admin_user_id, allowed_roles=["company_admin", "hr_admin"])
    with connect() as conn:
        project = conn.execute("SELECT project_id FROM employee_projects WHERE company_id=? AND project_id=?", (company_id, int(project_id))).fetchone()
        if not project:
            return []
        rows = conn.execute(
            "SELECT * FROM project_files WHERE company_id=? AND project_id=? ORDER BY uploaded_at, file_name",
            (company_id, int(project_id)),
        ).fetchall()
    return [dict(row) for row in rows]


def read_project_file_for_admin(company_id, admin_user_id, file_id):
    from company.store import authorize_user
    authorize_user(company_id, admin_user_id, allowed_roles=["company_admin", "hr_admin"])
    with connect() as conn:
        row = conn.execute("SELECT * FROM project_files WHERE company_id=? AND file_id=?", (company_id, int(file_id))).fetchone()
    if not row:
        return {"status": "not_found", "message": "Project file not found."}
    record = dict(row)
    allowed_root = (BASE_DIR / "data" / "project_files" / str(company_id) / str(record["employee_id"]) / str(record["project_id"])).resolve()
    candidate = Path(record.get("file_path") or "").resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError:
        return {"status": "forbidden", "message": "The stored file path failed the project security check."}
    if not candidate.is_file():
        return {"status": "not_found", "message": "The uploaded project file is no longer available on disk."}
    return {"status": "success", "file_name": str(record.get("file_name") or candidate.name), "file_type": str(record.get("file_type") or ""), "file_size": int(record.get("file_size") or candidate.stat().st_size), "data": candidate.read_bytes()}


def update_project_submission_status(company_id, admin_user_id, submission_id, *, status, admin_feedback=""):
    from company.store import authorize_user
    authorize_user(company_id, admin_user_id, allowed_roles=["company_admin", "hr_admin"])
    ensure_employee_portfolio_tables()
    allowed = {"submitted", "under_review", "needs_information", "approved", "declined"}
    normalized = str(status or "").casefold().strip()
    if normalized not in allowed:
        return {"status": "invalid", "message": "Unsupported project submission status."}
    timestamp = now()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE project_submissions SET status=?, admin_feedback=?, updated_at=?, reviewed_by=?, reviewed_at=? WHERE company_id=? AND submission_id=?",
            (normalized, str(admin_feedback or "").strip(), timestamp, admin_user_id, timestamp, company_id, int(submission_id)),
        )
        conn.commit()
    if not cursor.rowcount:
        return {"status": "not_found", "message": "Project submission not found."}
    return {"status": "success", "message": f"Project submission #{submission_id} updated to {normalized.replace('_', ' ')}."}


# ============================================================
# PROJECT FILE MANAGEMENT
# ============================================================

def get_project_file(
    company_id,
    employee_id,
    project_id,
    file_id,
):
    ensure_employee_portfolio_tables()

    with connect() as conn:
        row = conn.execute("""
            SELECT *
            FROM project_files
            WHERE file_id = ?
              AND company_id = ?
              AND employee_id = ?
              AND project_id = ?
        """, (
            file_id,
            company_id,
            employee_id,
            project_id,
        )).fetchone()

    return dict(row) if row else None


def delete_project_file(
    company_id,
    employee_id,
    project_id,
    file_id,
):
    ensure_employee_portfolio_tables()

    with connect() as conn:

        row = conn.execute("""
            SELECT file_path
            FROM project_files
            WHERE file_id = ?
              AND company_id = ?
              AND employee_id = ?
              AND project_id = ?
        """, (
            file_id,
            company_id,
            employee_id,
            project_id,
        )).fetchone()

        if not row:
            return {
                "status": "error",
                "message": "Project file not found.",
            }

        file_path = row["file_path"]

        conn.execute("""
            DELETE FROM project_files
            WHERE file_id = ?
              AND company_id = ?
              AND employee_id = ?
              AND project_id = ?
        """, (
            file_id,
            company_id,
            employee_id,
            project_id,
        ))

        conn.commit()

    try:
        path_obj = Path(file_path)

        if path_obj.exists():
            path_obj.unlink()

    except Exception as exc:
        return {
            "status": "success",
            "message": (
                "File record deleted, but the physical file "
                f"could not be removed: {exc}"
            ),
            "file_id": file_id,
        }

    return {
        "status": "success",
        "message": "Project file deleted successfully.",
        "file_id": file_id,
    }



def get_my_published_performance(company_id: str, user_id: str):
    """Return only published/completed feedback for the authenticated user's own employee profile."""
    from company.store import authorize_user
    user = authorize_user(company_id, user_id)
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        return []
    return [row for row in get_performance(company_id, employee_id)
            if str(row.get("status") or "").casefold() in {"completed", "published", "submitted"}]
