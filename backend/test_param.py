from sqlalchemy import select, func
from app.models.requirement import Requirement

stmt = select(func.count(Requirement.id)).where(Requirement.status.in_(["draft", "pending_approval"]))
print("String:", str(stmt))
print("Params:", stmt.compile().params)
