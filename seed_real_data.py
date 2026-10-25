"""Populate Campus Team Finder with real public dataset-derived content.

Data sources:
- Stack Overflow Developer Survey 2024 (downloaded from its official CDN).
  Respondents are represented as pseudonymous demo Student nodes. Names and
  emails are generated placeholders; no survey respondent identity is claimed.
- Public GitHub repository metadata from the GitHub Search API.
- Application records and project ownership/member links are synthetic demo data
  because the public sources do not link survey respondents to GitHub projects.

Run only against a NEW, EMPTY Neo4j database. This script refuses to seed if
any nodes already exist.
"""
from __future__ import annotations

import csv
import io
import json
import os
import random
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=False)

URI = os.getenv("NEO4J_URI", "").strip()
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j").strip()
PASSWORD = os.getenv("NEO4J_PASSWORD", "")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"

# The old Stack Overflow CDN ZIP URL now returns HTTP 404. The official
# StackExchange/Survey archive hosts the 2024 CSV through Git LFS instead.
SURVEY_CSV_URL = (
    "https://media.githubusercontent.com/media/StackExchange/Survey/"
    "refs/heads/main/packages/archive/2024/results.csv"
)
SURVEY_CSV_PATH = DATA_DIR / "survey_results_public.csv"
STUDENT_COUNT = 305
PROJECT_COUNT = 153
APPLICATION_COUNT = 302
SKILL_COUNT = 70
RANDOM_SEED = 20261025

TECH_COLUMNS = [
    "LanguageHaveWorkedWith",
    "DatabaseHaveWorkedWith",
    "PlatformHaveWorkedWith",
    "WebframeHaveWorkedWith",
    "EmbeddedHaveWorkedWith",
    "MiscTechHaveWorkedWith",
    "ToolsTechHaveWorkedWith",
    "NEWCollabToolsHaveWorkedWith",
]


