"""Load demo data: python seed.py  →  login demo@hiretrack.ai / demo1234"""

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Application, Interview, Match, Resume, Stage, User
from app.security import hash_password

EMAIL, PASSWORD = "demo@hiretrack.ai", "demo1234"

RESUME = """Alex Rivera — Full-Stack Software Engineer
alex.rivera@example.com · github.com/alexr

EXPERIENCE
Software Engineer, Brightline Payments (2022–present)
- Built and maintained REST APIs in Python (FastAPI) serving 2M requests/day
- Migrated the merchant dashboard from jQuery to React, cutting page load time by 40%
- Designed PostgreSQL schemas and optimised slow queries; added Redis caching
- Containerised services with Docker and set up GitHub Actions CI/CD

Junior Developer, Campus Labs (2020–2022)
- Developed internal tools in JavaScript and Node.js
- Wrote unit tests with pytest and Jest, raising coverage from 35% to 80%

SKILLS
Python, FastAPI, JavaScript, TypeScript, React, Node.js, PostgreSQL, Redis, Docker, Git, AWS (EC2, S3)

EDUCATION
B.Tech in Computer Science, 2020
"""

JD = """Northwind Labs — Senior Backend Engineer
We're looking for a backend engineer to scale our data platform.
Requirements: 4+ years Python, FastAPI or Django, PostgreSQL, Docker, Kubernetes, AWS.
Experience with Kafka and Terraform is a strong plus. You'll mentor junior engineers."""


def main():
    init_db()
    db = SessionLocal()
    existing = db.scalar(select(User).where(User.email == EMAIL))
    if existing:
        db.delete(existing)  # cascades to all demo rows
        db.commit()

    user = User(name="Alex Rivera", email=EMAIL, password_hash=hash_password(PASSWORD))
    db.add(user)
    db.flush()
    resume = Resume(user_id=user.id, content=RESUME, is_active=True)
    db.add(resume)
    db.flush()
    match = Match(
        user_id=user.id, resume_id=resume.id, job_description=JD, fit_score=72,
        missing_skills=json.dumps(["Kubernetes", "Kafka", "Terraform", "Mentoring"]),
        suggested_bullets=json.dumps([
            "Built and scaled Python/FastAPI services handling 2M requests/day on AWS, with Dockerised deployments via CI/CD",
            "Designed and tuned PostgreSQL schemas and Redis caching, reducing p95 API latency by [X%]",
            "Raised test coverage from 35% to 80% and coached teammates on testing practices",
        ]),
    )
    db.add(match)
    db.flush()

    today = date.today()
    now = datetime.now().replace(second=0, microsecond=0)
    rows = [
        ("Northwind Labs", "Senior Backend Engineer", Stage.WISHLIST, None, "https://example.com/northwind", match.id),
        ("Contoso", "Frontend Engineer (React)", Stage.WISHLIST, None, None, None),
        ("Globex", "Software Engineer II", Stage.APPLIED, today - timedelta(days=12), "https://example.com/globex", None),
        ("Initech", "Python Developer", Stage.APPLIED, today - timedelta(days=5), None, None),
        ("Umbrella Health", "Full-Stack Engineer", Stage.APPLIED, today - timedelta(days=2), None, None),
        ("Stark Industries", "Platform Engineer", Stage.INTERVIEW, today - timedelta(days=15), None, None),
        ("Wayne Enterprises", "Backend Engineer", Stage.INTERVIEW, today - timedelta(days=9), None, None),
        ("Hooli", "Software Engineer", Stage.OFFER, today - timedelta(days=30), None, None),
        ("Vandelay Imports", "Junior Data Engineer", Stage.REJECTED, today - timedelta(days=20), None, None),
    ]
    apps = {}
    for company, role, stage, applied, url, match_id in rows:
        a = Application(user_id=user.id, company=company, role=role, stage=stage,
                        applied_date=applied, job_url=url, match_id=match_id)
        db.add(a)
        apps[company] = a
    db.flush()
    db.add_all([
        Interview(application_id=apps["Stark Industries"].id, scheduled_at=now + timedelta(days=1, hours=2), round="Technical"),
        Interview(application_id=apps["Wayne Enterprises"].id, scheduled_at=now + timedelta(hours=4), round="HR"),
        Interview(application_id=apps["Hooli"].id, scheduled_at=now - timedelta(days=10), round="Final"),
    ])
    db.commit()
    print(f"Seeded demo account → {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
