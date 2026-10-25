# Campus Team Finder — Real-data rebuild

This package populates the existing Campus Team Finder Neo4j schema using public, real-world source data where it is available, and clearly documented synthetic records where no matching public data exists.

## What gets imported

- **305 `Student` nodes:** a sample of actual responses from the Stack Overflow Developer Survey 2024 with reported technologies. The source does not provide respondent names/emails in the anonymized CSV. To fit the existing backend schema, the script uses pseudonymous display names (`Developer Profile 001`, etc.) and placeholder emails (`developer001@example.edu`). These are not real contact details and do not identify respondents. Department/year/bio fields are derived from survey responses.
- **153 `Project` nodes:** public GitHub repository names, descriptions, languages/topics, creation dates, and archived status. Repository URLs, stars, and owner identities are not added as properties because they are not part of the existing backend schema.
- **70 `Skill` nodes:** the most frequently reported technologies from the survey, with GitHub repository languages included in the ranking.
- **302 `Application` nodes:** synthetic demo applications. The public sources do not include Campus Team Finder applications or a reliable link between survey respondents and repositories.
- **Relationships:** `HAS_SKILL` and `REQUIRES` are based on technology data where names match. `OWNS` and owner `MEMBER_OF` links are synthetic assignments to make the existing app's project-owner workflows demoable; they do not represent actual GitHub repository ownership. Accepted synthetic applications also create `MEMBER_OF` links.

The node labels, property names, constraints, indexes, and relationship types are kept compatible with the uploaded Flask backend. The script intentionally refuses to write to a database containing any nodes.

## Data sources and license notes

1. Stack Overflow Developer Survey 2024 public CSV archive: https://survey.stackoverflow.co/2024/ and the official archive linked from the survey. Survey datasets are published under the Open Database License (ODbL); review the terms and attribution/share-alike requirements before redistributing an adapted database.
2. Public GitHub repository metadata: GitHub Search API, https://docs.github.com/en/rest/search/search#search-repositories. Repository content and metadata may be subject to individual repository licenses and GitHub terms. This script imports only public metadata fields into the demo database.

The script downloads the survey archive on first run and caches it in `data/`. It queries the public GitHub Search API at runtime. Internet access is required. GitHub may rate-limit unauthenticated requests. If that happens, wait and retry, or set a personal access token in the `GITHUB_TOKEN` environment variable before running the script. Use a token with no extra permissions; public repository read access is sufficient. Do not paste the token into this chat or commit it to GitHub.

## 1. Create an Aura instance

Create an AuraDB instance at https://console.neo4j.io/. Save its password securely and copy its connection URI (usually `neo4j+s://...`).

## 2. Configure `.env`

Create a file named `.env` in this folder:

```dotenv
NEO4J_URI=neo4j+s://YOUR-AURA-URI
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=YOUR_NEW_AURA_PASSWORD
NEO4J_DATABASE=neo4j
```

Replace the placeholders with your values. Do not share `.env` or commit it to GitHub.

## 3. Install dependencies

In PowerShell, from this folder, activate your existing virtual environment if you created one in this folder, then run:

```powershell
python -m pip install neo4j python-dotenv
```

If your virtual environment was created in another folder, activate that environment first, or create one here:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install neo4j python-dotenv
```

## 4. Seed the database

Run:

```powershell
python seed_real_data.py
```

The first run downloads the Stack Overflow 2024 survey archive and queries GitHub's public repository search. The script checks that the Aura database is empty before creating constraints, indexes, nodes, and relationships. If any nodes already exist, it stops safely. It does not delete or overwrite data.

Expected node counts:

- `Student`: 305
- `Project`: 153
- `Skill`: 70
- `Application`: 302
- Total: 830

These counts are targets; the script will stop if a required source cannot be obtained rather than silently filling missing real records with synthetic student/project data.

## 5. Connect the Flask backend

Set the same `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` in the backend `.env` and Render environment variables. Preserve other existing variables (`JWT_SECRET`, `TOKEN_HOURS`, `FRONTEND_ORIGINS`) as required by your backend. Test `/api/health`; for the demo, `X-Student-Id: S001` is an existing seeded demo profile. This identity header is not secure authentication.

## Notes

- This is a new dataset-based reconstruction, not the exact previous database contents.
- `Student` is the backend's existing label, but these records represent pseudonymous developer-survey profiles, not verified campus students.
- The survey is a self-selected developer survey and should not be described as representative of all students or developers.
- The original backend ZIP included a `.env` file and a `.git` directory. Neither is included in this rebuild package. Never publish secrets; rotate any credentials that were exposed.
