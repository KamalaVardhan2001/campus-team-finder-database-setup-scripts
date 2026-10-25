\# Campus Team Finder — Database Setup Scripts



\## Overview



This repository contains the scripts and schema definitions used to rebuild and populate the Neo4j graph database for the Campus Team Finder project, developed as part of the Database Modelling and Design coursework.



\## Repository Contents



| File or folder | Description |

|---|---|

| `seed\_real\_data.py` | Python script for downloading source data and populating the Neo4j database. |

| `schema.cypher` | Cypher statements defining database constraints and indexes. |

| `README\_SETUP.md` | Detailed instructions for configuring, installing dependencies, and running the database seeding script. |

| `data/` | Cached source data used by the setup process, where applicable. |



\## Technology Stack



\- \*\*Database:\*\* Neo4j Aura

\- \*\*Query language:\*\* Cypher

\- \*\*Programming language:\*\* Python

\- \*\*Driver:\*\* Neo4j Python Driver



\## Getting Started



1\. Clone or download this repository.

2\. Follow the instructions in \[`README\_SETUP.md`](README\_SETUP.md).

3\. Configure your Neo4j connection details in a local `.env` file.

4\. Install the required Python dependencies.

5\. Run `seed\_real\_data.py` to populate an empty Neo4j database.



\*\*Important:\*\* The seeding script is designed to stop if the target database already contains nodes. Use an empty database for rebuilding.



\## Data and Security Notes



\- Student profiles use pseudonymous names and placeholder emails; they are not verified campus identities.

\- Project records are derived from public GitHub repository metadata.

\- Application records and some project membership assignments are synthetic demo data.

\- Review source-data licensing and attribution requirements before redistributing datasets.

\- Never commit `.env`, database passwords, or access tokens.



\## Project Information



\*\*Project:\*\* Campus Team Finder  

\*\*Course:\*\* Database Modelling and Design  

\*\*Database:\*\* Neo4j

