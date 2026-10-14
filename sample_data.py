"""Fictional jobs and CV for a repeatable offline rehearsal."""

from jobs import Job

CV = """Alex Chen — fictional résumé
6 years of experience delivering analytics projects with client teams.
Led stakeholder workshops with operations teams to identify process bottlenecks.
Built Python prototypes for document triage and used SQL for data analysis.
Designed prompt engineering experiments and evaluated AI outputs with reviewers.
Presented findings to business sponsors. Have not deployed a cloud application.
"""


def demo_jobs() -> list[Job]:
    specs = [
        ("AI Consultant", "AI", "Python and SQL; 4+ years of experience. Lead stakeholder workshops and AI evaluation.", "SGD 120k - SGD 160k"),
        ("AI Strategy Consultant", "AI", "Python and prompt engineering; 5+ years of experience. Stakeholder workshops.", "SGD 110k - SGD 150k"),
        ("Data Consultant", "Data", "SQL and data analysis; 3+ years of experience. Work with clients.", "SGD 100k - SGD 140k"),
        ("AI Implementation Consultant", "AI", "Python, SQL and cloud deployment; 5+ years of experience.", "SGD 95k - SGD 125k"),
        ("Machine Learning Consultant", "AI", "AI evaluation and Python; 7+ years of experience.", "SGD 155k - SGD 190k"),
        ("AI Product Consultant", "AI", "Stakeholder workshops and prompt engineering; 4+ years of experience.", ""),
        ("AI Transformation Consultant", "AI", "Change management and stakeholder workshops; 5+ years of experience.", "SGD 130k - SGD 165k"),
        ("AI Solutions Consultant", "AI", "Python, SQL and AI evaluation; 2+ years of experience.", "SGD 85k - SGD 105k"),
        ("AI Research Engineer", "AI", "Python and AI evaluation; 3+ years of experience.", "SGD 130k - SGD 170k"),
        ("Marketing Consultant", "Marketing", "Campaign analytics and stakeholder workshops; 2+ years of experience.", "SGD 90k - SGD 120k"),
        ("AI Advisory Consultant", "AI", "SQL, Python and stakeholder workshops; 4+ years of experience.", "SGD 135k - SGD 170k"),
        ("AI Governance Consultant", "AI", "AI evaluation and stakeholder workshops; 6+ years of experience.", "SGD 140k - SGD 175k"),
    ]
    return [Job(id=f"demo-{i}", title=title, company=f"Demo Company {i}", category=domain,
                location="Singapore (fictional)", salary=salary, description=description,
                url="", source="Fictional example")
            for i, (title, domain, description, salary) in enumerate(specs, 1)]