def http_get(url: str, *, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    request_headers = {"User-Agent": "CampusTeamFinder-educational-demo/1.0"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} while downloading {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download {url}: {exc.reason}") from exc


def download_to_path(url: str, destination: Path, *, timeout: int = 180) -> None:
    """Stream a large public CSV to disk instead of holding it all in memory."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CampusTeamFinder-educational-demo/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
    except urllib.error.HTTPError as exc:
        destination.unlink(missing_ok=True)
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} while downloading {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download {url}: {exc.reason}") from exc


def get_survey_rows() -> list[dict[str, str]]:
    if not SURVEY_CSV_PATH.exists():
        print("Downloading the official Stack Overflow Developer Survey 2024 CSV from GitHub...")
        print("This file is large; the first download may take a few minutes.")
        download_to_path(SURVEY_CSV_URL, SURVEY_CSV_PATH, timeout=300)

    rows: list[dict[str, str]] = []
    try:
        with SURVEY_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as text_file:
            reader = csv.DictReader(text_file)
            if not reader.fieldnames:
                raise RuntimeError("The downloaded survey CSV has no header row.")
            missing = [column for column in TECH_COLUMNS if column not in reader.fieldnames]
            if len(missing) > 4:
                raise RuntimeError(
                    "Unexpected survey schema; technology columns missing: " + ", ".join(missing)
                )
            for row in reader:
                technologies = []
                for column in TECH_COLUMNS:
                    technologies.extend(split_multi(row.get(column, "")))
                if technologies:
                    row["_technologies"] = technologies
                    rows.append(row)
    except UnicodeDecodeError as exc:
        SURVEY_CSV_PATH.unlink(missing_ok=True)
        raise RuntimeError(
            "The downloaded survey file is not readable as UTF-8 CSV. Delete the data file and retry."
        ) from exc

    if len(rows) < STUDENT_COUNT:
        raise RuntimeError(
            f"Only {len(rows)} usable survey records were found; need {STUDENT_COUNT}. "
            "Check that the official CSV downloaded completely."
        )
    return rows


def split_multi(value: str | None) -> list[str]:
    if not value or value.strip().lower() in {"", "nan", "none"}:
        return []
    return [item.strip() for item in value.split(";") if item.strip() and item.strip().lower() != "nan"]


def get_github_repositories() -> list[dict]:
    """Fetch public repository metadata. Uses unauthenticated GitHub search API."""
    repos: list[dict] = []
    seen: set[str] = set()
    queries = ["stars:>20 fork:false", "stars:>5 fork:false"]
    for query in queries:
        for page in (1, 2):
            params = urllib.parse.urlencode({
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
                "page": page,
            })
            url = "https://api.github.com/search/repositories?" + params
            try:
                github_headers = {"Accept": "application/vnd.github+json"}
                github_token = os.getenv("GITHUB_TOKEN", "").strip()
                if github_token:
                    github_headers["Authorization"] = f"Bearer {github_token}"
                payload = json.loads(http_get(url, headers=github_headers, timeout=30))
            except RuntimeError as exc:
                if repos:
                    print(f"Warning: GitHub search could not fetch another page ({exc}). Continuing with {len(repos)} repositories.")
                    break
                raise RuntimeError(
                    "Could not fetch public GitHub repositories. Check internet access and retry. "
                    "GitHub's unauthenticated search API can impose rate limits. Details: " + str(exc)
                ) from exc
            for repo in payload.get("items", []):
                full_name = repo.get("full_name")
                if full_name and full_name.lower() not in seen:
                    seen.add(full_name.lower())
                    repos.append(repo)
                    if len(repos) >= PROJECT_COUNT:
                        return repos[:PROJECT_COUNT]
            # GitHub's search API has a stricter rate limit than ordinary API calls.
            time.sleep(2)
    if len(repos) < PROJECT_COUNT:
        raise RuntimeError(
            f"GitHub returned only {len(repos)} distinct repositories; {PROJECT_COUNT} are required. "
            "Wait a minute and run the script again, or set a GitHub token in GITHUB_TOKEN to increase API limits."
        )
    return repos[:PROJECT_COUNT]


def role_department(dev_type: str, main_branch: str) -> str:
    text = f"{dev_type}; {main_branch}".lower()
    if any(x in text for x in ("data scientist", "machine learning", "ai", "academic researcher")):
        return "Data Science / AI"
    if any(x in text for x in ("devops", "cloud", "site reliability", "system administrator", "security")):
        return "Infrastructure / Cloud / Security"
    if any(x in text for x in ("student", "learning to code")):
        return "Student / Learning to Code"
    if any(x in text for x in ("designer", "ux", "ui")):
        return "Design / UX"
    if dev_type.strip():
        return "Software Development"
    return "Other Developer"


def education_band(ed_level: str) -> str:
    value = (ed_level or "").lower()
    if not value:
        return "Not specified"
    if any(x in value for x in ("master", "doctoral", "professional degree")):
        return "Postgraduate"
    if any(x in value for x in ("bachelor", "associate", "college/university")):
        return "Undergraduate / College"
    if any(x in value for x in ("secondary", "primary", "school")):
        return "School"
    return "Other / Not specified"


def choose_top_skills(survey_rows: list[dict[str, str]], repos: list[dict]) -> list[str]:
    counts: Counter[str] = Counter()
    for row in survey_rows:
        counts.update(set(row.get("_technologies", [])))
    # Include actual GitHub primary languages in the candidate pool, then keep the
    # 70 most frequent survey technologies. GitHub languages that match those
    # canonical names can be linked to projects.
    for repo in repos:
        language = repo.get("language")
        if language:
            counts[language] += 1
    ranked = [name for name, _ in counts.most_common()]
    # Stable preference for meaningful names; the real survey provides far more than 70.
    skills = ranked[:SKILL_COUNT]
    if len(skills) < SKILL_COUNT:
        raise RuntimeError(f"Only {len(skills)} distinct skills found; expected at least {SKILL_COUNT}.")
    return skills


def build_students(survey_rows: list[dict[str, str]], skills: list[str]) -> list[dict]:
    randomizer = random.Random(RANDOM_SEED)
    candidates = [row for row in survey_rows if row.get("_technologies")]
    # Sample from actual respondent rows, but don't store names, emails, response IDs,
    # salary, country, or any other potentially identifying fields.
    chosen = randomizer.sample(candidates, STUDENT_COUNT)
    skill_lookup = {skill.lower(): skill for skill in skills}
    students = []
    for index, row in enumerate(chosen, start=1):
        technologies = []
        for raw in row.get("_technologies", []):
            canonical = skill_lookup.get(raw.lower())
            if canonical and canonical not in technologies:
                technologies.append(canonical)
        if not technologies:
            technologies = [skills[(index * 7) % len(skills)]]
        dev_type = row.get("DevType", "") or ""
        main_branch = row.get("MainBranch", "") or ""
        ed_level = row.get("EdLevel", "") or ""
        display_skills = ", ".join(technologies[:5])
        students.append({
            "studentId": f"S{index:03d}",
            "name": f"Developer Profile {index:03d}",
            "email": f"developer{index:03d}@example.edu",
            "department": role_department(dev_type, main_branch),
            "year": education_band(ed_level),
            "bio": f"Pseudonymous profile derived from Stack Overflow Developer Survey 2024. Reported technologies include {display_skills}.",
            "skills": technologies,
        })
    return students


def canonical_skill(text: str, skill_lookup: dict[str, str]) -> str | None:
    normalized = (text or "").strip().replace("-", " ").replace("_", " ").lower()
    if normalized in skill_lookup:
        return skill_lookup[normalized]
    # Common naming aliases between GitHub languages/topics and survey options.
    aliases = {
        "c#": "c#", "c++": "c++", "jupyter notebook": "jupyter notebook",
        "machine-learning": "machine learning", "reactjs": "react", "nodejs": "node.js",
        "vuejs": "vue.js", "nextjs": "next.js", "typescript": "typescript",
    }
    normalized = aliases.get(normalized, normalized)
    return skill_lookup.get(normalized)


def build_projects(repos: list[dict], students: list[dict], skills: list[str]) -> list[dict]:
    randomizer = random.Random(RANDOM_SEED + 1)
    skill_lookup = {skill.lower(): skill for skill in skills}
    projects = []
    for index, repo in enumerate(repos[:PROJECT_COUNT], start=1):
        owner = randomizer.choice(students)
        language = repo.get("language") or ""
        topics = repo.get("topics") or []
        required = []
        for candidate in [language, *topics]:
            skill = canonical_skill(str(candidate), skill_lookup)
            if skill and skill not in required:
                required.append(skill)
        if not required:
            required = [skills[index % len(skills)]]
        description = (repo.get("description") or "").strip()
        if not description:
            description = f"Public open-source GitHub repository: {repo.get('full_name', repo.get('name', 'repository'))}."
        # Keep within the existing Project schema; source URLs and stars are not added
        # as properties because the user's backend schema doesn't use those fields.
        created = (repo.get("created_at") or date.today().isoformat())[:10]
        try:
            datetime.strptime(created, "%Y-%m-%d")
        except ValueError:
            created = date.today().isoformat()
        category = (topics[0].replace("-", " ").title() if topics else (language or "Open Source"))[:100]
        projects.append({
            "projectId": f"GH{index:04d}",
            "title": (repo.get("name") or f"Open Source Project {index}")[:200],
            "summary": description[:1000],
            "category": category,
            "createdAt": created,
            "maxMembers": 5,
            "status": "archived" if repo.get("archived") else "open",
            "ownerId": owner["studentId"],
            "requiredSkills": required,
        })
    return projects


def build_applications(students: list[dict], projects: list[dict]) -> list[dict]:
    randomizer = random.Random(RANDOM_SEED + 2)
    used_pairs: set[tuple[str, str]] = set()
    rows = []
    for index in range(1, APPLICATION_COUNT + 1):
        project = projects[(index - 1) % len(projects)]
        owner_id = project["ownerId"]
        candidates = [s for s in students if s["studentId"] != owner_id and (s["studentId"], project["projectId"]) not in used_pairs]
        if not candidates:
            candidates = [s for s in students if s["studentId"] != owner_id]
        student = randomizer.choice(candidates)
        used_pairs.add((student["studentId"], project["projectId"]))
        status = "accepted" if index % 7 == 0 else ("rejected" if index % 5 == 0 else ("withdrawn" if index % 11 == 0 else "pending"))
        applied = date.today() - timedelta(days=randomizer.randint(0, 250))
        rows.append({
            "applicationId": f"A{index:03d}",
            "appliedAt": applied.isoformat(),
            "status": status,
            "fullName": student["name"],
            "email": student["email"],
            "applicantId": student["studentId"],
            "projectId": project["projectId"],
        })
    return rows


def main() -> None:
    if not URI or not USERNAME or not PASSWORD:
        raise SystemExit("Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD in this folder's .env file first.")

    print("Source: Stack Overflow Developer Survey 2024 + public GitHub repository metadata")
    survey_rows = get_survey_rows()
    print(f"Loaded {len(survey_rows):,} survey responses with reported technologies.")
    repos = get_github_repositories()
    print(f"Loaded {len(repos)} public GitHub repositories.")
    skills = choose_top_skills(survey_rows, repos)
    students = build_students(survey_rows, skills)
    projects = build_projects(repos, students, skills)
    applications = build_applications(students, projects)

    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
    try:
        driver.verify_connectivity()
        with driver.session(database=DATABASE) as session:
            existing = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
            if existing:
                raise SystemExit(
                    f"Refusing to seed: the database already contains {existing} nodes. "
                    "Use a fresh, empty Aura database to avoid duplicates or data loss."
                )

            for statement in [
                "CREATE CONSTRAINT student_id_unique IF NOT EXISTS FOR (s:Student) REQUIRE s.studentId IS UNIQUE",
                "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.projectId IS UNIQUE",
                "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS FOR (sk:Skill) REQUIRE sk.name IS UNIQUE",
                "CREATE CONSTRAINT application_id_unique IF NOT EXISTS FOR (a:Application) REQUIRE a.applicationId IS UNIQUE",
                "CREATE INDEX student_email_index IF NOT EXISTS FOR (s:Student) ON (s.email)",
                "CREATE INDEX project_status_index IF NOT EXISTS FOR (p:Project) ON (p.status)",
                "CREATE INDEX application_status_index IF NOT EXISTS FOR (a:Application) ON (a.status)",
            ]:
                session.run(statement).consume()

            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                CREATE (:Student {studentId: row.studentId, name: row.name, email: row.email,
                    department: row.department, year: row.year, bio: row.bio})
            """, rows=students).consume())
            session.execute_write(lambda tx: tx.run(
                "UNWIND $rows AS row CREATE (:Skill {name: row.name})",
                rows=[{"name": name} for name in skills],
            ).consume())
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MATCH (owner:Student {studentId: row.ownerId})
                CREATE (p:Project {projectId: row.projectId, title: row.title, summary: row.summary,
                    category: row.category, createdAt: date(row.createdAt),
                    maxMembers: row.maxMembers, status: row.status})
                CREATE (owner)-[:OWNS]->(p)
                MERGE (owner)-[:MEMBER_OF]->(p)
            """, rows=projects).consume())
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MATCH (p:Project {projectId: row.projectId})
                UNWIND row.requiredSkills AS skillName
                MATCH (sk:Skill {name: skillName})
                MERGE (p)-[:REQUIRES]->(sk)
            """, rows=projects).consume())

            student_skill_pairs = [
                {"studentId": student["studentId"], "skillName": skill}
                for student in students for skill in student["skills"]
                if skill in set(skills)
            ]
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MATCH (s:Student {studentId: row.studentId}), (sk:Skill {name: row.skillName})
                MERGE (s)-[:HAS_SKILL]->(sk)
            """, rows=student_skill_pairs).consume())
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MATCH (s:Student {studentId: row.applicantId})
                MATCH (p:Project {projectId: row.projectId})
                CREATE (a:Application {applicationId: row.applicationId, appliedAt: date(row.appliedAt),
                    status: row.status, fullName: row.fullName, email: row.email})
                CREATE (s)-[:SUBMITTED]->(a)
                CREATE (a)-[:FOR_PROJECT]->(p)
                WITH s, p, row
                FOREACH (_ IN CASE WHEN row.status = 'accepted' THEN [1] ELSE [] END |
                    MERGE (s)-[:MEMBER_OF]->(p))
            """, rows=applications).consume())

            node_counts = session.run("""
                MATCH (n) WITH labels(n) AS labels, count(*) AS count
                RETURN labels, count ORDER BY labels
            """).data()
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            print("\nDatabase seeded successfully.")
            print("Node counts:")
            for row in node_counts:
                print(f"  {row['labels']}: {row['count']}")
            print(f"Relationships: {rel_count}")
            print("Demo identity header: X-Student-Id: S001")
            print("\nData provenance:")
            print("  - Student profile attributes/skills: Stack Overflow Developer Survey 2024 (anonymized, pseudonymous display records).")
            print("  - Projects: public GitHub repository metadata.")
            print("  - Applications and OWNS/MEMBER_OF assignment of GitHub repositories: synthetic demo data.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
