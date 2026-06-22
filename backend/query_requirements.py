import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models.agent import AgentRun

def load_dotenv_manually():
    env_vars = {}
    env_path = "c:/Test_AI_Agents/Test_AI_Agents/stlc-platform/.env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

def query_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        env_vars = load_dotenv_manually()
        database_url = env_vars.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stlc_agents")
        database_url = database_url.replace("@db:", "@localhost:")
    
    print(f"Connecting to database: {database_url.split('@')[-1]}")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    session = Session()
    try:
        # Get all agent runs
        runs = session.execute(
            select(AgentRun)
            .order_by(AgentRun.id.desc())
        ).scalars().all()
        print(f"Total agent runs: {len(runs)}")
        for r in runs[:15]:  # print newest 15 runs
            print(f"  Run ID: {r.id}")
            print(f"    Project ID: {r.project_id}")
            print(f"    Agent Name: {r.agent_name}")
            print(f"    Status: {r.status}")
            print(f"    Error: {r.error_message}")
            try:
                print(f"    Progress: {r.progress_percent}%")
            except AttributeError:
                pass
            print(f"    Created At: {r.created_at}")
            print("-" * 30)
            
    finally:
        session.close()

if __name__ == "__main__":
    query_db()
