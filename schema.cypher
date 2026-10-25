// Campus Team Finder schema compatible with the existing Flask backend.
// Run against a NEW, EMPTY Neo4j Aura database.

CREATE CONSTRAINT student_id_unique IF NOT EXISTS
FOR (s:Student) REQUIRE s.studentId IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.projectId IS UNIQUE;

CREATE CONSTRAINT skill_name_unique IF NOT EXISTS
FOR (sk:Skill) REQUIRE sk.name IS UNIQUE;

CREATE CONSTRAINT application_id_unique IF NOT EXISTS
FOR (a:Application) REQUIRE a.applicationId IS UNIQUE;

CREATE INDEX student_email_index IF NOT EXISTS
FOR (s:Student) ON (s.email);

CREATE INDEX project_status_index IF NOT EXISTS
FOR (p:Project) ON (p.status);

CREATE INDEX application_status_index IF NOT EXISTS
FOR (a:Application) ON (a.status);
