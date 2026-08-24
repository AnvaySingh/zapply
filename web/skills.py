"""Local, LLM-free skill detection for the web app's job cards.

Computing real per-job Requirements would cost an LLM call per job (quota death on a 10-job
list). Instead we match a curated skill vocabulary against the resume and each job's text —
instant, free, offline, and good enough to show "matches X · missing Y" on a card. Aliases fold
variants (k8s→Kubernetes, postgres→PostgreSQL) to one canonical name.
"""

from __future__ import annotations

import re

# canonical name -> spellings/aliases to look for (matched case-insensitively, whole-token)
SKILLS: dict[str, list[str]] = {
    "Python": ["python"], "Java": ["java"], "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"], "Go": ["golang", "go"], "Rust": ["rust"],
    "C++": ["c++"], "C#": ["c#", ".net", "dotnet"], "Ruby": ["ruby"], "PHP": ["php"],
    "Scala": ["scala"], "Kotlin": ["kotlin"], "Swift": ["swift"], "R": ["r"],
    "SQL": ["sql"], "Bash": ["bash", "shell scripting"],
    "React": ["react", "react.js", "reactjs"], "Angular": ["angular"], "Vue": ["vue", "vue.js"],
    "Next.js": ["next.js", "nextjs"], "HTML": ["html"], "CSS": ["css"], "Tailwind": ["tailwind"],
    "Node.js": ["node.js", "node", "nodejs"], "Django": ["django"], "Flask": ["flask"],
    "FastAPI": ["fastapi"], "Spring": ["spring", "spring boot"], "Rails": ["rails"],
    "GraphQL": ["graphql"], "REST": ["rest", "rest api", "restful"], "gRPC": ["grpc"],
    "PostgreSQL": ["postgresql", "postgres"], "MySQL": ["mysql"], "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"], "Kafka": ["kafka"], "Spark": ["spark"], "Hadoop": ["hadoop"],
    "Snowflake": ["snowflake"], "Airflow": ["airflow"], "Elasticsearch": ["elasticsearch"],
    "DynamoDB": ["dynamodb"], "Cassandra": ["cassandra"],
    "AWS": ["aws", "amazon web services"], "GCP": ["gcp", "google cloud"], "Azure": ["azure"],
    "Kubernetes": ["kubernetes", "k8s"], "Docker": ["docker"], "Terraform": ["terraform"],
    "Ansible": ["ansible"], "Jenkins": ["jenkins"], "CI/CD": ["ci/cd", "cicd"], "Linux": ["linux"],
    "Prometheus": ["prometheus"], "Grafana": ["grafana"],
    "Machine Learning": ["machine learning"], "Deep Learning": ["deep learning"],
    "PyTorch": ["pytorch"], "TensorFlow": ["tensorflow"], "scikit-learn": ["scikit-learn", "sklearn"],
    "Pandas": ["pandas"], "NumPy": ["numpy"], "NLP": ["nlp", "natural language processing"],
    "LLM": ["llm", "large language model"], "Computer Vision": ["computer vision"],
    "Git": ["git"], "Microservices": ["microservices", "microservice"],
    "Distributed Systems": ["distributed systems"], "Agile": ["agile"], "Scrum": ["scrum"],
}


def _compile(aliases: list[str]) -> list[re.Pattern]:
    # Bound each alias by non-alphanumeric so "go" doesn't match "google" and "java" not "javascript".
    return [re.compile(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])") for a in aliases]


_PATTERNS = {canon: _compile(aliases) for canon, aliases in SKILLS.items()}


def extract_skills(text: str) -> set[str]:
    """Canonical skills detected in a blob of text."""
    low = (text or "").lower()
    return {canon for canon, pats in _PATTERNS.items() if any(p.search(low) for p in pats)}


def overlap_and_gaps(candidate_skills: set[str], job_text: str) -> tuple[list[str], list[str]]:
    """Given the candidate's skills, split a job's detected skills into matches and gaps."""
    job = extract_skills(job_text)
    overlap = sorted(job & candidate_skills)
    gaps = sorted(job - candidate_skills)
    return overlap, gaps
